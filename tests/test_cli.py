import fcntl
import json
import subprocess
import time

from orchestrate.cli import main

from .conftest import git


def start(project, unit="A-1"):
    return main(
        [
            "--config",
            str(project["config"]),
            "start",
            unit,
            "--worktree",
            str(project["worktree"]),
            "--plan",
            "m1.md",
        ]
    )


def test_start_records_unit_and_branch(fake_env, project):
    assert start(project) == 0
    unit = json.loads((project["ws"] / "units.json").read_text())["A-1"]
    origin_main = git(project["repo"], "rev-parse", "--short", "origin/main")
    assert unit["status"] == "building"
    assert unit["branch"] == "agent/a-1"
    assert unit["base"] == origin_main
    assert git(project["worktree"], "branch", "--show-current") == "agent/a-1"
    assert unit["tab"] == "t1" and unit["pane"] == "p1" and unit["session"] == "sess-1"
    brief = project["worktree"] / "scratch" / "a-1-brief.txt"
    assert brief.read_text() == f"Build A-1 on agent/a-1 from {origin_main}.\n"
    assert (project["ws"] / "plans" / "m1.md").exists()
    assert "herdr agent start a-1 --kind claude --pane p1" in fake_env.read_text()


def test_start_refuses_busy_worktree(fake_env, project, capsys):
    assert start(project) == 0
    assert start(project, "B-1") == 2
    assert "in use by A-1" in capsys.readouterr().err


def test_start_refuses_dirty_worktree(fake_env, project, capsys):
    (project["worktree"] / "app.py").write_text("print(2)\n")
    assert start(project) == 2
    assert "uncommitted changes" in capsys.readouterr().err


def test_second_supervisor_refused(fake_env, project, capsys):
    with open(project["ws"] / "units.json.supervisor", "a+") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert main(["--config", str(project["config"]), "supervise"]) == 0
    assert "another supervisor is running" in capsys.readouterr().out


def test_supervise_with_no_units(fake_env, project, capsys):
    assert main(["--config", str(project["config"]), "supervise"]) == 0
    assert "EVENT: - no active units" in capsys.readouterr().out


def test_stop_signals_only_this_workspace_supervisor(fake_env, project, capsys):
    target = subprocess.Popen(["bash", "-c", 'exec -a "orch supervise" sleep 30'])
    bystander = subprocess.Popen(["sleep", "30"])
    try:
        time.sleep(0.2)
        (project["ws"] / "units.json.supervisor").write_text(f"{target.pid}\n")
        assert main(["--config", str(project["config"]), "stop"]) == 0
        assert target.wait(timeout=5) != 0
        assert bystander.poll() is None
    finally:
        target.kill()
        bystander.kill()
    assert f"stopped supervisor {target.pid}" in capsys.readouterr().out


def test_stop_ignores_a_reused_pid(fake_env, project, capsys):
    other = subprocess.Popen(["sleep", "30"])
    try:
        (project["ws"] / "units.json.supervisor").write_text(f"{other.pid}\n")
        assert main(["--config", str(project["config"]), "stop"]) == 0
        assert other.poll() is None
    finally:
        other.kill()
    assert "is not one" in capsys.readouterr().out


def test_roles_table(fake_env, project, capsys):
    assert main(["--config", str(project["config"]), "roles"]) == 0
    out = capsys.readouterr().out
    assert "builder" in out and "built by claude: reviews reviewer, second_reviewer" in out


def test_conform_harness_example(fake_env, project, capsys):
    assert main(["--config", str(project["config"]), "conform", "harness", "claude"]) == 0
    assert "conforms" in capsys.readouterr().out


def test_every_verb_dispatches():
    import argparse

    from orchestrate.cli import COMMANDS, STANDALONE, parser

    sub = next(a for a in parser()._actions if isinstance(a, argparse._SubParsersAction))
    assert set(sub.choices) == set(COMMANDS) | set(STANDALONE)
