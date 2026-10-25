"""Data models for extracted statement data and extractor configs."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional


# --- Extracted output models ---------------------------------------------


@dataclass
class Transaction:
    """A single ledger row."""

    date: Optional[str]  # ISO 8601 (YYYY-MM-DD) once normalized
    description: Optional[str]
    amount: Optional[Decimal]  # signed; negative = debit
    balance: Optional[Decimal]  # running balance after the transaction
    raw: dict[str, str] = field(default_factory=dict)  # original column values

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "description": self.description,
            "amount": None if self.amount is None else str(self.amount),
            "balance": None if self.balance is None else str(self.balance),
        }


@dataclass
class Statement:
    """A parsed statement: scalar fields plus the transaction ledger."""

    bank: str
    fields: dict[str, Any] = field(default_factory=dict)
    transactions: list[Transaction] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "bank": self.bank,
            "fields": {
                k: (str(v) if isinstance(v, Decimal) else v)
                for k, v in self.fields.items()
            },
            "transactions": [t.as_dict() for t in self.transactions],
        }


# --- Config models --------------------------------------------------------


@dataclass
class Region:
    """A region of a page to restrict extraction to.

    bbox is (x0, top, x1, bottom) in PDF points. All optional; when absent
    the whole page is used.
    """

    bbox: Optional[tuple[float, float, float, float]] = None
    page: Optional[int] = None  # 1-indexed; None means all pages

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "Region":
        if not data:
            return cls()
        bbox = data.get("bbox")
        if bbox is not None:
            bbox = tuple(float(v) for v in bbox)  # type: ignore[assignment]
            if len(bbox) != 4:
                raise ConfigError("region.bbox must have exactly 4 numbers (x0, top, x1, bottom)")
        return cls(bbox=bbox, page=data.get("page"))


@dataclass
class TransactionConfig:
    """How to find and interpret the transaction table.

    Two modes:
      - mode="table": use pdfplumber's table extraction (ruled or text grids).
        Requires `columns` (field -> column index).
      - mode="lines": apply `row_pattern` (a regex with named groups) to each
        text line across pages. Lines that don't match are skipped. Good for
        whitespace-aligned statements with no usable grid lines.
    """

    mode: str = "table"  # "table" | "lines"
    table_settings: dict[str, Any] = field(default_factory=dict)
    region: Region = field(default_factory=Region)
    # table mode: maps output field name -> column index in the extracted table.
    columns: dict[str, int] = field(default_factory=dict)
    # Number of leading rows to treat as a header (per page). (table mode)
    header_rows: int = 1
    # If a cell's value matches one of these (per the column labels), the row
    # is treated as a repeated header and dropped. (table mode)
    header_labels: list[str] = field(default_factory=list)
    # lines mode: regex with named groups (date, description, amount, balance).
    row_pattern: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TransactionConfig":
        mode = data.get("mode", "table")
        if mode not in ("table", "lines"):
            raise ConfigError(f"transactions.mode must be 'table' or 'lines', got {mode!r}")

        if mode == "table":
            columns = data.get("columns") or {}
            if not columns:
                raise ConfigError("transactions.columns is required in table mode (map field -> column index)")
            columns = {k: int(v) for k, v in columns.items()}
            row_pattern = None
        else:  # lines
            row_pattern = data.get("row_pattern")
            if not row_pattern:
                raise ConfigError("transactions.row_pattern is required in lines mode")
            columns = {}

        return cls(
            mode=mode,
            table_settings=data.get("table_settings") or {},
            region=Region.from_dict(data.get("region")),
            columns=columns,
            header_rows=int(data.get("header_rows", 1)),
            header_labels=list(data.get("header_labels") or []),
            row_pattern=row_pattern,
        )


@dataclass
class FieldConfig:
    """How to extract one scalar statement-level field."""

    name: str
    pattern: str  # regex; first capture group (or whole match) is the value
    page: Optional[int] = None  # 1-indexed; None = search all pages
    bbox: Optional[tuple[float, float, float, float]] = None
    kind: str = "string"  # "string" | "amount" | "date"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "FieldConfig":
        if "pattern" not in data:
            raise ConfigError(f"field '{name}' is missing required 'pattern'")
        bbox = data.get("bbox")
        if bbox is not None:
            bbox = tuple(float(v) for v in bbox)  # type: ignore[assignment]
        return cls(
            name=name,
            pattern=data["pattern"],
            page=data.get("page"),
            bbox=bbox,
            kind=data.get("kind", "string"),
        )


@dataclass
class NormalizationConfig:
    """Per-bank rules for normalizing dates and amounts."""

    # Candidate strptime formats tried in order.
    date_formats: list[str] = field(default_factory=list)
    decimal_separator: str = "."
    thousands_separator: str = ","
    # Tokens that flag a credit / debit when present in the amount string.
    credit_suffixes: list[str] = field(default_factory=lambda: ["CR"])
    debit_suffixes: list[str] = field(default_factory=lambda: ["DR"])
    # If True, parentheses around a number mean a negative value.
    parentheses_negative: bool = True

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "NormalizationConfig":
        data = data or {}
        return cls(
            date_formats=list(data.get("date_formats") or []),
            decimal_separator=data.get("decimal_separator", "."),
            thousands_separator=data.get("thousands_separator", ","),
            credit_suffixes=list(data.get("credit_suffixes") or ["CR"]),
            debit_suffixes=list(data.get("debit_suffixes") or ["DR"]),
            parentheses_negative=bool(data.get("parentheses_negative", True)),
        )


@dataclass
class ExtractorConfig:
    """A complete per-bank extractor definition, loaded from one YAML file."""

    name: str
    match: list[str]  # regex signatures; any match identifies this bank
    transactions: TransactionConfig
    fields: list[FieldConfig] = field(default_factory=list)
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
    source_path: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], source_path: Optional[str] = None) -> "ExtractorConfig":
        name = data.get("name")
        if not name:
            raise ConfigError(f"extractor config is missing 'name' ({source_path})")
        match = data.get("match")
        if not match:
            raise ConfigError(f"extractor '{name}' is missing 'match' signatures")
        if isinstance(match, str):
            match = [match]
        if "transactions" not in data:
            raise ConfigError(f"extractor '{name}' is missing 'transactions' block")

        fields_data = data.get("fields") or {}
        fields_list = [FieldConfig.from_dict(fname, fdata) for fname, fdata in fields_data.items()]

        return cls(
            name=name,
            match=list(match),
            transactions=TransactionConfig.from_dict(data["transactions"]),
            fields=fields_list,
            normalization=NormalizationConfig.from_dict(data.get("normalization")),
            source_path=source_path,
        )


class ConfigError(Exception):
    """Raised when an extractor config is malformed."""
