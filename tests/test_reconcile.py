"""Unit tests for balance reconciliation."""

from decimal import Decimal

from statement_parser.models import Statement, Transaction
from statement_parser.reconcile import reconcile


def _stmt(opening, closing, amounts):
    return Statement(
        bank="test",
        fields={"opening_balance": opening, "closing_balance": closing},
        transactions=[
            Transaction(date=None, description=None, amount=a, balance=None)
            for a in amounts
        ],
    )


def test_reconcile_ok():
    s = _stmt(Decimal("1000"), Decimal("1100"), [Decimal("200"), Decimal("-100")])
    r = reconcile(s)
    assert r is not None and r.ok
    assert r.difference == Decimal("0")


def test_reconcile_mismatch():
    s = _stmt(Decimal("1000"), Decimal("1200"), [Decimal("200"), Decimal("-100")])
    r = reconcile(s)
    assert r is not None and not r.ok
    assert r.difference == Decimal("-100")


def test_reconcile_skipped_without_balances():
    s = Statement(bank="test", fields={}, transactions=[])
    assert reconcile(s) is None


def test_reconcile_ignores_none_amounts():
    s = _stmt(Decimal("1000"), Decimal("1000"), [None, Decimal("0")])
    r = reconcile(s)
    assert r is not None and r.ok
