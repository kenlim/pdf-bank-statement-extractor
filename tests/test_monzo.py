"""Integration test: parse the synthetic Monzo (positional single-amount column)."""

from pathlib import Path

import pdfplumber

from statement_parser.config import detect_bank, load_extractors
from statement_parser.extract import extract, read_full_text
from statement_parser.output import to_csv, to_json

FIXTURES = Path(__file__).parent / "fixtures"
EXTRACTORS = Path(__file__).parents[1] / "extractors"
PDF = FIXTURES / "monzo.pdf"


def _extract_statement():
    extractors = load_extractors([EXTRACTORS])
    with pdfplumber.open(PDF) as pdf:
        cfg = detect_bank(read_full_text(pdf), extractors)
        assert cfg is not None and cfg.name == "monzo"
        return extract(pdf, cfg)


def test_monzo_auto_detect_and_extract():
    stmt = _extract_statement()
    assert stmt.bank == "monzo"
    assert len(stmt.transactions) == 4


def test_monzo_signed_amounts():
    stmt = _extract_statement()
    by_desc = {t.description: t.amount for t in stmt.transactions}
    assert by_desc["Coffee Shop"] < 0           # debit
    assert by_desc["TFL Travel"] < 0            # debit
    assert by_desc["Salary ACME"] > 0           # credit
    assert by_desc["Jane Doe (P2P Payment)"] > 0  # credit, desc has parentheses


def test_monzo_fields():
    stmt = _extract_statement()
    assert stmt.fields["account_number"] == "25384833"
    assert stmt.fields["sort_code"] == "04-00-04"


def test_monzo_csv_matches_golden():
    stmt = _extract_statement()
    golden = (FIXTURES / "monzo.golden.csv").read_text()
    assert to_csv(stmt) == golden


def test_monzo_json_matches_golden():
    stmt = _extract_statement()
    golden = (FIXTURES / "monzo.golden.json").read_text()
    assert to_json(stmt) == golden
