"""Runtime settings. Everything is read from environment variables (and .env).

No secrets live in the repo. Put your key in .env, which is git-ignored.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

VALID_MODES = ("auto", "text", "vision", "hybrid")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # --- LLM ---------------------------------------------------------------
    provider: str = "gemini"
    model: str = "gemini-3.5-flash-lite"  # first pass: cheap and fast
    escalation_model: str = "gemini-3.5-flash"  # second pass: only when a check fails
    mode: str = "auto"  # auto | text | vision | hybrid
    escalate: bool = True  # allow one retry (on the stronger model; falls back to the first-pass model)
    max_output_tokens: int = 4096
    timeout_s: float = 120.0
    api_attempts: int = 5  # transient API errors: 1 try + 4 retries with backoff (3s, 6s, 12s, 24s)
    api_backoff_s: float = 3.0

    # --- Ingestion ---------------------------------------------------------
    max_file_mb: float = 20.0
    max_pages: int = 6  # pages rendered to images per document
    max_text_chars: int = 60_000
    max_image_edge: int = 1600  # longest edge of rendered page images, in px
    jpeg_quality: int = 88
    min_text_chars_per_page: int = 80  # below this we treat the text layer as missing
    scan_image_coverage: float = 0.6  # page area covered by one image => scanned page

    # --- Validation --------------------------------------------------------
    # Absolute, in currency units. Printed amounts are exact to the cent: the 9 labelled invoices and all 17 extracted
    # invoices in the sample pack reconcile to 0.00, and a looser value hid a 0.80 misread digit in the stress test.
    # The prompt creates no items for "round off" lines, so an invoice that prints one fails this check and is flagged.
    total_tolerance: float = 0.05
    min_confidence: float = 0.7  # self-reported confidence below this => needs_review

    def with_overrides(self, **kwargs) -> Settings:
        clean = {k: v for k, v in kwargs.items() if v is not None}
        return replace(self, **clean) if clean else self


def load_settings(**overrides) -> Settings:
    """Build Settings from the environment, then apply explicit overrides."""
    base = Settings(
        provider=os.getenv("LLM_PROVIDER", Settings.provider),
        model=os.getenv("EXTRACT_MODEL", Settings.model),
        escalation_model=os.getenv("ESCALATION_MODEL", Settings.escalation_model),
        mode=os.getenv("EXTRACT_MODE", Settings.mode),
        escalate=_bool("ESCALATE", Settings.escalate),
        timeout_s=float(os.getenv("REQUEST_TIMEOUT_S", Settings.timeout_s)),
        api_attempts=int(os.getenv("API_ATTEMPTS", Settings.api_attempts)),
        max_pages=int(os.getenv("MAX_PAGES", Settings.max_pages)),
        max_image_edge=int(os.getenv("MAX_IMAGE_EDGE", Settings.max_image_edge)),
        max_file_mb=float(os.getenv("MAX_FILE_MB", Settings.max_file_mb)),
        total_tolerance=float(os.getenv("TOTAL_TOLERANCE", Settings.total_tolerance)),
    )
    settings = base.with_overrides(**overrides)
    if settings.mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}, got {settings.mode!r}")
    return settings
