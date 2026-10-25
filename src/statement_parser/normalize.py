"""Normalization of raw date and amount strings into ISO dates and signed Decimals."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from .models import NormalizationConfig


class NormalizationError(Exception):
    """Raised when a value cannot be normalized under the configured rules."""


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

    if not cleaned:
        raise NormalizationError(f"amount {value!r} contained no digits")

    try:
        return Decimal(cleaned) * sign
    except InvalidOperation as exc:
        raise NormalizationError(f"amount {value!r} is not a valid number") from exc
