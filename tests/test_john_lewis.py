"""Integration test: parse the synthetic John Lewis fixture vs goldens.

Exercises positional single-amount-column extraction across a MULTI-PAGE
transaction region (region.pages), with a CR-marked payment, a foreign
transaction plus a separate fee line, and year resolution from the statement
date.
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
PDF = FIXTURES / "john-lewis.pdf"


def _extract_statement():
    extractors = load_extractors([EXTRACTORS])
    with pdfplumber.open(PDF) as pdf:
        cfg = detect_bank(read_full_text(pdf), extractors)
        assert cfg is not None and cfg.name == "john-lewis"
        return extract(pdf, cfg)


def test_john_lewis_auto_detect_and_extract():
    stmt = _extract_statement()
    assert stmt.bank == "john-lewis"
    # 8 purchases/payments + the foreign purchase's separate fee row = 9.
    assert len(stmt.transactions) == 9


def test_john_lewis_multipage_region():
    # Transactions come from pages 4 and 5; the account-number tail on the
    # summary pages must not be picked up.
    stmt = _extract_statement()
    descs = [t.description for t in stmt.transactions]
    assert any("FAKE GROCER" in d for d in descs)        # page 4
    assert any("FAKE STREAMING" in d for d in descs)     # page 5


def test_john_lewis_payment_cr_negative():
    stmt = _extract_statement()
    by_desc = {t.description: t.amount for t in stmt.transactions}
    assert by_desc["PAYMENT RECEIVED - THANK YOU"] == Decimal("-100.00")


def test_john_lewis_foreign_fee_captured():
    stmt = _extract_statement()
    fee = next(t.amount for t in stmt.transactions if "NON-STERLING" in (t.description or ""))
    assert fee == Decimal("0.10")


def test_john_lewis_dates_resolved_from_statement_date():
    stmt = _extract_statement()
    by_desc = {t.description: t.date for t in stmt.transactions}
    # Statement date "06 Feb 2022": Jan -> 2022, Feb -> 2022.
    assert by_desc["FAKE GROCER STORE FAKETOWN 000"] == "2022-01-08"
    assert by_desc["FAKE STREAMING UK FAKECITY"] == "2022-02-02"


def test_john_lewis_csv_matches_golden():
    stmt = _extract_statement()
    assert to_csv(stmt) == (FIXTURES / "john-lewis.golden.csv").read_text()


def test_john_lewis_json_matches_golden():
    stmt = _extract_statement()
    assert to_json(stmt) == (FIXTURES / "john-lewis.golden.json").read_text()


def test_john_lewis_reconciles():
    r = reconcile(_extract_statement())
    assert r is not None and r.ok
