"""Unit tests for date/amount normalization."""

from decimal import Decimal

import pytest

from statement_parser.models import NormalizationConfig
from statement_parser.normalize import (
    NormalizationError,
    normalize_amount,
    normalize_date,
)


def norm(**kwargs) -> NormalizationConfig:
    return NormalizationConfig.from_dict(kwargs)


def test_date_first_matching_format():
    n = norm(date_formats=["%d/%m/%Y", "%d %b %Y"])
    assert normalize_date("01/02/2024", n) == "2024-02-01"
    assert normalize_date("2 Jan 2024", n) == "2024-01-02"


def test_date_no_format_passes_through():
    assert normalize_date("whatever", norm()) == "whatever"


def test_date_unmatched_raises():
    n = norm(date_formats=["%d/%m/%Y"])
    with pytest.raises(NormalizationError):
        normalize_date("Jan 5 2024", n)


def test_amount_plain():
    assert normalize_amount("1,234.56", norm()) == Decimal("1234.56")


def test_amount_parentheses_negative():
    assert normalize_amount("(4.50)", norm()) == Decimal("-4.50")


def test_amount_leading_minus():
    assert normalize_amount("-73.21", norm()) == Decimal("-73.21")


def test_amount_cr_dr_suffix():
    n = norm(credit_suffixes=["CR"], debit_suffixes=["DR"])
    assert normalize_amount("100.00 CR", n) == Decimal("100.00")
    assert normalize_amount("100.00 DR", n) == Decimal("-100.00")


def test_amount_currency_symbol_stripped():
    assert normalize_amount("$1,000.00", norm()) == Decimal("1000.00")


def test_amount_european_separators():
    n = norm(decimal_separator=",", thousands_separator=".")
    assert normalize_amount("1.234,56", n) == Decimal("1234.56")


def test_amount_empty_is_none():
    assert normalize_amount("", norm()) is None
    assert normalize_amount(None, norm()) is None


def test_amount_no_digits_raises():
    with pytest.raises(NormalizationError):
        normalize_amount("abc", norm())
