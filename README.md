# Invoice extraction pipeline

[![tests](https://github.com/shivanshs0311/invoice-extractor/actions/workflows/tests.yml/badge.svg)](https://github.com/shivanshs0311/invoice-extractor/actions/workflows/tests.yml)

Reads a vendor invoice (digital PDF, scanned PDF or phone photo) and returns validated JSON in the assignment schema.
It checks its own work, flags documents a human should look at, and measures itself with a one-command eval.
It runs on Google Gemini, and the free tier of a Google AI Studio key is enough to run everything here.

```
python extract.py data/sample_pack/labelled/L01.pdf --out out.json
python eval.py
```

The written report is in [REPORT.md](REPORT.md).

## Results at a glance

| What | Result |
| --- | --- |
| Labelled documents (10) | 10 of 10 fully correct, 100% on every field, in 3 separate runs |
| Prompt tuning | one prompt version (v1), never edited after an eval run |
| Cost per document | $0.00165 at list price (1,867 input and 437 output tokens). Running the stronger model on everything would cost about 8 times more for the same accuracy |
| Damaged scans (stress set, 30) | 14 correct; the 10 unreadable ones return an explicit `unreadable_document` error instead of a guess |
| Review flag (stress set) | 79% precision, 94% recall: flagged documents hold 98% of the wrong fields |
| Tests | 173, no API key needed, run on every push |

Three commands cover everything: `python extract.py <file>` (one document), `python eval.py` (the eval table) and
`python -m uvicorn server:app --port 8000` (upload a document in the browser at http://127.0.0.1:8000).

## Quick start

Needs Python 3.10 or newer and a Gemini API key. A free key (no card) comes from https://aistudio.google.com/apikey

```bash
git clone <this repo> && cd invoice-extractor
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                 # Windows: copy .env.example .env
```

Open `.env` and put your key after `GEMINI_API_KEY=`. Then download the sample pack and unzip it into `data/sample_pack/`
so it looks like this (see [data/README.md](data/README.md)):

```
data/sample_pack/
  README.md  schema.json
  labelled/    L01.pdf L01.json  L02.jpg L02.json ... L10.pdf L10.json
  unlabelled/  U01.pdf U02.jpg ... U10.pdf
```

`data/` is git-ignored on purpose, because the assignment says not to publish the documents.

### Run the extractor

```bash
# one document, JSON on stdout (logs go to stderr)
python extract.py data/sample_pack/labelled/L01.pdf > out.json

# Windows PowerShell 5 writes UTF-16 when you use ">", so prefer --out there
python extract.py data/sample_pack/labelled/L01.pdf --out out.json

# all 20 documents (labelled and unlabelled): one JSON each in outputs/, plus outputs/_run_log.json with the
# review flags, tokens, cost and status per file
python extract.py data/sample_pack --out-dir outputs
```

Useful flags: `--meta` (adds tokens, cost, checks and attempts under `_meta`), `--with-review` (adds `needs_review` and
`review_reasons` to each JSON), `--mode auto|text|vision|hybrid`, `--model`, `--escalation-model`, `--no-escalate`, `--workers N`.

Exit code: 0 for ok or needs_review, 2 when a single document failed completely, 1 for configuration problems.

### Run the eval (one command)

```bash
python eval.py
```

Runs the extractor on every labelled document, compares field by field, and prints the results table, a per-document grid,
accuracy by source type, cost, a review-flag check and every error with an automatic cause hint. It also saves everything to
`reports/runs/default/`.

```bash
python eval.py --write-report        # also refreshes the results block inside REPORT.md
python eval.py --reuse               # re-score saved predictions without calling the API (after editing matching rules)
python eval.py --tag run2            # a repeat run, saved separately, to see how stable the numbers are
python scripts/ablation.py           # text vs vision vs hybrid in one table
python scripts/stress.py             # writes data/stress/: damaged copies of the labelled documents
python eval.py --data-dir data/stress --tag stress
python scripts/preflight.py          # pre-submission checklist
```

### Frontend (bonus)

```bash
python -m uvicorn server:app --port 8000
```

Open http://127.0.0.1:8000 and drop a document. You see:

- the original next to the extracted fields, the "does it add up" check and why a document needs review;
- for a file that could not be read: what happened, why, and what to do, in plain words (technical details are folded away);
- a **History** tab with every earlier upload: search by file, vendor or invoice number, filter by Passed, Needs review or Failed,
  reopen any record next to its original file, download its JSON, or delete it.

History is stored in `data/history/` (a SQLite file plus the uploaded files). That folder is git-ignored because invoices are
confidential. Set `HISTORY_DIR` to keep it somewhere else.

### Tests

```bash
pip install -r requirements-dev.txt
pytest -q          # no API key or network needed
```

The LLM client is tested against a local fake HTTP server, so the real Google SDK code path runs without a key.

## How it works

```
file --> ingest --> LLM (JSON schema forced) --> schema check --> sanity + totals checks --> output JSON
          |                  ^                                          |
          |                  +---- one retry with the failed checks -----+
          |                        (stronger model, text + images)
          +- bad input? fail fast, no API call, flagged record
```

1. **Ingest.** File type comes from magic bytes, not the extension. Digital PDFs yield layout-preserving text (table rows stay
   on one line). Scans, photos and image-dominated PDFs are rendered to page images (EXIF rotation fixed, capped at 1600 px).
2. **Extract.** One LLM call whose only allowed output is JSON matching a schema (`response_mime_type` plus `response_schema`).
   Clean digital PDFs go in as text (cheap, exact digits). Scans go in as images. No sampling parameters are sent, so the model defaults apply.
3. **Validate.** Pydantic schema, then arithmetic and sanity checks (table below).
4. **Retry or flag.** An error-level failure triggers one retry, with the failed checks quoted back and, for digital PDFs, the page
   images added. The retry uses the stronger model, or the first-pass model when the stronger one is unavailable (see "Free tier").
   If it still fails, the record is returned but flagged `needs_review` with reasons. Bad data is never passed on silently.

### Why this design

| Choice | Reason |
| --- | --- |
| Gemini 3.5 Flash-Lite first, Gemini 3.5 Flash on retry | Most documents are easy, so the cheap model handles them. The stronger model is only used when a check fails. Prices live in `pricing.json`. |
| Text layer for digital PDFs, images for scans | A text layer gives exact digits for a fraction of the tokens. Scans have no text, so vision is the only route. `--mode` forces either one so the report can show the trade-off with real numbers. |
| Forced JSON schema | The reply is always a JSON object, so there is no free-text parsing. Pydantic still validates it, because a schema-shaped answer can have a wrong value. |
| Public schema separate from the LLM schema | The model also returns `document_type`, `legibility`, `confidence`, `notes`. They feed validation and review flags and are stripped from the public output. |
| Own retry loop, SDK retries off | Every retry is counted, printed to the terminal and visible in the run log. |
| Document text treated as untrusted | The system prompt says to never follow instructions found inside a document. |

The full list of decisions, each with the alternative it was chosen over (including dedicated invoice APIs, OCR plus templates,
and the database for the history), is in [REPORT.md section 2.8](REPORT.md).

### Free tier

The default models work on a free AI Studio key, with these limits:

- Google caps the stronger model at a small number of requests per day on the free tier (20 per day when this was checked on 2026-11-21).
  A daily quota error is not retried, because waiting cannot fix it. The pipeline runs the one retry on the first-pass model instead,
  still with the failed-check feedback and the page images. A paid key uses the stronger model as designed.
- Short outages ("503 high demand") and per-minute limits (429) are retried with exponential backoff and jitter, and every retry prints a line.
- If you still see many 429s, run with `--workers 1`.

### Validation checks

| Check | Severity | What it does |
| --- | --- | --- |
| schema_valid | error, retry | JSON must parse and match the schema, dates must be `YYYY-MM-DD`, currency a 3 letter code |
| document_type_consistent | error, retry | `is_invoice` must agree with `document_type` |
| core_fields_present | error, retry | vendor, invoice number, date, total and at least one line item |
| totals_reconcile | error, retry | `sum(line amounts) + tax_total` must equal `total` within an absolute tolerance of 0.05 (cent rounding only; an invoice with a printed "round off" line fails this check and is flagged for review) |
| totals_unverifiable, currency_known, date_plausible, tax_plausible, legibility_good, confidence_ok, input_quality_ok | warn, flag | suspicious but not provably wrong, so no retry, but `needs_review` is set |

### Bad inputs

| Input | Result |
| --- | --- |
| Not an invoice (PO, bank statement, cover letter) | `is_invoice: false`, every other field `null`, enforced in code even if the model leaks values |
| Missing, empty, oversize, corrupt, truncated, password-protected, blank or unsupported file | Fails before any API call with a specific error code. A record with `needs_review: true` and an `error` object is written, and the batch continues |
| API timeouts, 429s, 5xx | Retried with exponential backoff and jitter (honours Google's suggested wait), then a flagged failed record. A daily quota error is not retried |
| Model output that never matches the schema, refusals, truncated output | Retried once, then a flagged failed record. Truncation doubles the output limit on the retry |
| A scan the model rates "poor" whose result cannot be trusted (it says "not an invoice", fails an error check, or reports confidence below 0.7) | A failed record with `error.code` `unreadable_document`, not a silent `is_invoice: false`. A poor scan that still reads as a confident, consistent invoice is kept and flagged |
| Bad key or bad request | Fails immediately, no point trying a second model |

The extra bad-input case chosen for the assignment is **damaged or unreadable files plus API failure**. Details and tests are in
`tests/test_ingest.py`, `tests/test_pipeline.py` and `tests/test_llm.py`.

### Output shape

Each file in `outputs/` is exactly the 8 fields of the assignment's `schema.json`, which forbids extra keys. The bonus review flag therefore
lives in `outputs/_run_log.json` (`needs_review` and `review_reasons` per file), or inside each JSON when you pass `--with-review`.

```json
{
  "is_invoice": true,
  "vendor": "Acme Supplies Pvt Ltd",
  "invoice_number": "INV-2041",
  "invoice_date": "2026-03-14",
  "currency": "INR",
  "line_items": [{ "description": "A4 paper, 500 sheets", "quantity": 10, "amount": 3200.0 }],
  "tax_total": 576.0,
  "total": 3776.0
}
```

A failed extraction (damaged file, API down, unreadable scan) is the one deliberate exception: every field is `null` and an `error` object is added, so the
record is not schema-valid. That is on purpose. A failed read must never look like a genuine "not an invoice".

Labelling conventions the model follows are taken from the sample pack's own README: the seller's name as printed at the top; the issue date;
line items are the rows of the item table in printed order, with `amount` the row total before tax; charge rows and discount rows of the
table are items too, and a discount is negative; `tax_total` is the sum of all tax lines and is **0** (not null) when no tax is printed;
`total` is the final amount payable. If the model answers null for tax but the line items already add up to the total, the pipeline records 0
and notes it in `outputs/_run_log.json`. Adjustments that appear only in the totals block, below the table, are not items, so such an invoice
will not reconcile and is flagged for review.

### Eval matching rules

| Field | Rule |
| --- | --- |
| is_invoice | exact boolean |
| vendor | case, accents, punctuation and legal suffixes (Pvt, Ltd, LLC, GmbH...) ignored. Match if equal, or one name's words are a subset of the other's ("Acme" vs "Acme Pvt Ltd"), or similarity is at least 0.88 |
| invoice_number | case-insensitive, ignoring spaces and punctuation. Leading zeros still matter |
| invoice_date | exact ISO date |
| currency | exact ISO code after mapping symbols (Rs and the rupee sign to INR, $ to USD, and so on) |
| tax_total | numeric within 0.01. The pack says no tax is `0`, so `null` does not match `0` |
| total | numeric within 0.01. `null` only matches `null`. `"1,200.00"` equals `1200` |
| line_items | items are matched one to one. An item matches when amount is within 0.01, quantity agrees (only when the label has one) and description similarity is at least 0.6. Reported as item-level F1, amount-only F1 (ignores wording) and a strict flag (every item right) |

Field rows are computed over labelled invoices only, so non-invoices do not inflate them. `is_invoice` and the whole-document row use all
labelled documents. A document that failed completely counts as wrong everywhere. Matching lives in `invoice_extractor/matching.py`.

### Cost

Tokens come from the `usage` field of every API response. Hidden "thinking" tokens are billed as output by Google, so they are counted as output.
Cost per call is `input_tokens x input price + output tokens x output price`, with per-million-token list prices from `pricing.json`
(source and check date are recorded in that file). Document cost is the sum over all attempts, so retries are included. Nothing is estimated from text length.
On the free tier the actual bill is $0, so the figures in the report are what the same calls would cost at list price on a paid key.

## Project layout

```
extract.py               CLI: one file or a folder
eval.py                  one-command eval
server.py, frontend/     FastAPI app and the upload page (bonus)
schema.json              the assignment's output schema (every output is validated against it)
pricing.json             model prices (USD per million tokens, list price)
invoice_extractor/
  config.py              settings from env
  schema.py              Pydantic models and the JSON schema sent to the model
  prompts.py             system prompt, request builder, PROMPT_VERSION
  ingest.py              type sniffing, PDF text, scan detection, rendering, bad-input errors
  llm.py                 client interface, Gemini implementation, retry with backoff
  validate.py            schema and totals checks, review reasons
  pipeline.py            orchestration, retry and fallback, graceful failure
  explain.py             plain-language text for every error code and review reason
  history.py             upload history (SQLite) used by the API
  matching.py            eval matching rules
  evaluate.py            scoring, aggregation, tables, REPORT.md updater
  data_io.py             finds documents and labels in any folder layout
scripts/                 ablation, stress test and preflight check
tests/                   unit tests, including the real SDK against a local fake server
outputs/                 JSON for all 20 documents (written by extract.py)
reports/                 eval runs (reports/runs/<tag>/results.md, predictions/)
```

To use another LLM provider, add a class with the same `extract()` signature as `GeminiClient` in `llm.py` and register it in `make_client`.

## Security and confidentiality

- No keys are committed. `.env` is git-ignored and `.env.example` has an empty value. `python scripts/preflight.py` scans the files and the git history for keys.
- The sample documents and labels live in `data/`, which is git-ignored. Keep this repository private and share access only with the reviewers.
- Document text is untrusted input. It is sent as data, never executed, and the frontend renders it with `textContent` only.

## Known limitations

See "Known limitations" in [REPORT.md](REPORT.md). The main one: the totals check catches arithmetic mistakes, not a wrong but
self-consistent vendor, invoice number or date, so those can pass without a flag. Model output is not fully deterministic, so repeat
runs can differ slightly; `python eval.py --tag run2` measures that.
