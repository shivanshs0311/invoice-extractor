#### Run

| Setting | Value |
| --- | --- |
| Run tag | stress |
| When | 2026-11-21T15:13:37 |
| Documents scored | 30 |
| Mode | auto |
| Model | gemini-3.5-flash-lite |
| Escalation model | gemini-3.5-flash |
| Prompt version | v1 (sha 26befab048) |

#### Field-level accuracy

Field rows use the labelled documents that are invoices. `is_invoice` and the last row use every labelled document.

| Field | Correct | Accuracy |
| --- | ---: | ---: |
| is_invoice | 24/30 | 80% |
| vendor | 18/27 | 67% |
| invoice_number | 13/27 | 48% |
| invoice_date | 15/27 | 56% |
| currency | 18/27 | 67% |
| line_items (strict: every item right) | 15/27 | 56% |
| line_items (item-level F1, mean) | n=27 | 61% |
| line_items (amount-only F1, ignores wording) | n=27 | 61% |
| tax_total | 14/27 | 52% |
| total | 14/27 | 52% |
| ALL fields correct (whole document) | 15/30 | 50% |

#### Per-document results

| Document | Source | Status | Review | inv? | vendor | inv# | date | cur | items | tax | total | Cost | Tok in/out | Calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| L01_medium.pdf | scanned_pdf | needs_review | yes | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | $0.00141 | 2,245/296 | 2 |
| L01_mild.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00140 | 2,245/291 | 1 |
| L01_severe.pdf | scanned_pdf | needs_review | yes | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00097 | 2,245/120 | 2 |
| L02_medium.pdf | scanned_pdf | needs_review | yes | ✓ | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | $0.00174 | 2,245/427 | 2 |
| L02_mild.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00165 | 2,245/391 | 1 |
| L02_severe.pdf | scanned_pdf | needs_review | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00099 | 2,245/126 | 1 |
| L03_medium.pdf | scanned_pdf | needs_review | yes | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00155 | 2,245/352 | 1 |
| L03_mild.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00146 | 2,245/316 | 1 |
| L03_severe.pdf | scanned_pdf | needs_review | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00098 | 2,245/121 | 1 |
| L04_medium.pdf | scanned_pdf | needs_review | yes | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00425 | 3,345/1,299 | 1 |
| L04_mild.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00421 | 3,345/1,284 | 1 |
| L04_severe.pdf | scanned_pdf | needs_review | yes | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00130 | 3,345/118 | 2 |
| L05_medium.pdf | scanned_pdf | needs_review | yes | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | $0.00222 | 2,245/620 | 2 |
| L05_mild.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00213 | 2,245/582 | 1 |
| L05_severe.pdf | scanned_pdf | needs_review | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00097 | 2,245/119 | 1 |
| L06_medium.pdf | scanned_pdf | needs_review | yes | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00155 | 2,245/351 | 1 |
| L06_mild.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00148 | 2,245/324 | 1 |
| L06_severe.pdf | scanned_pdf | needs_review | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00096 | 2,245/114 | 1 |
| L07_medium.pdf | scanned_pdf | needs_review | yes | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00145 | 2,245/309 | 1 |
| L07_mild.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00141 | 2,245/296 | 1 |
| L07_severe.pdf | scanned_pdf | needs_review | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00098 | 2,245/123 | 1 |
| L08_medium.pdf | scanned_pdf | ok | no | ✓ | - | - | - | - | - | - | - | $0.00099 | 2,245/127 | 1 |
| L08_mild.pdf | scanned_pdf | ok | no | ✓ | - | - | - | - | - | - | - | $0.00097 | 2,245/117 | 1 |
| L08_severe.pdf | scanned_pdf | needs_review | yes | ✓ | - | - | - | - | - | - | - | $0.00098 | 2,245/122 | 1 |
| L09_medium.pdf | scanned_pdf | needs_review | yes | ✓ | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | $0.00163 | 2,245/384 | 2 |
| L09_mild.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00160 | 2,245/370 | 1 |
| L09_severe.pdf | scanned_pdf | needs_review | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00097 | 2,245/120 | 1 |
| L10_medium.pdf | scanned_pdf | needs_review | yes | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✗ | ✗ | $0.00160 | 2,245/370 | 2 |
| L10_mild.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00157 | 2,245/358 | 1 |
| L10_severe.pdf | scanned_pdf | needs_review | yes | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00098 | 2,245/121 | 2 |

#### Accuracy by source type

| Source type | Docs | All fields correct | Field accuracy | Avg cost |
| --- | ---: | ---: | ---: | ---: |
| scanned_pdf | 30 | 15/30 | 60% | $0.00155 |

#### Cost per document

| Cost metric | Value |
| --- | ---: |
| Average cost per document | $0.00155 |
| Average input tokens per document | 2,355 |
| Average output tokens per document | 336 |
| Total spend for this run | $0.04637 |
| Documents that needed a retry or escalation | 8/30 |
| Documents that failed outright | 0/30 |
| Average latency per document | 52.3s |

#### Review flag check

| Review flag check | Value |
| --- | ---: |
| Documents flagged needs_review | 19/30 |
| Documents with at least one wrong field | 15/30 |
| Flag precision (flagged docs that really had errors) | 79% |
| Flag recall (docs with errors that were flagged) | 100% |
| Share of all wrong fields that sit in flagged docs | 100% |

#### Errors (auto-hints are a starting point for the failure analysis, verify each by eye)

| Document | Field | Expected | Got | Auto-hint (verify by eye) | Flagged |
| --- | --- | --- | --- | --- | --- |
| L01_medium.pdf | line_items | 4 item(s) | 4 item(s) | line items: wrong amounts | yes |
| L01_severe.pdf | vendor | Northwind Logistics Ltd | null | missed field (returned null) | yes |
| L01_severe.pdf | invoice_number | NWL-88213 | null | missed field (returned null) | yes |
| L01_severe.pdf | invoice_date | 2026-04-08 | null | missed field (returned null) | yes |
| L01_severe.pdf | currency | GBP | null | missed field (returned null) | yes |
| L01_severe.pdf | line_items | 4 item(s) | 0 item(s) | line items: 4 missing | yes |
| L01_severe.pdf | tax_total | 113.9 | null | missed field (returned null) | yes |
| L01_severe.pdf | total | 683.4 | null | missed field (returned null) | yes |
| L02_medium.pdf | invoice_number | SGS/1847 | SG6/3847 | wrong identifier (PO or order number?) or misread characters | yes |
| L02_medium.pdf | invoice_date | 2026-08-19 | 2020-06-18 | wrong date (due date or another date?) | yes |
| L02_medium.pdf | line_items | 6 item(s) | 6 item(s) | line items: wrong amounts | yes |
| L02_medium.pdf | tax_total | 3529.8 | 3528.8 | wrong number (misread digit or wrong row) | yes |
| L02_medium.pdf | total | 23139.8 | 23138.8 | wrong number (misread digit or wrong row) | yes |
| L02_severe.pdf | is_invoice | True | False | classification: invoice vs non-invoice | yes |
| L02_severe.pdf | vendor | Shree Ganesh Stationers | null | missed field (returned null) | yes |
| L02_severe.pdf | invoice_number | SGS/1847 | null | missed field (returned null) | yes |
| L02_severe.pdf | invoice_date | 2026-08-19 | null | missed field (returned null) | yes |
| L02_severe.pdf | currency | INR | null | missed field (returned null) | yes |
| L02_severe.pdf | line_items | 6 item(s) | 0 item(s) | line items: 6 missing | yes |
| L02_severe.pdf | tax_total | 3529.8 | null | missed field (returned null) | yes |
| L02_severe.pdf | total | 23139.8 | null | missed field (returned null) | yes |
| L03_severe.pdf | is_invoice | True | False | classification: invoice vs non-invoice | yes |
| L03_severe.pdf | vendor | Kaveri Office Mart Pvt Ltd | null | missed field (returned null) | yes |
| L03_severe.pdf | invoice_number | KOM/26-27/00418 | null | missed field (returned null) | yes |
| L03_severe.pdf | invoice_date | 2026-06-23 | null | missed field (returned null) | yes |
| L03_severe.pdf | currency | INR | null | missed field (returned null) | yes |
| L03_severe.pdf | line_items | 4 item(s) | 0 item(s) | line items: 4 missing | yes |
| L03_severe.pdf | tax_total | 9788.4 | null | missed field (returned null) | yes |
| L03_severe.pdf | total | 64168.4 | null | missed field (returned null) | yes |
| L04_severe.pdf | vendor | Meridian Print & Pack LLP | null | missed field (returned null) | yes |
| L04_severe.pdf | invoice_number | MPP-2026-0207 | null | missed field (returned null) | yes |
| L04_severe.pdf | invoice_date | 2026-02-17 | null | missed field (returned null) | yes |
| L04_severe.pdf | currency | INR | null | missed field (returned null) | yes |
| L04_severe.pdf | line_items | 24 item(s) | 0 item(s) | line items: 24 missing | yes |
| L04_severe.pdf | tax_total | 32194.8 | null | missed field (returned null) | yes |
| L04_severe.pdf | total | 300484.8 | null | missed field (returned null) | yes |
| L05_medium.pdf | invoice_number | OHS-0261-26 | OHS-8261-26 | wrong identifier (PO or order number?) or misread characters | yes |
| L05_medium.pdf | tax_total | 12708.9 | 12705.5 | wrong number (misread digit or wrong row) | yes |
| L05_medium.pdf | total | 83313.9 | 83313.5 | wrong number (misread digit or wrong row) | yes |
| L05_severe.pdf | is_invoice | True | False | classification: invoice vs non-invoice | yes |
| L05_severe.pdf | vendor | Orbit Hardware Supplies | null | missed field (returned null) | yes |
| L05_severe.pdf | invoice_number | OHS-0261-26 | null | missed field (returned null) | yes |
| L05_severe.pdf | invoice_date | 2026-01-27 | null | missed field (returned null) | yes |
| L05_severe.pdf | currency | INR | null | missed field (returned null) | yes |
| L05_severe.pdf | line_items | 10 item(s) | 0 item(s) | line items: 10 missing | yes |
| L05_severe.pdf | tax_total | 12708.9 | null | missed field (returned null) | yes |
| L05_severe.pdf | total | 83313.9 | null | missed field (returned null) | yes |
| L06_severe.pdf | is_invoice | True | False | classification: invoice vs non-invoice | yes |
| L06_severe.pdf | vendor | Anand & Rao Associates | null | missed field (returned null) | yes |
| L06_severe.pdf | invoice_number | AR/2026/0093 | null | missed field (returned null) | yes |
| L06_severe.pdf | invoice_date | 2026-05-30 | null | missed field (returned null) | yes |
| L06_severe.pdf | currency | INR | null | missed field (returned null) | yes |
| L06_severe.pdf | line_items | 4 item(s) | 0 item(s) | line items: 4 missing | yes |
| L06_severe.pdf | tax_total | 10933.2 | null | missed field (returned null) | yes |
| L06_severe.pdf | total | 71673.2 | null | missed field (returned null) | yes |
| L07_medium.pdf | invoice_number | PHS-1042 | PHS-1842 | wrong identifier (PO or order number?) or misread characters | yes |
| L07_severe.pdf | is_invoice | True | False | classification: invoice vs non-invoice | yes |
| L07_severe.pdf | vendor | Pixel Harbor Studio | null | missed field (returned null) | yes |
| L07_severe.pdf | invoice_number | PHS-1042 | null | missed field (returned null) | yes |
| L07_severe.pdf | invoice_date | 2026-03-14 | null | missed field (returned null) | yes |
| L07_severe.pdf | currency | USD | null | missed field (returned null) | yes |
| L07_severe.pdf | line_items | 4 item(s) | 0 item(s) | line items: 4 missing | yes |
| L07_severe.pdf | tax_total | 334.13 | null | missed field (returned null) | yes |
| L07_severe.pdf | total | 4384.13 | null | missed field (returned null) | yes |
| L09_medium.pdf | invoice_number | CFS-4471 | CFS-4472 | wrong identifier (PO or order number?) or misread characters | yes |
| L09_medium.pdf | invoice_date | 2026-10-14 | 2020-10-14 | wrong date (due date or another date?) | yes |
| L09_medium.pdf | line_items | 5 item(s) | 5 item(s) | line items: wrong amounts | yes |
| L09_medium.pdf | tax_total | 2032.5 | 3636.5 | wrong number (misread digit or wrong row) | yes |
| L09_medium.pdf | total | 42682.5 | 80982.5 | wrong number (misread digit or wrong row) | yes |
| L09_severe.pdf | is_invoice | True | False | classification: invoice vs non-invoice | yes |
| L09_severe.pdf | vendor | Coastal Fresh Seafoods | null | missed field (returned null) | yes |
| L09_severe.pdf | invoice_number | CFS-4471 | null | missed field (returned null) | yes |
| L09_severe.pdf | invoice_date | 2026-10-14 | null | missed field (returned null) | yes |
| L09_severe.pdf | currency | INR | null | missed field (returned null) | yes |
| L09_severe.pdf | line_items | 5 item(s) | 0 item(s) | line items: 5 missing | yes |
| L09_severe.pdf | tax_total | 2032.5 | null | missed field (returned null) | yes |
| L09_severe.pdf | total | 42682.5 | null | missed field (returned null) | yes |
| L10_medium.pdf | invoice_number | MAP/D/09-0312 | MAP/20-21/112 | wrong identifier (PO or order number?) or misread characters | yes |
| L10_medium.pdf | invoice_date | 2026-09-03 | 2020-09-03 | wrong date (due date or another date?) | yes |
| L10_medium.pdf | tax_total | 19689.6 | 19688.6 | wrong number (misread digit or wrong row) | yes |
| L10_medium.pdf | total | 90009.6 | 190009.6 | wrong number (misread digit or wrong row) | yes |
| L10_severe.pdf | vendor | Metro Auto Parts | null | missed field (returned null) | yes |
| L10_severe.pdf | invoice_number | MAP/D/09-0312 | null | missed field (returned null) | yes |
| L10_severe.pdf | invoice_date | 2026-09-03 | null | missed field (returned null) | yes |
| L10_severe.pdf | currency | INR | null | missed field (returned null) | yes |
| L10_severe.pdf | line_items | 5 item(s) | 0 item(s) | line items: 5 missing | yes |
| L10_severe.pdf | tax_total | 19689.6 | null | missed field (returned null) | yes |
| L10_severe.pdf | total | 90009.6 | null | missed field (returned null) | yes |
