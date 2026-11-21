#### Run

| Setting | Value |
| --- | --- |
| Run tag | ablation-text-only |
| When | 2026-11-21T17:57:23 |
| Documents scored | 10 |
| Mode | text |
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
| L01.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00119 | 1,482/297 | 1 |
| L02.jpg | image | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00165 | 2,245/391 | 1 |
| L03.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00129 | 1,616/324 | 1 |
| L04.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00391 | 2,404/1,275 | 1 |
| L05.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00198 | 1,756/582 | 1 |
| L06.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00129 | 1,602/324 | 1 |
| L07.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00120 | 1,503/298 | 1 |
| L08.pdf | digital_pdf | ok | no | ✓ | - | - | - | - | - | - | - | $0.00078 | 1,597/121 | 1 |
| L09.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00158 | 2,245/364 | 1 |
| L10.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00164 | 2,217/388 | 1 |

#### Accuracy by source type

| Source type | Docs | All fields correct | Field accuracy | Avg cost |
| --- | ---: | ---: | ---: | ---: |
| digital_pdf | 7 | 7/7 | 100% | $0.00166 |
| image | 1 | 1/1 | 100% | $0.00165 |
| scanned_pdf | 2 | 2/2 | 100% | $0.00161 |

#### Cost per document

| Cost metric | Value |
| --- | ---: |
| Average cost per document | $0.00165 |
| Average input tokens per document | 1,867 |
| Average output tokens per document | 436 |
| Total spend for this run | $0.01651 |
| Documents that needed a retry or escalation | 0/10 |
| Documents that failed outright | 0/10 |
| Average latency per document | 2.7s |

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
