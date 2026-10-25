"""Render a Statement as CSV or JSON."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from .models import Statement


def to_csv(statement: Statement) -> str:
    """Render the transaction ledger as CSV (one row per transaction)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["date", "description", "amount", "balance"])
    for t in statement.transactions:
        writer.writerow(
            [
                t.date or "",
                t.description or "",
                "" if t.amount is None else str(t.amount),
                "" if t.balance is None else str(t.balance),
            ]
        )
    return out.getvalue()


def to_json(statement: Statement) -> str:
    """Render the full statement (fields + transactions) as pretty JSON."""
    def default(o: Any) -> Any:
        raise TypeError(f"not JSON serializable: {type(o)}")

    return json.dumps(statement.as_dict(), indent=2, default=default)
