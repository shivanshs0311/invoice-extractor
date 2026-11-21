import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


@pytest.fixture(autouse=True)
def no_real_api_key(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
