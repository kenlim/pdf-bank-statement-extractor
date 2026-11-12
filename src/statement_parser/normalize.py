"""Normalization of raw date and amount strings into ISO dates and signed Decimals."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from .models import NormalizationConfig


class NormalizationError(Exception):
    """Raised when a value cannot be normalized under the configured rules."""


def resolve_period_end(period_text: Optional[str], pattern: str) -> Optional[tuple[int, int]]:
    """Extract the period's END (month number, year) from the period text.

    `pattern` must capture the end month name (group 1) and the 4-digit year
    (group 2), e.g. r"to\\s*\\d{1,2}([A-Za-z]+)\\s*(\\d{4})" against
    "11April to10May2022" -> ("May", "2022").
    Returns None if the text is missing or does not match.
    """
    if not period_text:
        return None
    m = re.search(pattern, period_text)
    if not m:
        return None
    month_name, year_str = m.group(1), m.group(2)
    month = _month_number(month_name)
    if month is None:
        return None
    return (month, int(year_str))


def _month_number(name: str) -> Optional[int]:
    name = name.strip()[:3].title()
    for fmt in ("%b",):
        try:
            return datetime.strptime(name, fmt).month
        except ValueError:
            continue
    return None


def resolve_year_for_month_day(
    raw: Optional[str],
    period_end: Optional[tuple[int, int]],
    input_formats: list[str],
) -> Optional[str]:
    """Resolve a bare month-day date (e.g. "Apr30") to an ISO date using the
    statement period's end (month, year).

    The year is the period's end year, or end year - 1 when the transaction's
    month sorts AFTER the end month (so it belongs to the earlier side of a
    period that crosses a calendar-year boundary, e.g. a December transaction
    on a December->January statement).

    `input_formats` are strptime formats for the raw month-day token (year
    defaults to 1900 when parsed alone, so only month/day are used). Returns
    None if the raw value is empty; raises NormalizationError if it is present
    but unparseable, or if no period end is available.
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if period_end is None:
        raise NormalizationError(
            f"cannot resolve year for date {raw!r}: statement period end unavailable"
        )
    end_month, end_year = period_end
    parsed = None
    for fmt in input_formats:
        try:
            parsed = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        raise NormalizationError(
            f"date {raw!r} did not match any month-day format in {input_formats}"
        )
    year = end_year if parsed.month <= end_month else end_year - 1
    return parsed.replace(year=year).strftime("%Y-%m-%d")


def normalize_date(value: Optional[str], norm: NormalizationConfig) -> Optional[str]:
    """Parse a date string using the configured candidate formats -> ISO date."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not norm.date_formats:
        # No formats configured: pass through unchanged.
        return value
    for fmt in norm.date_formats:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise NormalizationError(
        f"date {value!r} did not match any of date_formats={norm.date_formats}"
    )


def normalize_amount(value: Optional[str], norm: NormalizationConfig) -> Optional[Decimal]:
    """Parse an amount string into a signed Decimal.

    Handles thousands/decimal separators, currency symbols, parenthesised
    negatives, and CR/DR suffixes per the normalization config.
    """
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None

    sign = 1

    # Parenthesised negative, e.g. (1,234.56)
    if norm.parentheses_negative and raw.startswith("(") and raw.endswith(")"):
        sign = -1
        raw = raw[1:-1].strip()

    upper = raw.upper()
    for suffix in norm.credit_suffixes:
        if upper.endswith(suffix.upper()):
            raw = raw[: len(raw) - len(suffix)].strip()
            sign = 1
            break
    else:
        for suffix in norm.debit_suffixes:
            if upper.endswith(suffix.upper()):
                raw = raw[: len(raw) - len(suffix)].strip()
                sign = -1
                break

    # Leading minus sign.
    if raw.startswith("-"):
        sign = -1
        raw = raw[1:].strip()
    elif raw.startswith("+"):
        raw = raw[1:].strip()

    # Strip currency symbols and any stray non-numeric chars except separators.
    cleaned = re.sub(r"[^0-9" + re.escape(norm.decimal_separator + norm.thousands_separator) + r"]", "", raw)

    if norm.thousands_separator:
        cleaned = cleaned.replace(norm.thousands_separator, "")
    if norm.decimal_separator != ".":
        cleaned = cleaned.replace(norm.decimal_separator, ".")

    # OCR quirk: a number may carry more than one "." where earlier ones are
    # really thousands separators (e.g. "1.182.62" -> 1182.62). Keep only the
    # last separator as the decimal point.
    if norm.collapse_extra_decimals and cleaned.count(".") > 1:
        head, _, tail = cleaned.rpartition(".")
        cleaned = head.replace(".", "") + "." + tail

    if not cleaned:
        raise NormalizationError(f"amount {value!r} contained no digits")

    try:
        return Decimal(cleaned) * sign
    except InvalidOperation as exc:
        raise NormalizationError(f"amount {value!r} is not a valid number") from exc
