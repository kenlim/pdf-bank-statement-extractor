# pdf-statement-parser

A command-line tool that extracts transaction data from machine-generated bank
statement PDFs. Each bank's layout is described by a declarative YAML
**extractor**, so adding support for a new bank is a no-code task.

Built on [`pdfplumber`](https://github.com/jsvine/pdfplumber). Works on digital
(text-layer) PDFs — not scanned images (no OCR).

## Install

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```sh
# Auto-detect the bank and print the transaction ledger as CSV
statement-parser statement.pdf

# Full statement (fields + transactions) as JSON
statement-parser statement.pdf --format json

# Force a specific extractor instead of auto-detecting
statement-parser statement.pdf --bank acme-bank

# Write to a file
statement-parser statement.pdf -o out.csv

# Fail (exit 3) if opening + transactions != closing balance
statement-parser statement.pdf --strict

# List known extractors
statement-parser --list-banks

# When no extractor matches, dump the raw text to help author a new config
statement-parser mystery.pdf --debug
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (bad file, malformed config, zero rows after a match) |
| 2 | No extractor matched the PDF |
| 3 | Balance reconciliation failed under `--strict` |

## Writing an extractor

Extractors are YAML files loaded from:

1. the repo's `extractors/` directory,
2. `$STATEMENT_PARSER_CONFIG_DIR`, if set,
3. any `--config-dir DIR` (repeatable).

See [`extractors/acme-bank.yaml`](extractors/acme-bank.yaml) for a fully
annotated reference. The schema:

```yaml
name: my-bank                 # unique extractor name

match:                        # regexes; any match identifies this bank
  - "MY BANK PLC"

normalization:                # per-bank date/amount rules
  date_formats: ["%d/%m/%Y"]  # strptime formats, tried in order
  decimal_separator: "."
  thousands_separator: ","
  parentheses_negative: true  # (4.50) -> -4.50
  credit_suffixes: ["CR"]
  debit_suffixes: ["DR"]

fields:                       # scalar statement-level fields (all optional)
  account_number:
    pattern: "Account Number:\\s*([0-9-]+)"  # 1st capture group is the value
  opening_balance:
    pattern: "Opening Balance:\\s*([0-9.,]+)"
    kind: amount              # string (default) | amount | date
    # page: 1                 # optional: restrict to one page (1-indexed)
    # bbox: [x0, top, x1, bottom]   # optional: restrict to a region

transactions:
  table_settings:             # passed straight to pdfplumber extract_tables
    vertical_strategy: lines  # lines | lines_strict | text | explicit
    horizontal_strategy: lines
  region:                     # optional: restrict the table search area
    # page: 1
    # bbox: [x0, top, x1, bottom]
  header_rows: 1              # leading rows per table treated as the header
  header_labels: ["Date", "Description", "Amount", "Balance"]  # repeated-header rows to drop
  columns:                    # map output field -> column index in the table
    date: 0
    description: 1
    amount: 2
    balance: 3
```

Recognized transaction output fields: `date`, `description`, `amount`,
`balance`. `date` is normalized to ISO 8601; `amount` and `balance` to signed
decimals.

### Transaction extraction modes

The `transactions` block has two modes, chosen per bank:

**`mode: table`** (default) — uses pdfplumber's table extraction. Best for
statements with a ruled grid (visible cell borders). Requires `columns`
(field → column index). See [`extractors/acme-bank.yaml`](extractors/acme-bank.yaml).

**`mode: lines`** — applies a regex (`row_pattern`) to each text line across all
pages. Best for whitespace-aligned statements with no usable grid lines (many
real bank PDFs). Lines that don't match (headers, footers, wrapped description
sub-labels) are skipped automatically. The regex must use named groups
`date`, `description`, `amount`, `balance`. See
[`extractors/chase-uk.yaml`](extractors/chase-uk.yaml):

```yaml
transactions:
  mode: lines
  row_pattern: "^(?P<date>\\d{2} \\w{3} \\d{4})\\s+(?P<description>.+?)\\s+(?P<amount>[+-]?£[\\d,]+\\.\\d{2})\\s+(?P<balance>£[\\d,]+\\.\\d{2})$"
```

**`mode: positional`** — classifies words into columns by their x-position. Best
for statements with **separate debit/credit columns** (`Paid out` / `Paid in` /
`Balance`) and no grid lines — common in UK banking (HSBC, Barclays, Lloyds,
NatWest). Handles multi-line descriptions and emits a transaction whenever a row
carries a paid-out or paid-in amount. The signed amount is `paid_in - paid_out`
(credits positive, debits negative). See
[`extractors/hsbc-advance.yaml`](extractors/hsbc-advance.yaml):

```yaml
transactions:
  mode: positional
  paid_out_max: 410          # amount x1 <= this -> paid out (debit)
  paid_in_max: 495           # else x1 <= this   -> paid in (credit)
                             # else               -> running balance
  date_x_max: 100            # words with x0 <= this are the date column
  date_pattern: "^\\d{2} \\w{3} \\d{2}$"
  skip_rows_matching:        # non-transaction marker rows
    - "BALANCE *BROUGHT *FORWARD"
    - "BALANCE *CARRIED *FORWARD"
```

Tip: `statement-parser mystery.pdf --debug` dumps the extracted text so you can
see each line and craft the `row_pattern`. For positional mode, inspect word
x-positions with pdfplumber to find the column boundaries.

### Authoring workflow

1. Put a real statement in `samples/` (gitignored — never committed).
2. Run `statement-parser samples/mine.pdf --debug` to dump the extracted text
   and find anchor strings for `match` and `fields`.
3. Write the YAML, iterate until the CSV/JSON looks right.
4. Generate a synthetic fixture with the same layout and commit it under
   `tests/fixtures/` with golden output files (see below). Real PDFs stay local.

## Testing

```sh
python -m pytest
```

Tests run against **synthetic** fixture PDFs (fake data, safe to commit),
generated by `statement_parser.synth_acme` (table mode),
`statement_parser.synth_chase` (lines mode), `statement_parser.synth_monzo`
(positional single-column), and `statement_parser.synth_hsbc` (positional
debit/credit). Real statements never enter
the repo — `samples/` and `*.real.pdf` are gitignored.

To regenerate the Acme fixture and its golden files:

```sh
python -m statement_parser.synth_acme tests/fixtures/acme-bank.pdf
statement-parser tests/fixtures/acme-bank.pdf -o tests/fixtures/acme-bank.golden.csv
statement-parser tests/fixtures/acme-bank.pdf --format json -o tests/fixtures/acme-bank.golden.json
```
