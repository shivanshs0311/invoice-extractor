#### Run

| Setting | Value |
| --- | --- |
| Run tag | ablation-hybrid-cheap |
| When | 2026-11-21T17:57:23 |
| Documents scored | 10 |
| Mode | hybrid |
| Model | gemini-3.5-flash-lite |
| Escalation model | off |
| Prompt version | v1 (sha 26befab048) |

#### Field-level accuracy

Field rows use the labelled documents that are invoices. `is_invoice` and the last row use every labelled document.

| Field | Correct | Accuracy |
| --- | ---: | ---: |
| is_invoice | 10/10 | 100% |
| vendor | 9/9 | 100% |
| invoice_number | 9/9 | 100% |
| invoice_date | 9/9 | 100% |
| currency | 9/9 | 100% |
| line_items (strict: every item right) | 9/9 | 100% |
| line_items (item-level F1, mean) | n=9 | 100% |
| line_items (amount-only F1, ignores wording) | n=9 | 100% |
| tax_total | 9/9 | 100% |
| total | 9/9 | 100% |
| ALL fields correct (whole document) | 10/10 | 100% |

#### Per-document results

| Document | Source | Status | Review | inv? | vendor | inv# | date | cur | items | tax | total | Cost | Tok in/out | Calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| L01.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00152 | 2,582/297 | 1 |
| L02.jpg | image | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00165 | 2,245/391 | 1 |
| L03.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00160 | 2,716/316 | 1 |
| L04.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00457 | 4,604/1,275 | 1 |
| L05.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00234 | 2,856/594 | 1 |
| L06.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00162 | 2,702/324 | 1 |
| L07.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00152 | 2,603/296 | 1 |
| L08.pdf | digital_pdf | ok | no | ✓ | - | - | - | - | - | - | - | $0.00110 | 2,697/116 | 1 |
| L09.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00160 | 2,245/370 | 1 |
| L10.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00164 | 2,217/388 | 1 |

#### Accuracy by source type

| Source type | Docs | All fields correct | Field accuracy | Avg cost |
| --- | ---: | ---: | ---: | ---: |
| digital_pdf | 7 | 7/7 | 100% | $0.00204 |
| image | 1 | 1/1 | 100% | $0.00165 |
| scanned_pdf | 2 | 2/2 | 100% | $0.00162 |

#### Cost per document

| Cost metric | Value |
| --- | ---: |
| Average cost per document | $0.00192 |
| Average input tokens per document | 2,747 |
| Average output tokens per document | 437 |
| Total spend for this run | $0.01916 |
| Documents that needed a retry or escalation | 0/10 |
| Documents that failed outright | 0/10 |
| Average latency per document | 10.6s |

#### Review flag check

| Review flag check | Value |
| --- | ---: |
| Documents flagged needs_review | 0/10 |
| Documents with at least one wrong field | 0/10 |
| Flag precision (flagged docs that really had errors) | n/a |
| Flag recall (docs with errors that were flagged) | n/a |
| Share of all wrong fields that sit in flagged docs | n/a |

#### Errors (auto-hints are a starting point for the failure analysis, verify each by eye)

No errors.
