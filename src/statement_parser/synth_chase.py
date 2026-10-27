"""Generate a synthetic Chase-UK-style statement PDF for testing.

Mimics the real layout (whitespace-aligned, no grid lines, wrapped description
sub-labels, multi-page) with entirely fake data. Used for committed fixtures so
no real PII enters the repo. Exercises the "lines" extraction mode with a mix
of debits (-£) and a credit (+£, money in that raises the balance), thousands
separators, a no-amount "Opening balance" row (skipped), and pagination.

Run: python -m statement_parser.synth_chase out.pdf
"""

from __future__ import annotations

import sys
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OPENING = Decimal("1000.00")
# (date, description, amount, sub_label)
#   amount: signed; negative = debit (money out), positive = credit (money in).
#   sub_label: a wrapped second line (skipped by the parser), as Chase prints.
TRANSACTIONS = [
    ("01 Aug 2099", "Round up", Decimal("-0.20"), "Transfer"),
    ("01 Aug 2099", "Fake Cafe", Decimal("-26.50"), "Purchase"),
    ("02 Aug 2099", "Fake Streaming", Decimal("-12.99"), "Purchase"),
    ("02 Aug 2099", "Fake Supermarket", Decimal("-66.35"), "Purchase"),
    ("03 Aug 2099", "Round up", Decimal("-0.40"), "Transfer"),
    ("03 Aug 2099", "To Fake Savings - Saving", Decimal("-250.00"), "Transfer"),
    ("10 Aug 2099", "From Fake Employer - Salary", Decimal("1500.00"), "Transfer"),
    ("15 Aug 2099", "Fake Marketplace", Decimal("-34.98"), "Purchase"),
    ("20 Aug 2099", "Round up", Decimal("-0.80"), "Transfer"),
    ("28 Aug 2099", "Fake Restaurant", Decimal("-59.49"), "Purchase"),
    ("31 Aug 2099", "Round up", Decimal("-0.25"), "Transfer"),
]


def closing_balance() -> Decimal:
    bal = OPENING
    for _, _, amt, _ in TRANSACTIONS:
        bal += amt
    return bal


def money_in() -> Decimal:
    return sum((amt for _, _, amt, _ in TRANSACTIONS if amt > 0), Decimal("0"))


def money_out() -> Decimal:
    return sum((-amt for _, _, amt, _ in TRANSACTIONS if amt < 0), Decimal("0"))


def generate(path: str) -> None:
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    pound = "\u00a3"
    minus = "\u2212"  # U+2212 minus sign, as Chase uses in the summary row

    def header(page_first: bool, y_start: float) -> float:
        y = y_start
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Fake's Account statement")
        y -= 14
        c.setFont("Helvetica", 10)
        c.drawString(40, y, "01 August 2099 - 31 August 2099")
        y -= 24
        if page_first:
            # Summary block.
            c.setFont("Helvetica", 9)
            c.drawString(40, y, "Opening balance Money in Money out Closing balance")
            y -= 12
            c.drawString(40, y, f"+ {minus} =")
            y -= 12
            c.drawString(
                40,
                y,
                f"{pound}{OPENING:,.2f} {pound}{money_in():,.2f} "
                f"{pound}{money_out():,.2f} {pound}{closing_balance():,.2f}",
            )
            y -= 24
        # Column header row.
        c.setFont("Helvetica-Bold", 9)
        c.drawString(40, y, "Date")
        c.drawString(140, y, "Transaction details")
        c.drawString(430, y, "Amount")
        c.drawString(510, y, "Balance")
        y -= 18
        # A no-amount "Opening balance" row (skipped: no amount column match).
        if page_first:
            c.setFont("Helvetica", 9)
            c.drawString(40, y, "01 Aug 2099")
            c.drawString(140, y, "Opening balance")
            c.drawRightString(556, y, f"{pound}{OPENING:,.2f}")
            y -= 16
        return y

    # Precompute rows with running balance and signed amount strings.
    pound_rows = []
    bal = OPENING
    for date, desc, amt, sub in TRANSACTIONS:
        bal += amt
        if amt < 0:
            amt_str = f"-{pound}{abs(amt):,.2f}"
        else:
            amt_str = f"+{pound}{amt:,.2f}"
        pound_rows.append((date, desc, amt_str, f"{pound}{bal:,.2f}", sub))

    per_page = 4
    pages = [pound_rows[i : i + per_page] for i in range(0, len(pound_rows), per_page)]
    total_pages = len(pages)

    for pidx, page_rows in enumerate(pages):
        y = header(pidx == 0, height - 30)
        c.setFont("Helvetica", 9)
        for date, desc, amt_str, bal_s, sub in page_rows:
            c.drawString(40, y, date)
            c.drawString(140, y, desc)
            c.drawRightString(476, y, amt_str)
            c.drawRightString(556, y, bal_s)
            y -= 12
            # Wrapped sub-label on its own line (should be skipped by the parser).
            c.drawString(140, y, sub)
            y -= 16
        c.setFont("Helvetica", 8)
        c.drawString(40, 30, f"Page {pidx + 1} of {total_pages}")
        c.setFont("Helvetica", 7)
        c.drawString(
            40,
            18,
            "Chase is a registered trademark and trading name of J.P. Morgan Europe Limited.",
        )
        c.showPage()

    c.save()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m statement_parser.synth_chase OUT.pdf", file=sys.stderr)
        return 1
    generate(argv[0])
    print(f"wrote {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
