"""Generate a synthetic bank-statement PDF for testing.

Produces a fake statement that mimics a real layout (header fields + a ruled
transaction table) using entirely made-up data. Used to create committed test
fixtures without any real PII.

Run: python -m statement_parser.synth_acme out.pdf
"""

from __future__ import annotations

import sys
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# Fake, deterministic data. opening + sum(amounts) must equal closing so the
# reconciliation check passes on this fixture.
OPENING = Decimal("1000.00")
TRANSACTIONS = [
    # (date, description, amount)  amount negative = debit
    ("01/02/2024", "OPENING DEPOSIT", Decimal("500.00")),
    ("03/02/2024", "COFFEE SHOP", Decimal("-4.50")),
    ("05/02/2024", "SALARY ACME CORP", Decimal("2500.00")),
    ("09/02/2024", "GROCERIES", Decimal("-73.21")),
    ("14/02/2024", "RENT PAYMENT", Decimal("-1200.00")),
    ("20/02/2024", "REFUND ONLINE STORE", Decimal("18.99")),
]


def _rows_with_balance() -> list[tuple[str, str, str, str]]:
    rows = []
    balance = OPENING
    for date, desc, amount in TRANSACTIONS:
        balance += amount
        amt_str = f"{amount:,.2f}" if amount >= 0 else f"({abs(amount):,.2f})"
        rows.append((date, desc, amt_str, f"{balance:,.2f}"))
    return rows


def closing_balance() -> Decimal:
    balance = OPENING
    for _, _, amount in TRANSACTIONS:
        balance += amount
    return balance


def generate(path: str) -> None:
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    # Header / statement-level fields.
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, height - 25 * mm, "ACME BANK")
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, height - 33 * mm, "Account Number: 12-3456-7890123-00")
    c.drawString(20 * mm, height - 39 * mm, "Statement Period: 01 Feb 2024 to 29 Feb 2024")
    c.drawString(20 * mm, height - 45 * mm, f"Opening Balance: {OPENING:,.2f}")
    c.drawString(20 * mm, height - 51 * mm, f"Closing Balance: {closing_balance():,.2f}")

    # Transaction table with ruled grid lines.
    rows = _rows_with_balance()
    headers = ["Date", "Description", "Amount", "Balance"]
    col_x = [20 * mm, 45 * mm, 120 * mm, 150 * mm, 180 * mm]  # column boundaries
    top = height - 65 * mm
    row_h = 8 * mm

    c.setLineWidth(0.5)
    # Horizontal lines.
    n_rows = len(rows) + 1  # + header
    for i in range(n_rows + 1):
        y = top - i * row_h
        c.line(col_x[0], y, col_x[-1], y)
    # Vertical lines.
    for x in col_x:
        c.line(x, top, x, top - n_rows * row_h)

    # Header cells.
    c.setFont("Helvetica-Bold", 9)
    for i, h in enumerate(headers):
        c.drawString(col_x[i] + 2 * mm, top - row_h + 2.5 * mm, h)

    # Data cells.
    c.setFont("Helvetica", 9)
    for r, row in enumerate(rows, start=1):
        y = top - (r + 1) * row_h + 2.5 * mm
        for i, cell in enumerate(row):
            c.drawString(col_x[i] + 2 * mm, y, cell)

    c.showPage()
    c.save()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m statement_parser.synth_acme OUT.pdf", file=sys.stderr)
        return 1
    generate(argv[0])
    print(f"wrote {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
