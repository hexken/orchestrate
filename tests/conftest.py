import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FAKES = ROOT / "tests" / "fakes"
EXAMPLES = ROOT / "examples" / "adapters"


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    log = tmp_path / "calls.log"
    monkeypatch.setenv("PATH", f"{FAKES}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("AGY_SKILLS_HOME", str(tmp_path / "agy-skills"))
    return log
