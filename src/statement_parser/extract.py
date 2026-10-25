"""The extraction engine: turn a PDF + extractor config into a Statement."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Optional

import pdfplumber

from .models import (
    ExtractorConfig,
    FieldConfig,
    Region,
    Statement,
    Transaction,
    TransactionConfig,
)
from .normalize import normalize_amount, normalize_date


class ExtractionError(Exception):
    """Raised when extraction fails after a bank has been matched."""


def read_full_text(pdf: pdfplumber.PDF) -> str:
    """Concatenated text of every page, used for bank auto-detection."""
    return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _pages_for(pdf: pdfplumber.PDF, page: Optional[int]) -> list[Any]:
    if page is None:
        return list(pdf.pages)
    if page < 1 or page > len(pdf.pages):
        return []
    return [pdf.pages[page - 1]]


def _region_of(page: Any, region: Region) -> Any:
    if region.bbox is None:
        return page
    return page.crop(region.bbox)


def _extract_fields(pdf: pdfplumber.PDF, fields: list[FieldConfig], norm) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for fc in fields:
        value = _extract_one_field(pdf, fc)
        if value is None:
            result[fc.name] = None
            continue
        if fc.kind == "amount":
            result[fc.name] = normalize_amount(value, norm)
        elif fc.kind == "date":
            result[fc.name] = normalize_date(value, norm)
        else:
            result[fc.name] = value
    return result


def _extract_one_field(pdf: pdfplumber.PDF, fc: FieldConfig) -> Optional[str]:
    pattern = re.compile(fc.pattern, re.IGNORECASE | re.MULTILINE)
    for page in _pages_for(pdf, fc.page):
        target = page.crop(fc.bbox) if fc.bbox else page
        text = target.extract_text() or ""
        m = pattern.search(text)
        if m:
            # Use first capture group if present, else the whole match.
            return (m.group(1) if m.groups() else m.group(0)).strip()
    return None


def _is_header_row(row: list[Optional[str]], tcfg: TransactionConfig) -> bool:
    if not tcfg.header_labels:
        return False
    cells = {(c or "").strip().lower() for c in row}
    labels = {lbl.strip().lower() for lbl in tcfg.header_labels}
    # Treat as header if the row's cells are a subset of known header labels
    # (and it contains at least one).
    non_empty = {c for c in cells if c}
    if not non_empty:
        return False
    return non_empty.issubset(labels)


def _extract_transactions(pdf: pdfplumber.PDF, cfg: ExtractorConfig) -> list[Transaction]:
    if cfg.transactions.mode == "lines":
        return _extract_transactions_lines(pdf, cfg)
    if cfg.transactions.mode == "positional":
        return _extract_transactions_positional(pdf, cfg)
    return _extract_transactions_table(pdf, cfg)


def _row_to_transaction(raw: dict[str, str], norm) -> Transaction:
    return Transaction(
        date=normalize_date(raw.get("date"), norm) if "date" in raw else None,
        description=(raw.get("description") or "").strip() or None,
        amount=normalize_amount(raw.get("amount"), norm) if "amount" in raw else None,
        balance=normalize_amount(raw.get("balance"), norm) if "balance" in raw else None,
        raw=raw,
    )


def _extract_transactions_lines(pdf: pdfplumber.PDF, cfg: ExtractorConfig) -> list[Transaction]:
    tcfg = cfg.transactions
    norm = cfg.normalization
    pattern = re.compile(tcfg.row_pattern)  # type: ignore[arg-type]

    transactions: list[Transaction] = []
    for page in _pages_for(pdf, tcfg.region.page):
        region = _region_of(page, tcfg.region)
        text = region.extract_text() or ""
        for line in text.split("\n"):
            m = pattern.match(line.strip())
            if not m:
                continue
            raw = {k: (v or "") for k, v in m.groupdict().items()}
            transactions.append(_row_to_transaction(raw, norm))
    return transactions


def _group_words_into_rows(words: list[dict], y_tol: float) -> list[list[dict]]:
    """Group words into visual rows by vertical proximity (`top`)."""
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(w["top"] - rows[-1][0]["top"]) <= y_tol:
            rows[-1].append(w)
        else:
            rows.append([w])
    for r in rows:
        r.sort(key=lambda w: w["x0"])
    return rows


def _extract_transactions_positional(pdf: pdfplumber.PDF, cfg: ExtractorConfig) -> list[Transaction]:
    """Classify words by x-position into date / description / paid_out / paid_in
    / balance columns, accumulating multi-line descriptions and emitting a
    transaction whenever a row carries a paid_out or paid_in amount.
    """
    tcfg = cfg.transactions
    norm = cfg.normalization
    amt_re = re.compile(tcfg.amount_pattern)
    date_re = re.compile(tcfg.date_pattern)  # type: ignore[arg-type]
    skip_res = [re.compile(p) for p in tcfg.skip_rows_matching]

    transactions: list[Transaction] = []
    current_date: Optional[str] = None
    pending_desc: list[str] = []  # description fragments not yet attached to a txn

    for page in _pages_for(pdf, tcfg.region.page):
        region = _region_of(page, tcfg.region)
        words = region.extract_words()
        for row in _group_words_into_rows(words, tcfg.row_y_tolerance):
            # Partition the row's words into columns by position.
            date_tokens: list[str] = []
            desc_tokens: list[str] = []
            paid_out = paid_in = balance = None
            for w in row:
                text = w["text"]
                x0, x1 = w["x0"], w["x1"]
                if amt_re.match(text):
                    if x1 <= tcfg.paid_out_max:  # type: ignore[operator]
                        paid_out = text
                    elif x1 <= tcfg.paid_in_max:  # type: ignore[operator]
                        paid_in = text
                    else:
                        balance = text
                elif tcfg.date_x_max is not None and x0 <= tcfg.date_x_max:
                    date_tokens.append(text)
                else:
                    desc_tokens.append(text)

            # A date in the date column updates the running date.
            if date_tokens:
                maybe_date = " ".join(date_tokens)
                if date_re.match(maybe_date):
                    current_date = maybe_date
                else:
                    # Not a real date (e.g. a column 'A' marker); treat as desc.
                    desc_tokens = date_tokens + desc_tokens

            row_text = " ".join(w["text"] for w in row)
            if any(r.search(row_text) for r in skip_res):
                pending_desc = []
                continue

            if desc_tokens:
                pending_desc.append(" ".join(desc_tokens))

            # Emit a transaction when this row carries a paid_out or paid_in amount.
            if paid_out is not None or paid_in is not None:
                out_val = normalize_amount(paid_out, norm) if paid_out else None
                in_val = normalize_amount(paid_in, norm) if paid_in else None
                signed = (in_val or 0) - (out_val or 0)
                transactions.append(
                    Transaction(
                        date=normalize_date(current_date, norm) if current_date else None,
                        description=" ".join(pending_desc).strip() or None,
                        amount=signed,
                        balance=normalize_amount(balance, norm) if balance else None,
                        raw={
                            "date": current_date or "",
                            "description": " ".join(pending_desc).strip(),
                            "paid_out": paid_out or "",
                            "paid_in": paid_in or "",
                            "balance": balance or "",
                        },
                    )
                )
                pending_desc = []

    return transactions


def _extract_transactions_table(pdf: pdfplumber.PDF, cfg: ExtractorConfig) -> list[Transaction]:
    tcfg = cfg.transactions
    norm = cfg.normalization
    rows: list[list[Optional[str]]] = []

    for page in _pages_for(pdf, tcfg.region.page):
        region = _region_of(page, tcfg.region)
        tables = region.extract_tables(tcfg.table_settings or None)
        for table in tables:
            page_rows = table[tcfg.header_rows :] if tcfg.header_rows else table
            for row in page_rows:
                if _is_header_row(row, tcfg):
                    continue
                if all((c or "").strip() == "" for c in row):
                    continue
                rows.append(row)

    transactions: list[Transaction] = []
    for row in rows:
        raw: dict[str, str] = {}
        for field_name, col_idx in tcfg.columns.items():
            raw[field_name] = (row[col_idx] if 0 <= col_idx < len(row) else "") or ""
        transactions.append(_row_to_transaction(raw, norm))
    return transactions


def extract(pdf: pdfplumber.PDF, cfg: ExtractorConfig) -> Statement:
    """Run a bank's extractor against an opened PDF."""
    fields = _extract_fields(pdf, cfg.fields, cfg.normalization)
    transactions = _extract_transactions(pdf, cfg)

    if not transactions:
        region = cfg.transactions.region
        where = f"page {region.page}" if region.page else "all pages"
        if region.bbox:
            where += f", bbox {region.bbox}"
        raise ExtractionError(
            f"matched bank '{cfg.name}' but extracted zero transactions "
            f"(searched {where}). The statement layout may have changed, or the "
            f"transaction region/table_settings in {cfg.source_path} may be wrong."
        )

    return Statement(bank=cfg.name, fields=fields, transactions=transactions)
