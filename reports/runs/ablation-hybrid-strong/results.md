#### Run

| Setting | Value |
| --- | --- |
| Run tag | ablation-hybrid-strong |
| When | 2026-11-22T16:32:38 |
| Documents scored | 10 |
| Mode | hybrid |
| Model | gemini-3.5-flash |
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
| L01.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.01058 | 2,582/745 | 1 |
| L02.jpg | image | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.01303 | 2,245/1,074 | 1 |
| L03.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.01064 | 2,716/730 | 1 |
| L04.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.03065 | 4,604/2,638 | 1 |
| L05.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.01541 | 2,856/1,236 | 1 |
| L06.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.01014 | 2,702/676 | 1 |
| L07.pdf | digital_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.00890 | 2,603/555 | 1 |
| L08.pdf | digital_pdf | ok | no | ✓ | - | - | - | - | - | - | - | $0.00646 | 2,697/268 | 1 |
| L09.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.01236 | 2,245/999 | 1 |
| L10.pdf | scanned_pdf | ok | no | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | $0.01286 | 2,217/1,059 | 1 |

#### Accuracy by source type

| Source type | Docs | All fields correct | Field accuracy | Avg cost |
| --- | ---: | ---: | ---: | ---: |
| digital_pdf | 7 | 7/7 | 100% | $0.01325 |
| image | 1 | 1/1 | 100% | $0.01303 |
| scanned_pdf | 2 | 2/2 | 100% | $0.01261 |

#### Cost per document

| Cost metric | Value |
| --- | ---: |
| Average cost per document | $0.01310 |
| Average input tokens per document | 2,747 |
| Average output tokens per document | 998 |
| Total spend for this run | $0.131 |
| Documents that needed a retry or escalation | 0/10 |
| Documents that failed outright | 0/10 |
| Average latency per document | 14.4s |

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
