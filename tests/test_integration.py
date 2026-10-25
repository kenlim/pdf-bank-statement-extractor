"""Integration test: parse the synthetic Acme fixture and compare to goldens."""

from pathlib import Path

import pdfplumber
import pytest

from statement_parser.cli import main
from statement_parser.config import detect_bank, load_extractors
from statement_parser.extract import extract, read_full_text
from statement_parser.output import to_csv, to_json

FIXTURES = Path(__file__).parent / "fixtures"
EXTRACTORS = Path(__file__).parents[1] / "extractors"
PDF = FIXTURES / "acme-bank.pdf"


def _extract_statement():
    extractors = load_extractors([EXTRACTORS])
    with pdfplumber.open(PDF) as pdf:
        cfg = detect_bank(read_full_text(pdf), extractors)
        assert cfg is not None and cfg.name == "acme-bank"
        return extract(pdf, cfg)


def test_auto_detect_and_extract():
    stmt = _extract_statement()
    assert stmt.bank == "acme-bank"
    assert len(stmt.transactions) == 6
    assert stmt.fields["account_number"] == "12-3456-7890123-00"


def test_csv_matches_golden():
    stmt = _extract_statement()
    golden = (FIXTURES / "acme-bank.golden.csv").read_text()
    assert to_csv(stmt) == golden


def test_json_matches_golden():
    stmt = _extract_statement()
    golden = (FIXTURES / "acme-bank.golden.json").read_text()
    assert to_json(stmt) == golden


def test_reconciliation_passes_on_fixture():
    # The fixture is constructed so opening + sum(amounts) == closing.
    from statement_parser.reconcile import reconcile

    r = reconcile(_extract_statement())
    assert r is not None and r.ok


def test_cli_no_match_exits_2(tmp_path, capsys):
    from reportlab.pdfgen import canvas

    p = tmp_path / "unknown.pdf"
    c = canvas.Canvas(str(p))
    c.drawString(50, 50, "UNKNOWN INSTITUTION")
    c.showPage()
    c.save()

    code = main([str(p), "--config-dir", str(EXTRACTORS)])
    assert code == 2
    err = capsys.readouterr().err
    assert "no extractor matched" in err


def test_cli_csv_output(capsys):
    code = main([str(PDF)])
    assert code == 0
    out = capsys.readouterr().out
    assert out.startswith("date,description,amount,balance")
