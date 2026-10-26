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

    bbox is (x0, top, x1, bottom) in PDF points. `page` pins a single 1-indexed
    page; `pages` pins several. All optional; when both are absent every page is
    used. `page` and `pages` are mutually exclusive.
    """

    bbox: Optional[tuple[float, float, float, float]] = None
    page: Optional[int] = None  # 1-indexed; None means all pages
    pages: Optional[list[int]] = None  # 1-indexed list; alternative to `page`

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "Region":
        if not data:
            return cls()
        bbox = data.get("bbox")
        if bbox is not None:
            bbox = tuple(float(v) for v in bbox)  # type: ignore[assignment]
            if len(bbox) != 4:
                raise ConfigError("region.bbox must have exactly 4 numbers (x0, top, x1, bottom)")
        page = data.get("page")
        pages = data.get("pages")
        if page is not None and pages is not None:
            raise ConfigError("region may set 'page' or 'pages', not both")
        if pages is not None:
            if not isinstance(pages, list) or not pages:
                raise ConfigError("region.pages must be a non-empty list of page numbers")
            pages = [int(p) for p in pages]
        return cls(bbox=bbox, page=page, pages=pages)

    def page_numbers(self, total: int) -> Optional[list[int]]:
        """Resolve to a sorted list of 1-indexed page numbers, or None for all."""
        if self.pages is not None:
            return sorted(p for p in self.pages if 1 <= p <= total)
        if self.page is not None:
            return [self.page] if 1 <= self.page <= total else []
        return None


@dataclass
class ColumnBounds:
    """The x-coordinate footprint of one positional-mode column, in PDF points.

    Text columns (date, description) are matched by a word's LEFT edge (x0);
    amount-style columns (amount, paid_out, paid_in, balance) are matched by a
    number's RIGHT edge (x1), since those columns are right-aligned. All bounds
    are inclusive. A word/number falls in the column when every bound it sets
    is satisfied.

    Keys (all optional, mix as needed):
      left_edge_min:   x0 >= value
      left_edge_max:   x0 <= value
      right_edge_min:  x1 >= value
      right_edge_max:  x1 <= value
      right_edge_range: [lo, hi]  ->  lo <= x1 <= hi
    """

    left_edge_min: Optional[float] = None
    left_edge_max: Optional[float] = None
    right_edge_min: Optional[float] = None
    right_edge_max: Optional[float] = None

    @classmethod
    def from_dict(cls, col_name: str, data: dict[str, Any]) -> "ColumnBounds":
        if not isinstance(data, dict):
            raise ConfigError(
                f"column '{col_name}' must be a mapping of edge bounds"
            )
        known = {
            "left_edge_min",
            "left_edge_max",
            "right_edge_min",
            "right_edge_max",
            "right_edge_range",
        }
        unknown = set(data) - known
        if unknown:
            raise ConfigError(
                f"column '{col_name}' has unknown bound(s): {sorted(unknown)}. "
                f"Allowed: {sorted(known)}"
            )
        right_min = data.get("right_edge_min")
        right_max = data.get("right_edge_max")
        rng = data.get("right_edge_range")
        if rng is not None:
            if right_min is not None or right_max is not None:
                raise ConfigError(
                    f"column '{col_name}': right_edge_range cannot be combined "
                    f"with right_edge_min/right_edge_max"
                )
            if not (isinstance(rng, (list, tuple)) and len(rng) == 2):
                raise ConfigError(
                    f"column '{col_name}': right_edge_range must be [lo, hi]"
                )
            right_min, right_max = rng[0], rng[1]
        return cls(
            left_edge_min=(
                float(data["left_edge_min"]) if data.get("left_edge_min") is not None else None
            ),
            left_edge_max=(
                float(data["left_edge_max"]) if data.get("left_edge_max") is not None else None
            ),
            right_edge_min=float(right_min) if right_min is not None else None,
            right_edge_max=float(right_max) if right_max is not None else None,
        )

    def matches_left_edge(self, x0: float) -> bool:
        """Whether a word at left edge x0 falls in this (text) column."""
        if self.left_edge_min is not None and x0 < self.left_edge_min:
            return False
        if self.left_edge_max is not None and x0 > self.left_edge_max:
            return False
        return True

    def matches_right_edge(self, x1: float) -> bool:
        """Whether a number at right edge x1 falls in this (amount) column."""
        if self.right_edge_min is not None and x1 < self.right_edge_min:
            return False
        if self.right_edge_max is not None and x1 > self.right_edge_max:
            return False
        return True


@dataclass
class TransactionConfig:
    """How to find and interpret the transaction table.

    Two modes:
      - mode="table": use pdfplumber's table extraction (ruled or text grids).
        Requires `columns` (field -> column index).
      - mode="lines": apply `row_pattern` (a regex with named groups) to each
        text line across pages. Lines that don't match are skipped. Good for
        whitespace-aligned statements with no usable grid lines.
      - mode="positional": classify words by their x-position into columns
        (date, description, paid_out, paid_in, balance). Accumulates
        multi-line descriptions and emits a transaction whenever a row carries
        a paid_out or paid_in amount. signed amount = paid_in - paid_out.
        Good for statements with separate debit/credit columns (HSBC, Barclays,
        Lloyds, NatWest) that have no grid lines.
    """

    mode: str = "table"  # "table" | "lines" | "positional"
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
    # positional mode: per-column x-coordinate footprints (PDF points, NOT
    # monetary limits). A mapping of column name -> ColumnBounds for the
    # columns present on the statement. Recognised column names:
    #   date, description : matched by a word's LEFT edge (x0)
    #   amount            : single signed-amount column (matched by RIGHT edge)
    #   paid_out, paid_in : two-column debit/credit layout (matched by RIGHT
    #                       edge); signed amount = paid_in - paid_out
    #   balance           : running balance (matched by RIGHT edge)
    # A number that matches no amount-style column is IGNORED (e.g. an Amex
    # "Foreign Spend" sub-amount that falls left of the amount column's band).
    # date_pattern recognizes a date cell in the date column.
    column_bounds: dict[str, "ColumnBounds"] = field(default_factory=dict)
    amount_pattern: str = r"^-?[\d,]+\.\d{2}$"
    date_pattern: Optional[str] = None  # recognizes a date string (e.g. "01 Sep 26")
    row_y_tolerance: float = 4.0  # words within this many points vertically = same row
    desc_below: bool = False  # also attach description rows BELOW the amount row (until a date/skip)
    # Resolve a full year for bare month-day dates (e.g. "Apr30") from the
    # statement period. When set, it names the extracted field holding the
    # period text and a regex that captures the period's END month and year
    # (e.g. "May" and "2022" from "11April to10May2022"). A transaction's year
    # is the end year, or end year - 1 when its month sorts after the end month
    # (i.e. it belongs to the earlier side of a period that crosses a year
    # boundary). Requires the raw date to match one of the normalization's
    # month-day date_formats once a year is appended.
    year_from_period: Optional[dict] = None
    # Non-numeric tokens on an amount row that flip the signed amount negative,
    # e.g. ["CR"] on a credit-card statement where a credit/payment is money in.
    credit_markers: list[str] = field(default_factory=list)
    skip_rows_matching: list[str] = field(default_factory=list)  # e.g. BALANCE*FORWARD

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TransactionConfig":
        mode = data.get("mode", "table")
        if mode not in ("table", "lines", "positional"):
            raise ConfigError(
                f"transactions.mode must be 'table', 'lines', or 'positional', got {mode!r}"
            )

        columns: dict[str, int] = {}
        row_pattern = None
        column_bounds: dict[str, ColumnBounds] = {}
        date_pattern = None

        if mode == "table":
            cols = data.get("columns") or {}
            if not cols:
                raise ConfigError("transactions.columns is required in table mode (map field -> column index)")
            columns = {k: int(v) for k, v in cols.items()}
        elif mode == "lines":
            row_pattern = data.get("row_pattern")
            if not row_pattern:
                raise ConfigError("transactions.row_pattern is required in lines mode")
        else:  # positional
            raw_bounds = data.get("column_bounds")
            if not isinstance(raw_bounds, dict) or not raw_bounds:
                raise ConfigError(
                    "positional mode requires a 'column_bounds' mapping of "
                    "column name -> edge bounds"
                )
            allowed_cols = {"date", "description", "amount", "paid_out", "paid_in", "balance"}
            unknown = set(raw_bounds) - allowed_cols
            if unknown:
                raise ConfigError(
                    f"column_bounds has unknown column(s): {sorted(unknown)}. "
                    f"Allowed: {sorted(allowed_cols)}"
                )
            column_bounds = {
                name: ColumnBounds.from_dict(name, spec) for name, spec in raw_bounds.items()
            }
            has_single = "amount" in column_bounds
            has_two_col = "paid_out" in column_bounds and "paid_in" in column_bounds
            if not (has_single or has_two_col):
                raise ConfigError(
                    "positional column_bounds must define either an 'amount' "
                    "column (single signed-amount layout) or both 'paid_out' "
                    "and 'paid_in' columns (debit/credit layout)"
                )
            if has_single and has_two_col:
                raise ConfigError(
                    "positional column_bounds cannot mix 'amount' with "
                    "'paid_out'/'paid_in'; choose one layout"
                )
            date_pattern = data.get("date_pattern")
            if not date_pattern:
                raise ConfigError("transactions.date_pattern is required in positional mode")

        return cls(
            mode=mode,
            table_settings=data.get("table_settings") or {},
            region=Region.from_dict(data.get("region")),
            columns=columns,
            header_rows=int(data.get("header_rows", 1)),
            header_labels=list(data.get("header_labels") or []),
            row_pattern=row_pattern,
            column_bounds=column_bounds,
            amount_pattern=data.get("amount_pattern", r"^-?[\d,]+\.\d{2}$"),
            date_pattern=date_pattern,
            row_y_tolerance=float(data.get("row_y_tolerance", 4.0)),
            desc_below=bool(data.get("desc_below", False)),
            credit_markers=list(data.get("credit_markers") or []),
            skip_rows_matching=list(data.get("skip_rows_matching") or []),
            year_from_period=(
                dict(data["year_from_period"])
                if data.get("year_from_period") is not None
                else None
            ),
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
    # If True, when a number has more than one decimal separator (an OCR quirk
    # seen on some statements, e.g. "1.182.62" meaning 1,182.62), treat all but
    # the LAST separator as thousands separators. Off by default.
    collapse_extra_decimals: bool = False

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
            collapse_extra_decimals=bool(data.get("collapse_extra_decimals", False)),
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
