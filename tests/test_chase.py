"""Integration test: parse the synthetic Chase (lines-mode) fixture vs goldens."""

from pathlib import Path

import pdfplumber

from statement_parser.config import detect_bank, load_extractors
from statement_parser.extract import extract, read_full_text
from statement_parser.output import to_csv, to_json
from statement_parser.reconcile import reconcile

FIXTURES = Path(__file__).parent / "fixtures"
EXTRACTORS = Path(__file__).parents[1] / "extractors"
PDF = FIXTURES / "chase-uk.pdf"


def _extract_statement():
    extractors = load_extractors([EXTRACTORS])
    with pdfplumber.open(PDF) as pdf:
        cfg = detect_bank(read_full_text(pdf), extractors)
        assert cfg is not None and cfg.name == "chase-uk"
        return extract(pdf, cfg)


def test_lines_mode_auto_detect_and_extract():
    stmt = _extract_statement()
    assert stmt.bank == "chase-uk"
    # 10 transactions; wrapped "Transfer"/"Interest" sub-lines are skipped.
    assert len(stmt.transactions) == 10
    assert stmt.fields["opening_balance"] is not None
    assert stmt.fields["closing_balance"] is not None


def test_lines_mode_csv_matches_golden():
    stmt = _extract_statement()
    golden = (FIXTURES / "chase-uk.golden.csv").read_text()
    assert to_csv(stmt) == golden


def test_lines_mode_json_matches_golden():
    stmt = _extract_statement()
    golden = (FIXTURES / "chase-uk.golden.json").read_text()
    assert to_json(stmt) == golden


def test_lines_mode_reconciles():
    r = reconcile(_extract_statement())
    assert r is not None and r.ok
