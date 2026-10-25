"""Generate a synthetic Chase-UK-style round-up statement PDF for testing.

Mimics the real layout (whitespace-aligned, no grid lines, wrapped description
sub-labels, multi-page) with entirely fake data. Used for committed fixtures so
no real PII enters the repo.

Run: python -m statement_parser.synth_chase out.pdf
"""

from __future__ import annotations

import sys
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

OPENING = Decimal("50.00")
# (date, description, amount) — all credits, mirroring a round-up statement.
TRANSACTIONS = [
    ("01 Jan 2099", "Interest earned", Decimal("0.10")),
    ("01 Jan 2099", "Round up", Decimal("0.40")),
    ("02 Jan 2099", "Round up", Decimal("0.25")),
    ("03 Jan 2099", "Round up", Decimal("0.75")),
    ("05 Jan 2099", "Round up", Decimal("0.50")),
    ("08 Jan 2099", "Round up", Decimal("0.90")),
    ("12 Jan 2099", "Round up", Decimal("0.10")),
    ("15 Jan 2099", "Round up", Decimal("1.00")),
    ("20 Jan 2099", "Round up", Decimal("0.30")),
    ("28 Jan 2099", "Round up", Decimal("0.20")),
]


def closing_balance() -> Decimal:
    bal = OPENING
    for _, _, amt in TRANSACTIONS:
        bal += amt
    return bal


def money_in() -> Decimal:
    return sum((amt for _, _, amt in TRANSACTIONS), Decimal("0"))


def generate(path: str) -> None:
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    def header(page_first: bool, y_start: float) -> float:
        y = y_start
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Round-up statement")
        y -= 14
        c.setFont("Helvetica", 10)
        c.drawString(40, y, "01 January 2099 - 31 January 2099")
        y -= 24
        if page_first:
            # Summary block.
            c.setFont("Helvetica", 9)
            c.drawString(40, y, "Opening balance Money in Money out Closing balance")
            y -= 12
            c.drawString(40, y, "+ - =")
            y -= 12
            c.drawString(
                40,
                y,
                f"GBP{OPENING:.2f} GBP{money_in():.2f} GBP0.00 GBP{closing_balance():.2f}".replace(
                    "GBP", "\u00a3"
                ),
            )
            y -= 24
        # Column header row.
        c.setFont("Helvetica-Bold", 9)
        c.drawString(40, y, "Date")
        c.drawString(140, y, "Transaction details")
        c.drawString(430, y, "Amount")
        c.drawString(510, y, "Balance")
        y -= 18
        return y

    # Lay rows across pages. Keep it deterministic and simple: fixed rows/page.
    pound = "\u00a3"
    rows = []
    bal = OPENING
    for date, desc, amt in TRANSACTIONS:
        bal += amt
        rows.append((date, desc, f"+{pound}{amt:.2f}", f"{pound}{bal:.2f}"))

    per_page = 4
    pages = [rows[i : i + per_page] for i in range(0, len(rows), per_page)]
    total_pages = len(pages)

    for pidx, page_rows in enumerate(pages):
        y = header(pidx == 0, height - 30)
        c.setFont("Helvetica", 9)
        for date, desc, amt, bal_s in page_rows:
            c.drawString(40, y, date)
            c.drawString(140, y, desc)
            # Right-align amount and balance roughly like the real statement.
            c.drawRightString(476, y, amt)
            c.drawRightString(556, y, bal_s)
            y -= 12
            # Wrapped sub-label on its own line (should be skipped by the parser).
            c.drawString(140, y, "Transfer" if desc == "Round up" else "Interest")
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
