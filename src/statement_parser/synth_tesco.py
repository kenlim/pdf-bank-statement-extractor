"""Generate a synthetic Tesco Bank Clubcard statement PDF for testing.

Mimics the real Tesco layout: a single-page, column-aligned transaction table
(Trans Date | Post Date | ref no. | Transaction details | Amount £) bounded by
"BALANCE FROM PREVIOUS STATEMENT" / "NEW BALANCE" markers, with no running
balance. Entirely fake data so no real PII enters the repo. Exercises the
"positional" single signed-amount-column mode plus Tesco-only wrinkles:

  - a payment shown with a leading minus ("-£791.02") and a refund ("-£5.40");
  - a foreign transaction with FEE: the purchase line has no amount, its
    converted sterling Amount lands on the next line beside the conversion
    detail, and a separate charged fee line follows. The converted amount
    prints with an OCR quirk ("£1.182.62" meaning 1,182.62), handled by
    normalization.collapse_extra_decimals.

Sign convention (so previous + sum(amounts) == closing): spending POSITIVE,
payments/refunds NEGATIVE (leading minus in the Amount column).

Run: python -m statement_parser.synth_tesco out.pdf
"""

from __future__ import annotations

import sys
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PREVIOUS = Decimal("500.00")

# Each transaction: (trans_date, post_date, ref, [detail lines], amount, foreign)
# amount: signed magnitude (negative = payment/refund). foreign, when set, is
# (converted_amount_str_with_ocr_dots, fee_amount) and renders the conversion
# sub-line + a separate fee line; the row's own `amount` is then the converted
# sterling value parsed from converted_amount_str.
TRANSACTIONS = [
    ("15DEC", "17DEC", "10000001", ["FAKE GROCER STORE FAKETOWN"], Decimal("11.40"), None),
    ("17DEC", "20DEC", "10000002", ["FAKE COUNCIL FAKETOWN GB"], Decimal("2.00"), None),
    ("26DEC", "27DEC", "10000003", ["FAKE STORE REFUND FAKETOWN GB"], Decimal("-5.40"), None),
    ("29DEC", "30DEC", "10000004", ["FAKE CLINIC FAKECITY E1"], Decimal("240.00"), None),
    ("03JAN", "04JAN", "10000005", ["FASTERPAYMENT-THANKYOU"], Decimal("-791.02"), None),
    (
        "08JAN",
        "10JAN",
        "10000006",
        ["FAKE TUITION FAKELAND"],
        Decimal("1182.62"),
        # converted sterling amount (OCR double-dot), separate fee
        ("1,599.00USDEXCHANGERATE1.352", "£1.182.62", Decimal("32.52")),
    ),
    ("13JAN", "14JAN", "10000007", ["FAKE SUPERMARKET FAKETOWN GB"], Decimal("9.69"), None),
]


def closing_balance() -> Decimal:
    bal = PREVIOUS
    for _, _, _, _, amount, foreign in TRANSACTIONS:
        bal += amount
        if foreign is not None:
            bal += foreign[2]  # separate fee is an additional charge
    return bal


# Column x-positions mirroring the real statement.
CX_TRANS = 71
CX_POST = 122
CX_REF = 167
CX_DESC = 218
CX_AMOUNT_R = 553   # right edge of the Amount £ column


def generate(path: str) -> None:
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    pound = "\u00a3"

    # --- Page 1: summary + metadata (header fields + detection anchors). ---
    c.setFont("Helvetica", 10)
    y = height - 60
    c.drawString(40, y, "CustomerService 0000 000 0000 tescobank.com CLUBCARD Credit Card")
    y -= 14
    c.drawString(40, y, "Statement date 16January2022")
    y -= 14
    c.drawString(40, y, "MasterCardnumber 0000000000000001")
    y -= 14
    c.drawString(40, y, "TescoBank")
    y -= 20
    c.drawString(40, y, "Account summary")
    y -= 14
    c.drawString(40, y, f"Previous balance {pound}{PREVIOUS:,.2f}")
    y -= 14
    c.drawString(40, y, f"New balance {pound}{closing_balance():,.2f}")
    c.showPage()

    # --- Page 2: boilerplate (SUMMARY BOX) to mirror the real page count. ---
    c.setFont("Helvetica", 9)
    c.drawString(40, height - 60, "SUMMARYBOX Cardholder statement version")
    c.showPage()

    # --- Page 3: the transaction table. ---
    c.setFont("Helvetica", 10)
    y = height - 60
    c.drawString(40, y, "CLUBCARD Credit Card")
    y -= 16
    c.drawString(CX_TRANS, y, "17December 2021- 16January 2022")
    y -= 16
    # Column header.
    c.setFont("Helvetica-Bold", 9)
    c.drawString(CX_TRANS, y, "Trans")
    c.drawString(CX_POST, y, "Post")
    c.drawString(CX_DESC, y, "Description")
    c.drawRightString(CX_AMOUNT_R, y, "Amount")
    y -= 10
    c.drawString(CX_TRANS, y, "Date")
    c.drawString(CX_POST, y, "Date")
    y -= 16

    c.setFont("Helvetica", 9)
    # Brought-forward marker (skipped).
    c.drawString(CX_DESC, y, "BALANCEFROMPREVIOUSSTATEMENT")
    c.drawRightString(CX_AMOUNT_R, y, f"{pound}{PREVIOUS:,.2f}")
    y -= 16

    for trans, post, ref, detail_lines, amount, foreign in TRANSACTIONS:
        c.drawString(CX_TRANS, y, trans)
        c.drawString(CX_POST, y, post)
        c.drawString(CX_REF, y, ref)
        c.drawString(CX_DESC, y, detail_lines[0])
        if foreign is None:
            # Amount on the same line; payments/refunds carry a leading minus.
            amt_str = (
                f"-{pound}{abs(amount):,.2f}" if amount < 0 else f"{pound}{amount:,.2f}"
            )
            c.drawRightString(CX_AMOUNT_R, y, amt_str)
            y -= 14
            for line in detail_lines[1:]:
                c.drawString(CX_DESC, y, line)
                y -= 14
        else:
            conv_detail, conv_amount_str, fee = foreign
            y -= 14
            # Converted sterling amount beside the conversion detail (no date).
            c.drawString(CX_DESC, y, conv_detail)
            c.drawRightString(CX_AMOUNT_R, y, conv_amount_str)
            y -= 14
            # Separate charged fee line.
            c.drawString(CX_DESC, y, "2.75%FOREIGNEXCHANGEFEEONTHISTRANSACTION")
            c.drawRightString(CX_AMOUNT_R, y, f"{pound}{fee:,.2f}")
            y -= 14

    # Carried-forward marker (skipped).
    c.drawString(CX_DESC, y, "NEWBALANCE")
    c.drawRightString(CX_AMOUNT_R, y, f"{pound}{closing_balance():,.2f}")

    c.showPage()
    c.save()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m statement_parser.synth_tesco OUT.pdf", file=sys.stderr)
        return 1
    generate(argv[0])
    print(f"wrote {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
