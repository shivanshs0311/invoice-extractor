"""Orchestration: ingest -> LLM -> validate -> (retry once, on the stronger model if available) -> flag.

Contract: `extract_document` never raises for a bad document. A document that cannot be processed
comes back as an all-null record with needs_review=true and an `error`, so a batch always finishes
and nothing wrong is passed on silently. The only exception raised is a configuration problem
(for example a missing API key), because retrying that on every file would be pointless.
"""
from __future__ import annotations

import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from collections.abc import Callable

from .config import Settings, load_settings
from .cost import cost_usd
from .ingest import IngestError, LoadedDocument, load_document
from .llm import LLMClient, LLMError, Usage, call_with_retries, make_client
from .prompts import PROMPT_SHA, PROMPT_VERSION, SYSTEM_PROMPT, build_content
from .schema import EXTRACTION_TOOL_SCHEMA, PUBLIC_FIELDS, Invoice, null_invoice_dict
from .validate import feedback_for_checks, feedback_for_schema, is_unreadable, normalise_tax, parse_extraction, run_checks


# If the stronger model cannot be used (daily quota, outage, timeout), the retry still has value, because
# its real additions are the quoted check failures and the page images. So it runs once on the first-pass model.
FALLBACK_KINDS = ("quota", "rate_limit", "server_error", "timeout")

# A second model will not fix a bad key, a malformed request or a dead network.
NO_RETRY_KINDS = ("auth", "bad_request", "connection")


@dataclass
class Step:
    mode: str  # text | vision | hybrid
    model: str


@dataclass
class ExtractionResult:
    output: dict  # public schema fields + needs_review + review_reasons (+ error on failure)
    meta: dict  # tokens, cost, route, attempts, checks, warnings

    @property
    def status(self) -> str:
        return self.meta["status"]  # ok | needs_review | failed

    def public_json(self, with_review: bool = False) -> dict:
        """The JSON deliverable. By default exactly the 8 fields of schema.json (which forbids extra keys).

        with_review adds needs_review and review_reasons (an extension beyond the schema). A failed extraction
        always carries its `error` object: that record is deliberately not schema-valid, so a failed read can
        never be mistaken for a genuine "not an invoice".
        """
        out = {name: self.output.get(name) for name in PUBLIC_FIELDS}
        if self.output.get("error"):
            out["error"] = self.output["error"]
        if with_review:
            out["needs_review"] = self.output.get("needs_review")
            out["review_reasons"] = self.output.get("review_reasons")
        return out


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
def _coerce_mode(doc: LoadedDocument, mode: str) -> str:
    if doc.kind == "image" or not doc.has_text:
        return "vision"
    return mode


def plan_steps(doc: LoadedDocument, settings: Settings) -> list[Step]:
    """Decide which representation and model to try, in order.

    auto: clean digital PDFs go text-only first (cheap, exact digits). Scans and photos go vision.
          If the checks fail, the retry uses the stronger model, and for digital PDFs it also adds the
          page images (hybrid) so the model can see the layout.
    text / vision / hybrid: forced representation, used for ablations. The retry keeps the same one.
    """
    if settings.mode == "auto":
        if doc.kind == "image" or doc.is_scan or not doc.text_ok:
            first, second = "vision", "vision"
        else:
            first, second = "text", "hybrid"
    else:
        first = _coerce_mode(doc, settings.mode)
        second = first
    steps = [Step(first, settings.model)]
    if settings.escalate:
        steps.append(Step(second, settings.escalation_model))
    return steps


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def extract_document(
    path: str | Path,
    settings: Optional[Settings] = None,
    client: Optional[LLMClient] = None,
) -> ExtractionResult:
    settings = settings or load_settings()
    started = time.perf_counter()

    try:
        doc = load_document(path, settings)
    except IngestError as exc:
        return _failed(exc.code, exc.message, started)
    except Exception as exc:  # defensive: a parser bug must not kill a batch
        return _failed("internal_error", f"{type(exc).__name__}: {exc}", started, detail=traceback.format_exc())

    if client is None:
        client = make_client(settings)  # may raise LLMError for a missing key: configuration, so let it surface

    try:
        return _run(doc, settings, client, started)
    except Exception as exc:
        return _failed(
            "internal_error",
            f"{type(exc).__name__}: {exc}",
            started,
            source_type=doc.source_type,
            warnings=doc.warnings,
            detail=traceback.format_exc(),
        )


def extract_many(
    paths: list[Path],
    settings: Optional[Settings] = None,
    client: Optional[LLMClient] = None,
    workers: int = 4,
    progress: Optional[Callable[[int, Path, ExtractionResult], None]] = None,
) -> list[ExtractionResult]:
    """Run many documents concurrently. Results are returned in input order."""
    settings = settings or load_settings()
    if client is None and paths:
        client = make_client(settings)
    results: list[Optional[ExtractionResult]] = [None] * len(paths)
    pool = ThreadPoolExecutor(max_workers=max(1, workers))
    try:
        futures = {pool.submit(extract_document, p, settings, client): i for i, p in enumerate(paths)}
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            if progress:
                progress(i, paths[i], results[i])  # type: ignore[arg-type]
        pool.shutdown(wait=True)
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            print(
                "\nStopping: queued documents are cancelled. Calls already running finish first "
                f"(at most {settings.timeout_s:.0f}s each).",
                file=sys.stderr,
                flush=True,
            )
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    return results  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _run(doc: LoadedDocument, settings: Settings, client: LLMClient, started: float) -> ExtractionResult:
    """Try each planned step until one passes every error-level check, then build the result."""
    steps = plan_steps(doc, settings)
    attempts: list[dict] = []
    candidates: list[tuple] = []  # (extraction, report, attempt_number)
    usage = Usage()
    feedback: Optional[str] = None
    previous: Optional[dict] = None
    max_tokens = settings.max_output_tokens
    last_error: Optional[LLMError] = None
    fell_back = False

    # A for loop over a list sees items appended during the loop, which is how the fallback step gets run.
    for number, step in enumerate(steps, start=1):
        rec = _new_attempt(number, step)
        attempts.append(rec)
        try:
            result, retries = _call_model(client, doc, step, settings, feedback, previous, max_tokens)
        except LLMError as exc:
            rec.update(status="api_error", error=f"{exc.kind}: {exc}")
            last_error = exc
            if exc.kind == "truncated":
                max_tokens *= 2
            if exc.kind in NO_RETRY_KINDS:
                break
            if not fell_back and _can_fall_back(exc, step, attempts, settings):
                steps.append(Step(step.mode, settings.model))
                fell_back = True
            continue

        usage = usage + result.usage
        rec.update(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cost_usd=cost_usd(step.model, result.usage),
            latency_s=round(result.latency_s, 3),
            api_retries=retries,
        )

        ext, problems = parse_extraction(result.data)
        if ext is None:
            rec.update(status="schema_invalid", failed_checks=["schema_valid"], error="; ".join(problems[:5]))
            feedback, previous = feedback_for_schema(problems), result.data
            continue

        ext, normalised = normalise_tax(ext, settings.total_tolerance)
        rec["normalised"] = normalised
        report = run_checks(ext, settings, doc.warnings)
        rec.update(status="ok" if report.passed else "checks_failed", failed_checks=[c.name for c in report.failing])
        candidates.append((ext, report, number))
        if report.passed:
            break
        feedback, previous = feedback_for_checks(report), result.data

    return _finish(doc, settings, started, attempts, candidates, usage, last_error)


def _new_attempt(number: int, step: Step) -> dict:
    """One row of meta["attempts"]: what was tried and what it cost."""
    return {
        "attempt": number,
        "mode": step.mode,
        "model": step.model,
        "status": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": None,
        "latency_s": 0.0,
        "api_retries": 0,
        "failed_checks": [],
        "normalised": [],
        "error": None,
    }


def _call_model(client, doc, step, settings, feedback, previous, max_tokens):
    """One model call, with transient API errors retried. Returns (LLMResult, api_retries)."""
    content = build_content(doc, step.mode, feedback, previous)
    return call_with_retries(
        lambda: client.extract(
            model=step.model,
            system=SYSTEM_PROMPT,
            content=content,
            tool_schema=EXTRACTION_TOOL_SCHEMA,
            max_tokens=max_tokens,
        ),
        attempts=settings.api_attempts,
        backoff_s=settings.api_backoff_s,
        label=step.model,
    )


def _can_fall_back(exc: LLMError, step: Step, attempts: list[dict], settings: Settings) -> bool:
    """Retry on the first-pass model when the stronger one is unavailable, if the first-pass model has answered."""
    first_pass_answered = any(a["status"] != "api_error" for a in attempts)
    return first_pass_answered and step.model != settings.model and exc.kind in FALLBACK_KINDS


def _finish(doc, settings, started, attempts, candidates, usage, last_error) -> ExtractionResult:
    """Turn the attempts into the final result: a failure, an unreadable document, or an invoice."""
    common = dict(source_type=doc.source_type, warnings=doc.warnings, attempts=attempts, usage=usage)
    if not candidates:
        code = f"api_{last_error.kind}" if last_error else "invalid_output"
        message = str(last_error) if last_error else "The model returned output that never matched the schema."
        return _failed(code, message, started, **common)

    # Prefer the attempt with the fewest failed error-level checks; on a tie prefer the later (stronger) one.
    ext, report, number = min(candidates, key=lambda c: (len(c[1].errors), -c[2]))
    chosen = attempts[number - 1]

    if is_unreadable(ext, report, settings):
        # Not a genuine "not an invoice": the model could not read it. Say so instead of returning
        # nulls (or invented values) that look like a real answer.
        message = (
            "The model rates this scan as poor and its result is not trustworthy "
            f"(is_invoice={ext.is_invoice}, confidence={ext.confidence:.2f}, "
            f"failed checks: {[c.name for c in report.errors] or 'none'}). Send a clearer scan."
        )
        result = _failed("unreadable_document", message, started, **common)
        result.meta.update(_model_meta(ext, report, chosen))
        return result

    output = Invoice.from_extraction(ext).to_json_dict()
    reasons = report.review_reasons
    output["needs_review"] = bool(reasons)
    output["review_reasons"] = reasons
    meta = _base_meta(status="needs_review" if reasons else "ok", started=started, **common)
    meta.update(_model_meta(ext, report, chosen), normalisations=chosen["normalised"])
    return ExtractionResult(output=output, meta=meta)


def _model_meta(ext, report, attempt: dict) -> dict:
    """What the chosen attempt said about the document, for meta."""
    return {
        "final_mode": attempt["mode"],
        "model": attempt["model"],
        "document_type": ext.document_type,
        "legibility": ext.legibility,
        "model_confidence": ext.confidence,
        "notes": ext.notes,
        "checks": [c.to_dict() for c in report.checks],
    }


def _base_meta(
    *,
    status: str,
    started: float,
    attempts: list[dict],
    usage: Usage,
    source_type: Optional[str],
    warnings: Optional[list[str]],
) -> dict:
    costs = [a["cost_usd"] for a in attempts if a["input_tokens"] or a["output_tokens"]]
    total_cost = None if any(c is None for c in costs) else round(sum(costs), 8)
    return {
        "status": status,
        "source_type": source_type,
        "final_mode": None,
        "model": None,
        "document_type": None,
        "legibility": None,
        "model_confidence": None,
        "notes": None,
        "checks": [],
        "attempts": attempts,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": total_cost,
        "latency_s": round(time.perf_counter() - started, 3),
        "warnings": warnings or [],
        "prompt_version": PROMPT_VERSION,
        "prompt_sha": PROMPT_SHA,
        "error": None,
    }


def _failed(
    code: str,
    message: str,
    started: float,
    *,
    source_type: Optional[str] = None,
    warnings: Optional[list[str]] = None,
    attempts: Optional[list[dict]] = None,
    usage: Optional[Usage] = None,
    detail: Optional[str] = None,
) -> ExtractionResult:
    output = null_invoice_dict()
    output["needs_review"] = True
    output["review_reasons"] = [f"extraction_failed:{code}"]
    output["error"] = {"code": code, "message": message}
    meta = _base_meta(
        status="failed",
        started=started,
        attempts=attempts or [],
        usage=usage or Usage(),
        source_type=source_type,
        warnings=warnings,
    )
    meta["error"] = {"code": code, "message": message, **({"detail": detail} if detail else {})}
    return ExtractionResult(output=output, meta=meta)
