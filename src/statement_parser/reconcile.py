"""Balance reconciliation: opening + sum(amounts) should equal closing."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .models import Statement


@dataclass
class ReconResult:
    ok: bool
    opening: Optional[Decimal]
    closing: Optional[Decimal]
    total: Decimal
    expected_closing: Optional[Decimal]
    difference: Optional[Decimal]
    message: str


def reconcile(statement: Statement) -> Optional[ReconResult]:
    """Check opening + sum(amounts) == closing.

    Returns None when opening or closing balance is unavailable (nothing to
    check). Otherwise returns a ReconResult with ok=True/False.
    """
    opening = statement.fields.get("opening_balance")
    closing = statement.fields.get("closing_balance")
    if not isinstance(opening, Decimal) or not isinstance(closing, Decimal):
        return None

    total = Decimal("0")
    for t in statement.transactions:
        if t.amount is not None:
            total += t.amount

    expected = opening + total
    difference = expected - closing
    ok = difference == 0

    if ok:
        message = (
            f"reconciled: opening {opening} + transactions {total} = closing {closing}"
        )
    else:
        message = (
            f"reconciliation mismatch: opening {opening} + transactions {total} "
            f"= {expected}, but closing balance is {closing} (off by {difference})"
        )

    return ReconResult(
        ok=ok,
        opening=opening,
        closing=closing,
        total=total,
        expected_closing=expected,
        difference=difference,
        message=message,
    )
