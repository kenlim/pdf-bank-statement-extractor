"""Unit tests for date/amount normalization."""

from decimal import Decimal

import pytest

from statement_parser.models import NormalizationConfig
from statement_parser.normalize import (
    NormalizationError,
    normalize_amount,
    normalize_date,
    resolve_period_end,
    resolve_year_for_month_day,
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


# --- year-from-period resolution (Amex-style bare month-day dates) ---------

PERIOD_END_RE = r"to\d{1,2}([A-Za-z]+?)(\d{4})"


def test_resolve_period_end_no_spaces():
    assert resolve_period_end("11April to10May2022", PERIOD_END_RE) == (5, 2022)
    assert resolve_period_end("11May to10June2022", PERIOD_END_RE) == (6, 2022)


def test_resolve_period_end_missing_or_unmatched():
    assert resolve_period_end(None, PERIOD_END_RE) is None
    assert resolve_period_end("no period here", PERIOD_END_RE) is None


def test_resolve_year_same_year():
    end = (5, 2022)  # period ends May 2022
    assert resolve_year_for_month_day("Apr30", end, ["%b%d"]) == "2022-04-30"
    assert resolve_year_for_month_day("May9", end, ["%b%d"]) == "2022-05-09"


def test_resolve_year_wraps_previous_year():
    end = (1, 2023)  # period ends January 2023 (Dec -> Jan)
    assert resolve_year_for_month_day("Dec15", end, ["%b%d"]) == "2022-12-15"
    assert resolve_year_for_month_day("Dec31", end, ["%b%d"]) == "2022-12-31"
    assert resolve_year_for_month_day("Jan3", end, ["%b%d"]) == "2023-01-03"


def test_resolve_year_empty_passthrough_and_errors():
    end = (5, 2022)
    assert resolve_year_for_month_day("", end, ["%b%d"]) is None
    assert resolve_year_for_month_day(None, end, ["%b%d"]) is None
    with pytest.raises(NormalizationError):
        resolve_year_for_month_day("May9", None, ["%b%d"])  # no period end
    with pytest.raises(NormalizationError):
        resolve_year_for_month_day("garbage", end, ["%b%d"])  # unparseable


def test_collapse_extra_decimals_opt_in():
    n = norm(collapse_extra_decimals=True)
    assert normalize_amount("£1.182.62", n) == Decimal("1182.62")
    assert normalize_amount("£11.40", n) == Decimal("11.40")      # single dot untouched
    assert normalize_amount("£1,234.56", n) == Decimal("1234.56")  # normal thousands


def test_collapse_extra_decimals_off_by_default_errors():
    with pytest.raises(NormalizationError):
        normalize_amount("£1.182.62", norm())
