# Architecture — Component Diagram

How the `statement_parser` package is structured and how the pieces fit
together. This is the main "how the code works" view.

```mermaid
C4Component
  title Component Diagram - pdf-statement-parser

  Person(user, "User", "Runs the CLI on a statement PDF")
  System_Ext(pdfplumber, "pdfplumber", "Reads PDF text, words, tables")
  System_Ext(configs, "extractors/*.yaml", "Per-bank extractor definitions")

  Container_Boundary(pkg, "statement_parser package") {
    Component(cli, "cli", "argparse", "Entry point: parses args, orchestrates, picks exit code")
    Component(config, "config", "PyYAML", "Loads extractors, auto-detects bank by signature")
    Component(extract, "extract", "pdfplumber", "table/lines/positional extraction engine")
    Component(normalize, "normalize", "Decimal/datetime", "Raw strings -> ISO dates + signed decimals")
    Component(reconcile, "reconcile", "Decimal", "opening + sum(amounts) == closing check")
    Component(output, "output", "csv/json", "Renders Statement as CSV or JSON")
    Component(models, "models", "dataclasses", "Config schema + Statement/Transaction types")
  }

  Rel(user, cli, "Runs", "statement-parser file.pdf")
  Rel(cli, config, "Loads extractors & detects bank")
  Rel(config, configs, "Reads", "*.yaml")
  Rel(config, models, "Builds ExtractorConfig")
  Rel(cli, extract, "Runs extractor on PDF")
  Rel(extract, pdfplumber, "Opens PDF, gets text/tables")
  Rel(extract, normalize, "Cleans dates & amounts")
  Rel(extract, models, "Produces Statement")
  Rel(cli, reconcile, "Validates balances")
  Rel(cli, output, "Renders result")
  Rel(output, models, "Reads Statement")

  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## What each module does

| Module | Responsibility |
|--------|---------------|
| `cli.py` | Parses CLI args, orchestrates the pipeline, chooses the exit code (0/1/2/3). |
| `config.py` | Discovers and loads `*.yaml` extractors; auto-detects the bank by matching each config's `match:` signature against the PDF text. |
| `models.py` | Dataclasses for the config schema (`ExtractorConfig`, `TransactionConfig`, `FieldConfig`, `NormalizationConfig`) and the output (`Statement`, `Transaction`). |
| `extract.py` | The engine. Uses pdfplumber to pull scalar fields (regex/bbox) and transactions (table, lines, or positional mode). Raises if zero rows after a match. |
| `normalize.py` | Converts raw strings to ISO dates and signed `Decimal` amounts per the bank's rules (separators, `£`/`$`, `CR`/`DR`, parentheses). |
| `reconcile.py` | Checks `opening + sum(amounts) == closing` when both balances are present. |
| `output.py` | Renders a `Statement` to CSV (ledger) or JSON (fields + ledger). |
