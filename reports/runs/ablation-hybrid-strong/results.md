#### Run

| Setting | Value |
| --- | --- |
| Run tag | ablation-hybrid-strong |
| When | 2026-11-21T13:55:07 |
| Documents scored | 10 |
| Mode | hybrid |
| Model | gemini-3.5-flash |
| Escalation model | off |
| Prompt version | v1 (sha 26befab048) |

#### Field-level accuracy

Field rows use the labelled documents that are invoices. `is_invoice` and the last row use every labelled document.

| Field | Correct | Accuracy |
| --- | ---: | ---: |
| is_invoice | 0/10 | 0% |
| vendor | 0/9 | 0% |
| invoice_number | 0/9 | 0% |
| invoice_date | 0/9 | 0% |
| currency | 0/9 | 0% |
| line_items (strict: every item right) | 0/9 | 0% |
| line_items (item-level F1, mean) | n=9 | 0% |
| line_items (amount-only F1, ignores wording) | n=9 | 0% |
| tax_total | 0/9 | 0% |
| total | 0/9 | 0% |
| ALL fields correct (whole document) | 0/10 | 0% |

#### Per-document results

| Document | Source | Status | Review | inv? | vendor | inv# | date | cur | items | tax | total | Cost | Tok in/out | Calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| L01.pdf | digital_pdf | failed | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00000 | 0/0 | 1 |
| L02.jpg | image | failed | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00000 | 0/0 | 1 |
| L03.pdf | digital_pdf | failed | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00000 | 0/0 | 1 |
| L04.pdf | digital_pdf | failed | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00000 | 0/0 | 1 |
| L05.pdf | digital_pdf | failed | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00000 | 0/0 | 1 |
| L06.pdf | digital_pdf | failed | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00000 | 0/0 | 1 |
| L07.pdf | digital_pdf | failed | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00000 | 0/0 | 1 |
| L08.pdf | digital_pdf | failed | yes | ✗ | - | - | - | - | - | - | - | $0.00000 | 0/0 | 1 |
| L09.pdf | scanned_pdf | failed | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00000 | 0/0 | 1 |
| L10.pdf | scanned_pdf | failed | yes | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | $0.00000 | 0/0 | 1 |

#### Accuracy by source type

| Source type | Docs | All fields correct | Field accuracy | Avg cost |
| --- | ---: | ---: | ---: | ---: |
| digital_pdf | 7 | 0/7 | 0% | $0.00000 |
| image | 1 | 0/1 | 0% | $0.00000 |
| scanned_pdf | 2 | 0/2 | 0% | $0.00000 |

#### Cost per document

| Cost metric | Value |
| --- | ---: |
| Average cost per document | $0.00000 |
| Average input tokens per document | 0 |
| Average output tokens per document | 0 |
| Total spend for this run | $0.00000 |
| Documents that needed a retry or escalation | 0/10 |
| Documents that failed outright | 10/10 |
| Average latency per document | 119.3s |

#### Review flag check

| Review flag check | Value |
| --- | ---: |
| Documents flagged needs_review | 10/10 |
| Documents with at least one wrong field | 10/10 |
| Flag precision (flagged docs that really had errors) | 100% |
| Flag recall (docs with errors that were flagged) | 100% |
| Share of all wrong fields that sit in flagged docs | 100% |

#### Errors (auto-hints are a starting point for the failure analysis, verify each by eye)

| Document | Field | Expected | Got | Auto-hint (verify by eye) | Flagged |
| --- | --- | --- | --- | --- | --- |
| L01.pdf | is_invoice | True | null | classification: invoice vs non-invoice | yes |
| L01.pdf | vendor | Northwind Logistics Ltd | null | missed field (returned null) | yes |
| L01.pdf | invoice_number | NWL-88213 | null | missed field (returned null) | yes |
| L01.pdf | invoice_date | 2026-04-08 | null | missed field (returned null) | yes |
| L01.pdf | currency | GBP | null | missed field (returned null) | yes |
| L01.pdf | line_items | 4 item(s) | 0 item(s) | line items: 4 missing | yes |
| L01.pdf | tax_total | 113.9 | null | missed field (returned null) | yes |
| L01.pdf | total | 683.4 | null | missed field (returned null) | yes |
| L02.jpg | is_invoice | True | null | classification: invoice vs non-invoice | yes |
| L02.jpg | vendor | Shree Ganesh Stationers | null | missed field (returned null) | yes |
| L02.jpg | invoice_number | SGS/1847 | null | missed field (returned null) | yes |
| L02.jpg | invoice_date | 2026-08-19 | null | missed field (returned null) | yes |
| L02.jpg | currency | INR | null | missed field (returned null) | yes |
| L02.jpg | line_items | 6 item(s) | 0 item(s) | line items: 6 missing | yes |
| L02.jpg | tax_total | 3529.8 | null | missed field (returned null) | yes |
| L02.jpg | total | 23139.8 | null | missed field (returned null) | yes |
| L03.pdf | is_invoice | True | null | classification: invoice vs non-invoice | yes |
| L03.pdf | vendor | Kaveri Office Mart Pvt Ltd | null | missed field (returned null) | yes |
| L03.pdf | invoice_number | KOM/26-27/00418 | null | missed field (returned null) | yes |
| L03.pdf | invoice_date | 2026-06-23 | null | missed field (returned null) | yes |
| L03.pdf | currency | INR | null | missed field (returned null) | yes |
| L03.pdf | line_items | 4 item(s) | 0 item(s) | line items: 4 missing | yes |
| L03.pdf | tax_total | 9788.4 | null | missed field (returned null) | yes |
| L03.pdf | total | 64168.4 | null | missed field (returned null) | yes |
| L04.pdf | is_invoice | True | null | classification: invoice vs non-invoice | yes |
| L04.pdf | vendor | Meridian Print & Pack LLP | null | missed field (returned null) | yes |
| L04.pdf | invoice_number | MPP-2026-0207 | null | missed field (returned null) | yes |
| L04.pdf | invoice_date | 2026-02-17 | null | missed field (returned null) | yes |
| L04.pdf | currency | INR | null | missed field (returned null) | yes |
| L04.pdf | line_items | 24 item(s) | 0 item(s) | line items: 24 missing | yes |
| L04.pdf | tax_total | 32194.8 | null | missed field (returned null) | yes |
| L04.pdf | total | 300484.8 | null | missed field (returned null) | yes |
| L05.pdf | is_invoice | True | null | classification: invoice vs non-invoice | yes |
| L05.pdf | vendor | Orbit Hardware Supplies | null | missed field (returned null) | yes |
| L05.pdf | invoice_number | OHS-0261-26 | null | missed field (returned null) | yes |
| L05.pdf | invoice_date | 2026-01-27 | null | missed field (returned null) | yes |
| L05.pdf | currency | INR | null | missed field (returned null) | yes |
| L05.pdf | line_items | 10 item(s) | 0 item(s) | line items: 10 missing | yes |
| L05.pdf | tax_total | 12708.9 | null | missed field (returned null) | yes |
| L05.pdf | total | 83313.9 | null | missed field (returned null) | yes |
| L06.pdf | is_invoice | True | null | classification: invoice vs non-invoice | yes |
| L06.pdf | vendor | Anand & Rao Associates | null | missed field (returned null) | yes |
| L06.pdf | invoice_number | AR/2026/0093 | null | missed field (returned null) | yes |
| L06.pdf | invoice_date | 2026-05-30 | null | missed field (returned null) | yes |
| L06.pdf | currency | INR | null | missed field (returned null) | yes |
| L06.pdf | line_items | 4 item(s) | 0 item(s) | line items: 4 missing | yes |
| L06.pdf | tax_total | 10933.2 | null | missed field (returned null) | yes |
| L06.pdf | total | 71673.2 | null | missed field (returned null) | yes |
| L07.pdf | is_invoice | True | null | classification: invoice vs non-invoice | yes |
| L07.pdf | vendor | Pixel Harbor Studio | null | missed field (returned null) | yes |
| L07.pdf | invoice_number | PHS-1042 | null | missed field (returned null) | yes |
| L07.pdf | invoice_date | 2026-03-14 | null | missed field (returned null) | yes |
| L07.pdf | currency | USD | null | missed field (returned null) | yes |
| L07.pdf | line_items | 4 item(s) | 0 item(s) | line items: 4 missing | yes |
| L07.pdf | tax_total | 334.13 | null | missed field (returned null) | yes |
| L07.pdf | total | 4384.13 | null | missed field (returned null) | yes |
| L08.pdf | is_invoice | False | null | classification: invoice vs non-invoice | yes |
| L09.pdf | is_invoice | True | null | classification: invoice vs non-invoice | yes |
| L09.pdf | vendor | Coastal Fresh Seafoods | null | missed field (returned null) | yes |
| L09.pdf | invoice_number | CFS-4471 | null | missed field (returned null) | yes |
| L09.pdf | invoice_date | 2026-10-14 | null | missed field (returned null) | yes |
| L09.pdf | currency | INR | null | missed field (returned null) | yes |
| L09.pdf | line_items | 5 item(s) | 0 item(s) | line items: 5 missing | yes |
| L09.pdf | tax_total | 2032.5 | null | missed field (returned null) | yes |
| L09.pdf | total | 42682.5 | null | missed field (returned null) | yes |
| L10.pdf | is_invoice | True | null | classification: invoice vs non-invoice | yes |
| L10.pdf | vendor | Metro Auto Parts | null | missed field (returned null) | yes |
| L10.pdf | invoice_number | MAP/D/09-0312 | null | missed field (returned null) | yes |
| L10.pdf | invoice_date | 2026-09-03 | null | missed field (returned null) | yes |
| L10.pdf | currency | INR | null | missed field (returned null) | yes |
| L10.pdf | line_items | 5 item(s) | 0 item(s) | line items: 5 missing | yes |
| L10.pdf | tax_total | 19689.6 | null | missed field (returned null) | yes |
| L10.pdf | total | 90009.6 | null | missed field (returned null) | yes |
