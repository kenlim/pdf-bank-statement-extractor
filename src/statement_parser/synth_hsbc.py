"""Generate a synthetic HSBC-Advance-style statement PDF for testing.

Mimics the real layout: three amount columns (Paid out / Paid in / Balance) with
no grid lines, multi-line descriptions, dates that group transactions, and
brought/carried-forward balance rows. Entirely fake data so no real PII enters
the repo. Exercises the "positional" extraction mode.

Run: python -m statement_parser.synth_hsbc out.pdf
"""

from __future__ import annotations

import sys
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

OPENING = Decimal("1000.00")

# Each transaction: (date_or_None, [description lines], paid_out, paid_in, show_balance)
# date_or_None: a new date starts a group; None continues the current date.
TRANSACTIONS = [
    ("01 Jan 99", ["CR SALARY", "ACME CORP"], None, Decimal("2000.00"), False),
    (None, ["DD RENT", "LANDLORD LTD"], Decimal("1200.00"), None, True),  # bal 1800
    ("02 Jan 99", ["BP COFFEE SHOP", "Latte"], Decimal("4.50"), None, False),
    (None, ["DD UTILITIES"], Decimal("95.50"), None, True),  # bal 1700
    ("05 Jan 99", ["CR REFUND", "ONLINE STORE"], None, Decimal("20.00"), True),  # bal 1720
    ("08 Jan 99", ["BP GROCERIES"], Decimal("73.21"), None, True),  # bal 1646.79
]


def _column_x():
    # Right edges chosen to fall into the extractor's classification bands:
    # paid_out x1 <= 410, paid_in x1 <= 495, balance otherwise.
    return {"date": 53, "desc": 117, "paid_out": 390, "paid_in": 470, "balance": 550}


def closing_balance() -> Decimal:
    bal = OPENING
    for _, _, out, inn, _ in TRANSACTIONS:
        if out:
            bal -= out
        if inn:
            bal += inn
    return bal


def generate(path: str) -> None:
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    pound = "\u00a3"
    cx = _column_x()

    # Summary block + metadata (page 1 header).
    c.setFont("Helvetica", 10)
    y = height - 30 * mm
    c.drawString(40, y, "Your Statement")
    y -= 16
    c.drawString(40, y, "Account Summary")
    y -= 14
    c.drawString(40, y, f"OpeningBalance {pound}{OPENING:,.2f}")
    y -= 12
    c.drawString(40, y, f"ClosingBalance {pound}{closing_balance():,.2f}")
    y -= 14
    c.drawString(40, y, "01 January to 31 January 2099")
    y -= 12
    # HSBC signature strings for auto-detection.
    c.drawString(40, y, "Bank Identifier Code HBUKGB4141D")
    y -= 14
    c.drawString(40, y, "Your HSBC Advance details")
    y -= 18

    # Column header row.
    c.setFont("Helvetica-Bold", 9)
    c.drawString(cx["date"], y, "Date")
    c.drawString(cx["desc"], y, "Payment type and details")
    c.drawRightString(cx["paid_out"], y, f"{pound}Paid out")
    c.drawRightString(cx["paid_in"], y, f"{pound}Paid in")
    c.drawRightString(cx["balance"], y, f"{pound}Balance")
    y -= 16

    c.setFont("Helvetica", 9)
    # Brought-forward row.
    c.drawString(cx["date"], y, "01 Jan 99")
    c.drawString(cx["desc"], y, "BALANCEBROUGHTFORWARD")
    c.drawRightString(cx["balance"], y, f"{OPENING:,.2f}")
    y -= 14

    # Precompute running balance per transaction.
    running = OPENING
    for date, desc_lines, out, inn, show_bal in TRANSACTIONS:
        if out:
            running -= out
        if inn:
            running += inn
        row_balance = running
        for i, line in enumerate(desc_lines):
            if i == 0 and date:
                c.drawString(cx["date"], y, date)
            c.drawString(cx["desc"], y, line)
            if i == len(desc_lines) - 1:  # amounts land on the last desc line
                if out:
                    c.drawRightString(cx["paid_out"], y, f"{out:,.2f}")
                if inn:
                    c.drawRightString(cx["paid_in"], y, f"{inn:,.2f}")
                if show_bal:
                    c.drawRightString(cx["balance"], y, f"{row_balance:,.2f}")
            y -= 14
        y -= 2

    # Carried-forward row.
    c.drawString(cx["desc"], y, "BALANCECARRIEDFORWARD")
    c.drawRightString(cx["balance"], y, f"{closing_balance():,.2f}")

    c.showPage()
    c.save()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m statement_parser.synth_hsbc OUT.pdf", file=sys.stderr)
        return 1
    generate(argv[0])
    print(f"wrote {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
