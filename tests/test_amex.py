"""Integration test: parse the synthetic Amex (positional single-amount column
with credit markers and an ignored foreign-spend column) fixture vs goldens."""

from pathlib import Path

import pdfplumber

from statement_parser.config import detect_bank, load_extractors
from statement_parser.extract import extract, read_full_text
from statement_parser.output import to_csv, to_json
from statement_parser.reconcile import reconcile

FIXTURES = Path(__file__).parent / "fixtures"
EXTRACTORS = Path(__file__).parents[1] / "extractors"
PDF = FIXTURES / "amex.pdf"


def _extract_statement():
    extractors = load_extractors([EXTRACTORS])
    with pdfplumber.open(PDF) as pdf:
        cfg = detect_bank(read_full_text(pdf), extractors)
        assert cfg is not None and cfg.name == "amex"
        return extract(pdf, cfg)


def test_amex_auto_detect_and_extract():
    stmt = _extract_statement()
    assert stmt.bank == "amex"
    # 6 transactions; the per-cardmember subtotal row is skipped.
    assert len(stmt.transactions) == 6


def test_amex_credit_marker_sign():
    stmt = _extract_statement()
    by_desc = {t.description: t.amount for t in stmt.transactions}
    # "CR" payment/refund -> negative; spending -> positive.
    assert by_desc["PAYMENT RECEIVED - THANK YOU"] < 0
    assert by_desc["FAKE MOTORS LIMITED FAKETOWN"] > 0


def test_amex_foreign_spend_ignored():
    stmt = _extract_statement()
    by_desc = {t.description: t.amount for t in stmt.transactions}
    # The foreign transaction's sterling Amount is used, not the foreign-spend
    # sub-amount (997.00) or the non-sterling fee, and the currency name is
    # not swept into the description.
    assert by_desc["FAKE MEMBERSHIP UNLIM FAKELAND"] == __import__("decimal").Decimal("836.43")


def test_amex_multiline_descriptions_joined():
    stmt = _extract_statement()
    descs = {t.description for t in stmt.transactions}
    assert "FAKE MOTORS LIMITED FAKETOWN" in descs  # two lines joined
    assert "FAKE SPORTS CLUB FAKETOWN" in descs


def test_amex_dates_resolved_from_period():
    stmt = _extract_statement()
    by_desc = {t.description: t.date for t in stmt.transactions}
    # Bare month-day tokens are resolved to full ISO dates using the statement
    # period "11April to10May2022": April -> 2022, May -> 2022.
    assert by_desc["FAKE MOTORS LIMITED FAKETOWN"] == "2022-04-11"
    assert by_desc["FAKE LODGING * REF123 FAKECITY"] == "2022-05-03"
    assert by_desc["FAKE MEMBERSHIP UNLIM FAKELAND"] == "2022-05-09"


def test_amex_csv_matches_golden():
    stmt = _extract_statement()
    golden = (FIXTURES / "amex.golden.csv").read_text()
    assert to_csv(stmt) == golden


def test_amex_json_matches_golden():
    stmt = _extract_statement()
    golden = (FIXTURES / "amex.golden.json").read_text()
    assert to_json(stmt) == golden


def test_amex_reconciles():
    r = reconcile(_extract_statement())
    assert r is not None and r.ok
