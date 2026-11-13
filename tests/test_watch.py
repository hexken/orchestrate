import time
from pathlib import Path

from orchestrate.config import Review
from orchestrate.registry import Workspace
from orchestrate.watch import render


def test_render(tmp_path):
    ws = Workspace(tmp_path)
    ws.logs.mkdir()
    review = tmp_path / "A-1-reviewer.md"
    review.write_text("Verdict: changes needed\n")
    land = ws.logs / "a-1-land-1.out"
    land.write_text("pushing\nwaiting for build\n")
    (ws.logs / "push-agent-a-1-h1.log").write_text("=== 10:00:00 check 1: pytest\nok\n")
    now = time.time()
    unit = {
        "unit": "A-1",
        "status": "reviewing",
        "branch": "agent/a-1",
        "timeline": [[f"2026-01-01 10:0{i}:00", f"mark {i}"] for i in range(7)],
        "required": [
            {"path": str(review), "role": "reviewer", "kind": "review"},
            {"path": str(tmp_path / "none.md"), "role": "second_reviewer", "kind": "review"},
        ],
        "jobs": {"land": {"log": str(land), "started": now - 125}},
    }
    lines = render(unit, ws, Review(), now)
    assert lines[0].startswith("A-1   REVIEWING   agent/a-1   pr -")
    assert lines[1:6] == [f"10:0{i} mark {i}" for i in range(2, 7)]
    assert "reviewer review: hold" in lines
    assert "second_reviewer review: pending" in lines
    assert "land running 2m05s: waiting for build" in lines
    assert "push 10:00:00 check 1: pytest" in lines
    assert not Path(tmp_path / "none.md").exists()
