import json
import shutil
import time

from orchestrate.cli import main

from .conftest import EXAMPLES, git

LAND_FAKE = """#!/usr/bin/env bash
case $1 in
  describe) echo '{"forge": "fake"}' ;;
  auth) exit 0 ;;
  merge) echo "land merge $2" >>"$FAKE_LOG" ;;
  land) git -C "$2" push -q origin "$4:refs/heads/$3" && echo "LANDED PR #1 SUCCESSFUL $4" ;;
esac
"""


def test_one_unit_from_start_to_merge(fake_env, project, monkeypatch, capsys):
    ws, wt, cfg = project["ws"], project["worktree"], str(project["config"])
    project["config"].write_text(project["config"].read_text() + "[timeouts]\nidle_seconds = 0\n")
    assert main(["scaffold", "--repo", str(project["repo"])]) == 0
    shutil.copy(EXAMPLES / "harness-agy", ws / "adapters" / "harness-agy")
    land = ws / "adapters" / "land-fake"
    land.write_text(LAND_FAKE)
    land.chmod(0o755)
    monkeypatch.setenv("FAKE_AGENT_STATUS", "idle")
    monkeypatch.setenv("FAKE_ANSWER", "clean")

    assert main(["--config", cfg, "start", "A-1", "--worktree", str(wt), "--plan", "m1.md"]) == 0
    git(wt, "config", "user.email", "t@example.com")
    git(wt, "config", "user.name", "T")
    (wt / "feature.py").write_text("x = 1\n")
    git(wt, "add", "feature.py")
    git(wt, "commit", "-qm", "feature")
    summary = wt / "scratch" / "units" / "A-1.md"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text("# A-1\nbuilt feature.py\n")

    main(["--config", cfg, "supervise", "--once"])
    unit = json.loads((ws / "units.json").read_text())["A-1"]
    assert unit["status"] == "reviewing"
    assert {item["role"] for item in unit["required"]} == {"reviewer", "second_reviewer"}
    (wt / "scratch" / "units" / "A-1-reviewer.md").write_text("clean\n")

    deadline = time.time() + 30
    while time.time() < deadline:
        main(["--config", cfg, "supervise", "--once"])
        unit = json.loads((ws / "units.json").read_text())["A-1"]
        if unit["status"] not in ("reviewing", "landing"):
            break
        time.sleep(0.5)
    assert unit["status"] == "merged", unit.get("event")
    assert (wt / "scratch" / "units" / "A-1-second_reviewer.md").read_text().strip() == "clean"
    assert "land merge 1" in fake_env.read_text()
    assert (ws / "logs" / "units" / "A-1" / "unit.json").exists()
    events = (ws / "logs" / "events.jsonl").read_text()
    assert "merged PR #1" in events
    assert not (project["repo"].parent / "myapp-review-a-1-second-reviewer").exists()
