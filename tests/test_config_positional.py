"""Unit tests for positional-mode `column_bounds` config parsing/validation."""

import pytest

from statement_parser.models import ColumnBounds, ConfigError, TransactionConfig


def tcfg(column_bounds, **extra):
    data = {"mode": "positional", "date_pattern": r"^\d+$", "column_bounds": column_bounds}
    data.update(extra)
    return TransactionConfig.from_dict(data)


# --- ColumnBounds edge matching -------------------------------------------


def test_left_edge_bounds_inclusive():
    cb = ColumnBounds.from_dict("date", {"left_edge_min": 10, "left_edge_max": 50})
    assert cb.matches_left_edge(10) is True   # inclusive lower
    assert cb.matches_left_edge(50) is True   # inclusive upper
    assert cb.matches_left_edge(30) is True
    assert cb.matches_left_edge(9) is False
    assert cb.matches_left_edge(51) is False


def test_right_edge_bounds_inclusive():
    cb = ColumnBounds.from_dict("amount", {"right_edge_min": 480, "right_edge_max": 560})
    assert cb.matches_right_edge(480) is True
    assert cb.matches_right_edge(560) is True
    assert cb.matches_right_edge(479) is False
    assert cb.matches_right_edge(561) is False


def test_right_edge_range_sugar():
    cb = ColumnBounds.from_dict("amount", {"right_edge_range": [480, 560]})
    assert cb.right_edge_min == 480
    assert cb.right_edge_max == 560
    assert cb.matches_right_edge(500) is True
    assert cb.matches_right_edge(470) is False


def test_open_ended_bounds():
    # Only an upper bound -> everything at/below matches.
    cb = ColumnBounds.from_dict("paid_out", {"right_edge_max": 410})
    assert cb.matches_right_edge(0) is True
    assert cb.matches_right_edge(410) is True
    assert cb.matches_right_edge(411) is False


# --- ColumnBounds validation errors ---------------------------------------


def test_unknown_bound_key_rejected():
    with pytest.raises(ConfigError, match="unknown bound"):
        ColumnBounds.from_dict("amount", {"right_edge_maximum": 500})


def test_range_cannot_combine_with_min_max():
    with pytest.raises(ConfigError, match="cannot be combined"):
        ColumnBounds.from_dict("amount", {"right_edge_range": [1, 2], "right_edge_min": 3})


def test_range_must_be_pair():
    with pytest.raises(ConfigError, match="must be \\[lo, hi\\]"):
        ColumnBounds.from_dict("amount", {"right_edge_range": [1, 2, 3]})


# --- TransactionConfig positional validation ------------------------------


def test_positional_requires_column_bounds():
    with pytest.raises(ConfigError, match="requires a 'column_bounds'"):
        TransactionConfig.from_dict({"mode": "positional", "date_pattern": r"^\d+$"})


def test_positional_single_amount_layout_ok():
    cfg = tcfg({"date": {"left_edge_max": 50}, "amount": {"right_edge_range": [480, 560]}})
    assert "amount" in cfg.column_bounds
    assert cfg.column_bounds["amount"].right_edge_min == 480


def test_positional_two_column_layout_ok():
    cfg = tcfg(
        {
            "paid_out": {"right_edge_max": 410},
            "paid_in": {"right_edge_max": 495},
            "balance": {"right_edge_min": 495},
        }
    )
    assert {"paid_out", "paid_in", "balance"} <= set(cfg.column_bounds)


def test_positional_needs_amount_or_paid_pair():
    with pytest.raises(ConfigError, match="must define either an 'amount'"):
        tcfg({"paid_out": {"right_edge_max": 410}})  # paid_in missing


def test_positional_cannot_mix_amount_and_paid():
    with pytest.raises(ConfigError, match="cannot mix 'amount'"):
        tcfg(
            {
                "amount": {"right_edge_max": 500},
                "paid_out": {"right_edge_max": 410},
                "paid_in": {"right_edge_max": 495},
            }
        )


def test_positional_unknown_column_rejected():
    with pytest.raises(ConfigError, match="unknown column"):
        tcfg({"amount": {"right_edge_max": 500}, "foreign_spend": {"right_edge_max": 418}})


def test_positional_requires_date_pattern():
    with pytest.raises(ConfigError, match="date_pattern is required"):
        TransactionConfig.from_dict(
            {"mode": "positional", "column_bounds": {"amount": {"right_edge_max": 500}}}
        )


# --- Region page / pages ---------------------------------------------------

from statement_parser.models import Region


def test_region_single_page():
    r = Region.from_dict({"page": 3})
    assert r.page_numbers(5) == [3]
    assert r.page_numbers(2) == []           # out of range -> empty


def test_region_pages_list():
    r = Region.from_dict({"pages": [4, 5]})
    assert r.page_numbers(6) == [4, 5]
    assert r.page_numbers(4) == [4]          # clamp to available pages


def test_region_no_page_means_all():
    assert Region.from_dict({}).page_numbers(3) is None


def test_region_page_and_pages_mutually_exclusive():
    with pytest.raises(ConfigError, match="not both"):
        Region.from_dict({"page": 1, "pages": [2, 3]})


def test_region_pages_must_be_nonempty_list():
    with pytest.raises(ConfigError, match="non-empty list"):
        Region.from_dict({"pages": []})
