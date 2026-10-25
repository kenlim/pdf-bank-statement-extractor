# Architecture — Extraction Engine Internals

The core logic: how `extract.py` turns a PDF + extractor config into a
`Statement`. This is where the two transaction modes (`table` and `lines`)
diverge.

## Overall extraction flow

```mermaid
flowchart TD
    start([extract pdf, cfg]) --> fields[Extract scalar fields<br/>account no, period, balances]
    fields --> mode{transactions.mode?}

    mode -->|table| tbl[Table extraction]
    mode -->|lines| lin[Lines extraction]
    mode -->|positional| pos[Positional extraction]

    tbl --> rows[List of Transaction]
    lin --> rows
    pos --> rows
    rows --> empty{zero rows?}
    empty -->|yes| err[/raise ExtractionError<br/>loud failure, exit 1/]
    empty -->|no| stmt([return Statement])
```

## Scalar field extraction (both modes)

Each `fields:` entry is a regex (optionally scoped to a page/bbox). The first
capture group is the value; `kind: amount|date` triggers normalization.

```mermaid
flowchart LR
    f[FieldConfig<br/>pattern, page?, bbox?] --> crop[Crop page to bbox<br/>if set]
    crop --> txt[page.extract_text]
    txt --> re{regex match?}
    re -->|yes| grp[Take group 1<br/>or whole match]
    re -->|no| none[value = None]
    grp --> kind{kind?}
    kind -->|amount| na[normalize_amount]
    kind -->|date| nd[normalize_date]
    kind -->|string| raw[keep as-is]
```

## Table mode (ruled grids — e.g. Acme fixture)

```mermaid
flowchart TD
    p[For each page in region] --> crop[Crop to region bbox]
    crop --> et[pdfplumber extract_tables<br/>using table_settings]
    et --> hdr[Drop header_rows per table]
    hdr --> rep{row == repeated<br/>header labels?}
    rep -->|yes| skip1[skip]
    rep -->|no| blank{all cells blank?}
    blank -->|yes| skip2[skip]
    blank -->|no| map[Map columns by index<br/>date=0, desc=1, ...]
    map --> norm[normalize date & amounts]
    norm --> out[Transaction]
```

## Lines mode (whitespace-aligned — e.g. Chase statements)

```mermaid
flowchart TD
    p[For each page in region] --> txt[page.extract_text]
    txt --> split[Split into lines]
    split --> each[For each line]
    each --> m{row_pattern<br/>matches?}
    m -->|no| skip[skip<br/>header / footer / wrapped sub-label]
    m -->|yes| grp[Named groups:<br/>date, description, amount, balance]
    grp --> norm[normalize date & amounts]
    norm --> out[Transaction]
```

The lines mode is why Chase statements work: they have no usable grid lines, so
table detection fails, but each ledger row has a regular shape
(`DD Mon YYYY  description  ±£amount  £balance`) that a regex captures cleanly.
Wrapped description sub-labels (a second line reading "Transfer" or "Purchase")
simply don't match the full-row pattern and are skipped.

## Positional mode (separate debit/credit columns — e.g. HSBC)

```mermaid
flowchart TD
    p[For each page in region] --> w[page.extract_words with x/y coords]
    w --> grp[Group words into rows<br/>by vertical position]
    grp --> each[For each row]
    each --> cls[Classify each word:<br/>date col / description / amount]
    cls --> amtcol{amount's x1 position?}
    amtcol -->|<= paid_out_max| po[paid_out]
    amtcol -->|<= paid_in_max| pi[paid_in]
    amtcol -->|otherwise| bal[balance]
    cls --> datecol{date in date column?}
    datecol -->|yes| setdate[update current_date]
    cls --> desc[accumulate description fragments]
    po --> emit{row has paid_out<br/>or paid_in?}
    pi --> emit
    emit -->|yes| txn[Emit Transaction<br/>amount = paid_in - paid_out<br/>attach pending description]
    emit -->|no| cont[keep accumulating]
    desc --> emit
```

The positional mode handles statements like HSBC Advance that have **separate
`Paid out` / `Paid in` / `Balance` columns** and no grid lines. Debit vs credit
is determined by an amount's horizontal position, not a sign. Descriptions span
multiple lines, so fragments accumulate until a row carries an amount, which
closes the transaction. `BALANCE BROUGHT/CARRIED FORWARD` marker rows are
skipped via `skip_rows_matching`.

## Normalization

```mermaid
flowchart LR
    subgraph amount[normalize_amount]
        a1["(1,234.56)"] --> a2[strip parens<br/>sign = -1]
        a2 --> a3[strip CR/DR suffix]
        a3 --> a4[strip £ $ and<br/>non-numeric chars]
        a4 --> a5[apply separators]
        a5 --> a6[Decimal × sign]
    end

    subgraph date[normalize_date]
        d1["01 Sep 2026"] --> d2[try each<br/>date_format in order]
        d2 --> d3["ISO: 2026-09-01"]
    end
```
