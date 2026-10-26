"""Integration test: parse the synthetic Tesco Clubcard fixture vs goldens.

Exercises positional single-amount-column extraction with: leading-minus
payments/refunds, a foreign transaction with a separate fee line, the
"£1.182.62" OCR decimal-collapse, year resolution from the statement period
(Dec -> previous year), and a page-pinned transaction region.
"""

from decimal import Decimal
from pathlib import Path

import pdfplumber

from statement_parser.config import detect_bank, load_extractors
from statement_parser.extract import extract, read_full_text
from statement_parser.output import to_csv, to_json
from statement_parser.reconcile import reconcile

FIXTURES = Path(__file__).parent / "fixtures"
EXTRACTORS = Path(__file__).parents[1] / "extractors"
PDF = FIXTURES / "tesco.pdf"


def _extract_statement():
    extractors = load_extractors([EXTRACTORS])
    with pdfplumber.open(PDF) as pdf:
        cfg = detect_bank(read_full_text(pdf), extractors)
        assert cfg is not None and cfg.name == "tesco"
        return extract(pdf, cfg)


def test_tesco_auto_detect_and_extract():
    stmt = _extract_statement()
    assert stmt.bank == "tesco"
    # 6 purchases/payments + the foreign purchase + its separate fee = 8 rows;
    # BALANCE FROM PREVIOUS / NEW BALANCE markers are skipped.
    assert len(stmt.transactions) == 8


def test_tesco_payment_and_refund_negative():
    stmt = _extract_statement()
    by_desc = {t.description: t.amount for t in stmt.transactions}
    assert by_desc["FASTERPAYMENT-THANKYOU"] == Decimal("-791.02")
    assert by_desc["FAKE STORE REFUND FAKETOWN GB"] == Decimal("-5.40")


def test_tesco_foreign_amount_and_fee():
    stmt = _extract_statement()
    amounts = {t.description: t.amount for t in stmt.transactions}
    # Converted sterling amount parsed despite the "£1.182.62" OCR double-dot.
    foreign = next(a for d, a in amounts.items() if d.startswith("FAKE TUITION"))
    assert foreign == Decimal("1182.62")
    # The non-sterling fee is captured as its own charge.
    fee = next(a for d, a in amounts.items() if "FOREIGNEXCHANGEFEE" in d)
    assert fee == Decimal("32.52")


def test_tesco_dates_resolved_across_year_boundary():
    stmt = _extract_statement()
    by_desc = {t.description: t.date for t in stmt.transactions}
    # Statement period "17December 2021 - 16January 2022": December -> 2021,
    # January -> 2022.
    assert by_desc["FAKE GROCER STORE FAKETOWN"] == "2021-12-15"
    assert by_desc["FASTERPAYMENT-THANKYOU"] == "2022-01-03"


def test_tesco_csv_matches_golden():
    stmt = _extract_statement()
    assert to_csv(stmt) == (FIXTURES / "tesco.golden.csv").read_text()


def test_tesco_json_matches_golden():
    stmt = _extract_statement()
    assert to_json(stmt) == (FIXTURES / "tesco.golden.json").read_text()


def test_tesco_reconciles():
    r = reconcile(_extract_statement())
    assert r is not None and r.ok
