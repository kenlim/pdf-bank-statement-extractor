"""Integration test: parse the synthetic HSBC (positional-mode) fixture."""

from pathlib import Path

import pdfplumber

from statement_parser.config import detect_bank, load_extractors
from statement_parser.extract import extract, read_full_text
from statement_parser.output import to_csv, to_json
from statement_parser.reconcile import reconcile

FIXTURES = Path(__file__).parent / "fixtures"
EXTRACTORS = Path(__file__).parents[1] / "extractors"
PDF = FIXTURES / "hsbc-advance.pdf"


def _extract_statement():
    extractors = load_extractors([EXTRACTORS])
    with pdfplumber.open(PDF) as pdf:
        cfg = detect_bank(read_full_text(pdf), extractors)
        assert cfg is not None and cfg.name == "hsbc-advance"
        return extract(pdf, cfg)


def test_positional_auto_detect_and_extract():
    stmt = _extract_statement()
    assert stmt.bank == "hsbc-advance"
    # 6 transactions; brought/carried-forward rows are skipped.
    assert len(stmt.transactions) == 6


def test_positional_debit_credit_signs():
    stmt = _extract_statement()
    by_desc = {t.description: t.amount for t in stmt.transactions}
    # Paid-in column -> positive; paid-out column -> negative.
    assert by_desc["CR SALARY ACME CORP"] > 0
    assert by_desc["DD RENT LANDLORD LTD"] < 0
    assert by_desc["BP GROCERIES"] < 0


def test_positional_multiline_descriptions_joined():
    stmt = _extract_statement()
    descs = {t.description for t in stmt.transactions}
    assert "CR SALARY ACME CORP" in descs  # two lines joined
    assert "DD RENT LANDLORD LTD" in descs


def test_positional_csv_matches_golden():
    stmt = _extract_statement()
    golden = (FIXTURES / "hsbc-advance.golden.csv").read_text()
    assert to_csv(stmt) == golden


def test_positional_json_matches_golden():
    stmt = _extract_statement()
    golden = (FIXTURES / "hsbc-advance.golden.json").read_text()
    assert to_json(stmt) == golden


def test_positional_reconciles():
    r = reconcile(_extract_statement())
    assert r is not None and r.ok
