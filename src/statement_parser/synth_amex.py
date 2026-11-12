"""Generate a synthetic American Express (UK) statement PDF for testing.

Mimics the real Amex layout: two date columns (Process Date ~x14, Transaction
Date ~x58), a free-text "Transaction Details" column, an optional "Foreign
Spend" sub-amount column (~x398), and a single right-aligned "Amount £" column
(~x533) with no running balance. Entirely fake data so no real PII enters the
repo. Exercises the "positional" single-amount-column mode plus two Amex-only
wrinkles the extractor must cope with:

  - credit_markers: payments/refunds carry a "CR" marker on their own line at
    the far right; the extractor flips their sign negative.
  - amount column band: a foreign transaction adds a "Foreign Spend" sub-amount
    (left of the sterling Amount column) and an "Exchange Rate ... +Nonsterling
    Transaction Fee" line; both fall outside the 'amount' column's right-edge
    band and must be ignored, not treated as the amount.

Sign convention (so previous + sum(amounts) == closing holds): spending is
POSITIVE, credits/payments (CR) are NEGATIVE.

Run: python -m statement_parser.synth_amex out.pdf
"""

from __future__ import annotations

import sys
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PREVIOUS = Decimal("40.92")

# Each transaction: (process_date, txn_date, [detail lines], amount, is_credit, foreign)
# amount is always a positive magnitude; is_credit=True means a payment/refund
# (rendered with a trailing "CR" and treated as negative by the extractor).
# foreign, when present, is (foreign_amount_str, currency, exchange_rate, fee)
# and renders the extra sub-lines that the extractor must ignore.
TRANSACTIONS = [
    ("Apr30", "Apr30", ["PAYMENT RECEIVED - THANK YOU"], Decimal("116.24"), True, None),
    ("Apr11", "Apr11", ["FAKE MOTORS LIMITED", "FAKETOWN"], Decimal("9.43"), False, None),
    ("Apr18", "Apr18", ["FAKE SPORTS CLUB", "FAKETOWN"], Decimal("54.00"), False, None),
    ("Apr25", "Apr29", ["FAKE ONLINE STORE", "FAKECITY"], Decimal("54.35"), False, None),
    ("May3", "May4", ["FAKE LODGING * REF123", "FAKECITY"], Decimal("255.00"), False, None),
    (
        "May9",
        "May9",
        ["FAKE MEMBERSHIP UNLIM", "FAKELAND"],
        Decimal("836.43"),
        False,
        ("997.00", "UNITED STATES DOLLAR", "1.2276", "24.28"),
    ),
]


def closing_balance() -> Decimal:
    bal = PREVIOUS
    for _, _, _, amount, is_credit, _ in TRANSACTIONS:
        bal += -amount if is_credit else amount
    return bal


def new_credits() -> Decimal:
    return sum(
        (amount for _, _, _, amount, is_credit, _ in TRANSACTIONS if is_credit),
        Decimal("0"),
    )


def new_debits() -> Decimal:
    return sum(
        (amount for _, _, _, amount, is_credit, _ in TRANSACTIONS if not is_credit),
        Decimal("0"),
    )


def spend_total() -> Decimal:
    """Total new spend transactions subtotal (debits minus credits)."""
    total = Decimal("0")
    for _, _, _, amount, is_credit, _ in TRANSACTIONS:
        total += -amount if is_credit else amount
    return total


# Column x-positions mirroring the real statement.
CX_PROC = 14
CX_TXN = 58
CX_DESC = 101
CX_FOREIGN_R = 418   # right edge of the Foreign Spend sub-amount
CX_AMOUNT_R = 533    # right edge of the Amount £ column


def generate(path: str) -> None:
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    pound = "\u00a3"

    # --- Page 1: summary + metadata (header fields + detection anchors). ---
    c.setFont("Helvetica", 10)
    y = height - 60
    c.drawString(40, y, "americanexpress.co.uk")
    y -= 14
    c.drawString(40, y, "American Express Services Europe Ltd.")
    y -= 20
    c.drawString(40, y, "Prepared for Membership Number Date")
    y -= 14
    c.drawString(40, y, "MS FAKE CARDHOLDER xxxx-xxxxxx-10001 10/05/22")
    y -= 20
    c.drawString(40, y, "Account Summary")
    y -= 14
    c.drawString(40, y, "Previous Balance New Credits New Debits Closing Balance")
    y -= 14
    c.drawString(
        40,
        y,
        f"{pound}{PREVIOUS:,.2f} - {pound}{new_credits():,.2f} "
        f"+ {pound}{new_debits():,.2f} = {pound}{closing_balance():,.2f}",
    )
    y -= 20
    c.drawString(40, y, "Statement Period From 11April to10May2022")
    c.showPage()

    # --- Page 2: the transaction table. ---
    c.setFont("Helvetica", 10)
    y = height - 80
    c.drawString(40, y, "MS FAKE CARDHOLDER xxxx-xxxxxx-10001 10/05/22")
    y -= 30

    # Section + column header.
    c.drawString(CX_PROC, y, "Transaction Process")
    y -= 14
    c.drawString(CX_PROC, y, "Date")
    c.drawString(CX_TXN, y, "Date")
    c.drawString(CX_DESC, y, "Transaction Details")
    c.drawRightString(CX_FOREIGN_R, y, "Foreign Spend")
    c.drawRightString(CX_AMOUNT_R, y, "Amount £")
    y -= 20

    c.setFont("Helvetica", 9)
    for proc, txn, detail_lines, amount, is_credit, foreign in TRANSACTIONS:
        # First line carries the dates + first detail line + amount.
        c.drawString(CX_PROC, y, proc)
        c.drawString(CX_TXN, y, txn)
        c.drawString(CX_DESC, y, detail_lines[0])
        c.drawRightString(CX_AMOUNT_R, y, f"{amount:,.2f}")
        y -= 12
        # "CR" marker drops onto the next line at the far right for credits.
        if is_credit:
            c.drawRightString(CX_AMOUNT_R, y, "CR")
            y -= 7
        # Remaining detail lines (wrapped description).
        for line in detail_lines[1:]:
            c.drawString(CX_DESC, y, line)
            y -= 12
        # Foreign-transaction sub-lines: foreign amount, currency, exchange
        # rate + non-sterling fee. All must be IGNORED by the extractor.
        if foreign is not None:
            f_amount, currency, rate, fee = foreign
            c.drawRightString(CX_FOREIGN_R, y, f_amount)
            y -= 8
            c.drawRightString(CX_FOREIGN_R, y, currency)
            y -= 12
            c.drawString(
                CX_DESC,
                y,
                f"Exchange Rate {rate} +Nonsterling Transaction Fee {fee}",
            )
            y -= 12
        y -= 4

    # Per-cardmember subtotal row (must be skipped).
    c.drawString(CX_PROC, y, f"Total new spend transactions for MS FAKE CARDHOLDER")
    c.drawRightString(CX_AMOUNT_R, y, f"{spend_total():,.2f}")

    c.showPage()
    c.save()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m statement_parser.synth_amex OUT.pdf", file=sys.stderr)
        return 1
    generate(argv[0])
    print(f"wrote {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
