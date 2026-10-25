"""Generate a synthetic Monzo-style statement PDF for testing.

Mimics the Monzo layout: a single signed Amount column plus a running Balance,
DD/MM/YYYY dates, and the summary/metadata block. Entirely fake data. Exercises
the "lines" extraction mode with negative amounts (debits).

Run: python -m statement_parser.synth_monzo out.pdf
"""

from __future__ import annotations

import sys
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Rows are listed newest-first (as Monzo does). Each: (date, description, amount).
# amount negative = debit. Balance is computed newest-first from CLOSING down.
CLOSING = Decimal("200.00")
ROWS_NEWEST_FIRST = [
    ("15/02/2099", "Coffee Shop", Decimal("-4.50")),
    ("12/02/2099", "Jane Doe (P2P Payment)", Decimal("50.00")),
    ("10/02/2099", "TFL Travel", Decimal("-12.80")),
    ("05/02/2099", "Salary ACME", Decimal("100.00")),
]


def _rows_with_balance():
    """Attach the running balance shown on each row (newest-first)."""
    out = []
    bal = CLOSING
    for date, desc, amt in ROWS_NEWEST_FIRST:
        out.append((date, desc, amt, bal))
        bal -= amt  # walking backwards in time
    return out


def generate(path: str) -> None:
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    pound = "\u00a3"

    c.setFont("Helvetica", 10)
    y = height - 60
    c.drawString(40, y, "Personal Account statement")
    y -= 14
    c.drawString(40, y, "01/02/2099 - 28/02/2099")
    y -= 14
    c.drawString(40, y, f"Jane Smith {pound}{CLOSING:,.2f}")
    y -= 12
    c.drawString(40, y, "Personal Account balance")
    y -= 16
    # Monzo detection + metadata strings.
    c.drawString(40, y, "Sort code: 04-00-04")
    y -= 12
    c.drawString(40, y, "Account number: 25384833")
    y -= 12
    c.drawString(40, y, "BIC: MONZGB2L")
    y -= 12
    c.drawString(40, y, "Monzo Bank Limited is a company registered in England.")
    y -= 20

    # Table header.
    c.setFont("Helvetica-Bold", 9)
    c.drawString(70, y, "Date")
    c.drawString(153, y, "Description")
    c.drawRightString(441, y, "Amount (GBP)")
    c.drawRightString(524, y, "Balance")
    y -= 16

    c.setFont("Helvetica", 9)
    for date, desc, amt, bal in _rows_with_balance():
        c.drawString(70, y, date)
        c.drawString(153, y, desc)
        c.drawRightString(441, y, f"{amt:,.2f}")
        c.drawRightString(524, y, f"{bal:,.2f}")
        y -= 14

    c.showPage()
    c.save()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m statement_parser.synth_monzo OUT.pdf", file=sys.stderr)
        return 1
    generate(argv[0])
    print(f"wrote {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
