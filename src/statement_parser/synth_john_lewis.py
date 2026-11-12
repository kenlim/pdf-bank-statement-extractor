"""Generate a synthetic John Lewis Partnership Card statement PDF for testing.

Mimics the real layout: space-separated columns (Spend date | Date processed |
Card ending | Transaction details | Amount £) spread across multiple pages with
a repeating column header and no running balance. Entirely fake data so no real
PII enters the repo. Exercises "positional" single signed-amount-column mode
plus John Lewis wrinkles:

  - multi-page transaction region (region.pages);
  - a payment with a trailing "CR" marker (flipped negative via credit_markers);
  - a foreign transaction with a separate fee: the purchase row carries its
    sterling Amount, a conversion sub-line ("5.00 USD @ 1.3699", no amount)
    follows, then a separate charged "NON-STERLING TRANSACTION FEE" line.

Sign convention (so previous + sum(amounts) == closing): spending POSITIVE,
payments (CR) NEGATIVE.

Run: python -m statement_parser.synth_john_lewis out.pdf
"""

from __future__ import annotations

import sys
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PREVIOUS = Decimal("300.00")
CARD = "0000"

# Each: (spend_date, processed_date, [detail lines], amount, is_credit, foreign)
# amount: positive magnitude; is_credit=True renders a trailing "CR" and is
# treated negative. foreign, when set, is (conversion_line, fee_amount) and
# renders the conversion sub-line (no amount) + a separate fee line.
TRANSACTIONS = [
    ("08 Jan", "10 Jan", ["FAKE GROCER STORE FAKETOWN 000"], Decimal("8.27"), False, None),
    ("09 Jan", "10 Jan", ["FAKE GADGET SHOP 00000000000"], Decimal("44.99"), False, None),
    ("10 Jan", "11 Jan", ["FAKE MARKETPLACE fake.example"], Decimal("23.18"), False, None),
    (
        "14 Jan",
        "15 Jan",
        ["FAKE CLOUD SVCS FAKELAND"],
        Decimal("3.65"),
        False,
        ("5.00 USD @ 1.3699", Decimal("0.10")),
    ),
    ("16 Jan", "17 Jan", ["FAKE DEPT STORE FAKETOWN"], Decimal("30.80"), False, None),
    ("27 Jan", "28 Jan", ["PAYMENT RECEIVED - THANK YOU"], Decimal("100.00"), True, None),
    ("31 Jan", "01 Feb", ["FAKE RESTAURANT FAKECITY"], Decimal("52.20"), False, None),
    ("02 Feb", "02 Feb", ["FAKE STREAMING UK FAKECITY"], Decimal("9.99"), False, None),
]


def closing_balance() -> Decimal:
    bal = PREVIOUS
    for _, _, _, amount, is_credit, foreign in TRANSACTIONS:
        bal += -amount if is_credit else amount
        if foreign is not None:
            bal += foreign[1]  # separate fee is an additional charge
    return bal


# Column x-positions mirroring the real statement.
CX_SPEND = 42
CX_PROC = 120
CX_CARD = 210
CX_DESC = 270
CX_AMOUNT_R = 546   # right edge of the Amount £ column
CX_CR = 552         # "CR" marker sits just right of the amount

ROWS_PER_PAGE = 4


def _header(c, y, pound):
    c.setFont("Helvetica", 10)
    c.drawString(40, y, "PARTNERSHIP CARD")
    y -= 14
    c.drawString(40, y, "Account number 0000 0000 0000 0000 06 Feb 2022")
    y -= 20
    c.setFont("Helvetica-Bold", 9)
    c.drawString(CX_SPEND, y, "Spend date")
    c.drawString(CX_PROC, y, "Date processed")
    c.drawString(CX_CARD, y, "Card ending")
    c.drawString(CX_DESC, y, "Transaction details")
    c.drawRightString(CX_AMOUNT_R, y, "Amount £")
    y -= 18
    c.setFont("Helvetica", 9)
    return y


def generate(path: str) -> None:
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    pound = "\u00a3"

    # --- Page 1: summary + metadata (header fields + detection anchors). ---
    c.setFont("Helvetica", 10)
    y = height - 60
    c.drawString(40, y, "Partnership Card")
    y -= 14
    c.drawString(40, y, "Online johnlewisfinance.com")
    y -= 14
    c.drawString(40, y, "Statement date 06 Feb 2022")
    y -= 20
    c.drawString(40, y, "Partnership Card account summary")
    y -= 14
    c.drawString(40, y, f"Previous balance {pound}{PREVIOUS:,.2f}")
    y -= 14
    c.drawString(40, y, f"Your new balance {pound}{closing_balance():,.2f}")
    c.showPage()

    # --- Pages 2-3: boilerplate to mirror the real page count. ---
    for _ in range(2):
        c.setFont("Helvetica", 9)
        c.drawString(40, height - 60, "Summary box / interest rates (boilerplate)")
        c.showPage()

    # --- Pages 4-5: the transaction table. ---
    # Lay rows across two pages with a repeating header.
    pages = [TRANSACTIONS[i : i + ROWS_PER_PAGE] for i in range(0, len(TRANSACTIONS), ROWS_PER_PAGE)]
    for page_rows in pages:
        y = _header(c, height - 60, pound)
        for spend, proc, detail_lines, amount, is_credit, foreign in page_rows:
            c.drawString(CX_SPEND, y, spend)
            c.drawString(CX_PROC, y, proc)
            c.drawString(CX_CARD, y, CARD)
            c.drawString(CX_DESC, y, detail_lines[0])
            c.drawRightString(CX_AMOUNT_R, y, f"{amount:,.2f}")
            if is_credit:
                c.drawString(CX_CR, y, "CR")
            y -= 14
            for line in detail_lines[1:]:
                c.drawString(CX_DESC, y, line)
                y -= 14
            if foreign is not None:
                conv_line, fee = foreign
                # Conversion detail (no amount).
                c.drawString(CX_DESC, y, conv_line)
                y -= 14
                # Separate charged fee line with its own processed date.
                c.drawString(CX_PROC, y, proc)
                c.drawString(CX_DESC, y, "NON-STERLING TRANSACTION FEE")
                c.drawRightString(CX_AMOUNT_R, y, f"{fee:,.2f}")
                y -= 14
        c.showPage()

    c.save()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m statement_parser.synth_john_lewis OUT.pdf", file=sys.stderr)
        return 1
    generate(argv[0])
    print(f"wrote {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
