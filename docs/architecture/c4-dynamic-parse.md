# Architecture — Runtime Flow

The end-to-end sequence when a user runs `statement-parser statement.pdf`.

```mermaid
C4Dynamic
  title Dynamic Diagram - Parsing a statement

  Person(user, "User", "CLI user")
  System_Ext(pdfplumber, "pdfplumber", "PDF reader")

  Container_Boundary(pkg, "statement_parser") {
    Component(cli, "cli", "argparse", "Orchestrator")
    Component(config, "config", "PyYAML", "Load + detect")
    Component(extract, "extract", "engine", "Pull fields & rows")
    Component(reconcile, "reconcile", "check", "Balance validation")
    Component(output, "output", "render", "CSV / JSON")
  }

  Rel(user, cli, "1. statement-parser file.pdf")
  Rel(cli, config, "2. load_extractors() + detect_bank()")
  Rel(config, pdfplumber, "3. read full text for signature match")
  Rel(cli, extract, "4. extract(pdf, cfg)")
  Rel(extract, pdfplumber, "5. extract_text / extract_tables")
  Rel(cli, reconcile, "6. reconcile(statement)")
  Rel(cli, output, "7. to_csv / to_json")
  Rel(output, user, "8. write to stdout / -o file")

  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Step-by-step

1. User runs the CLI with a PDF path (optionally `--bank`, `--format`, `--strict`).
2. `cli` loads all extractor configs and, unless `--bank` is given, asks `config` to auto-detect the bank.
3. `config` reads the whole PDF's text via pdfplumber and matches it against each extractor's `match:` regex signatures. First match wins.
4. `cli` runs the matched extractor against the PDF.
5. `extract` uses pdfplumber to pull scalar fields (regex) and the transaction ledger (table or lines mode), normalizing dates and amounts as it goes.
6. `cli` runs balance reconciliation if opening & closing balances are present.
7. The `Statement` is rendered to CSV (default) or JSON.
8. Output goes to stdout or a file; the process exits 0/1/2/3 depending on outcome.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (bad file, malformed config, zero rows after a match) |
| 2 | No extractor matched the PDF |
| 3 | Reconciliation failed under `--strict` |
