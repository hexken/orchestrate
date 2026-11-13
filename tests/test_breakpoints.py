import json

from orchestrate import breakpoints
from orchestrate.cli import main
from orchestrate.registry import Workspace

from .test_cli import start

PLAN = """# Work units

| ID | Name | Milestone | Size |
|---|---|---|---|
| M1-A | First | 1 | S |
| M1-B | Second | 1 | M |
| M2-C | Third | 2 | S |
"""


def orch(project, *args):
    return main(["--config", str(project["config"]), *args])


def set_units(project, **statuses):
    ws = Workspace(project["ws"])
    units = {
        k: {"unit": k, "status": v, "worktree": f"/w/{k}", "branch": k} for k, v in statuses.items()
    }
    ws.save(units)


def test_breakpoint_blocks_other_units_until_passed(fake_env, project, capsys):
    assert orch(project, "breakpoint", "add", "review-a", "--after", "A-1") == 0
    assert start(project, "B-1") == 2
    assert "breakpoint review-a is pending" in capsys.readouterr().err
    assert orch(project, "breakpoint", "pass", "review-a") == 0
    assert start(project, "B-1") == 0


def test_unit_the_breakpoint_waits_for_may_start(fake_env, project):
    orch(project, "breakpoint", "add", "review-a", "--after", "A-1")
    assert start(project, "A-1") == 0


def test_supervisor_reports_reached_once(fake_env, project, capsys):
    orch(project, "breakpoint", "add", "review-a", "--after", "A-1")
    set_units(project, **{"A-1": "landing"})
    ws = Workspace(project["ws"])
    assert breakpoints.reached(ws, ws.load()) == []
    set_units(project, **{"A-1": "merged"})
    capsys.readouterr()
    orch(project, "supervise", "--once")
    out = capsys.readouterr().out
    assert "EVENT: - breakpoint review-a reached" in out
    orch(project, "supervise", "--once")
    assert "breakpoint review-a reached" not in capsys.readouterr().out


def test_milestone_breakpoint_added_on_first_start(fake_env, project, capsys):
    plan = project["repo"] / "work-units.md"
    plan.write_text(PLAN)
    text = project["config"].read_text().replace("[land]", f'work_plan = "{plan}"\n[land]')
    project["config"].write_text(text)
    assert start(project, "M1-A") == 0
    points = json.loads((project["ws"] / "breakpoints.json").read_text())
    assert points["milestone-1"]["after"] == ["M1-A", "M1-B"]
    assert start(project, "M2-C") == 2
    assert "milestone-1 is pending" in capsys.readouterr().err


def test_plan_units_parses_table(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN)
    assert breakpoints.plan_units(plan) == {"M1-A": "1", "M1-B": "1", "M2-C": "2"}
