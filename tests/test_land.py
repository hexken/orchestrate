import subprocess
import sys

import pytest

from orchestrate import conform
from orchestrate.adapters import Land

from .conftest import EXAMPLES, git


@pytest.fixture
def landing(fake_env, project, tmp_path, monkeypatch):
    wt = project["worktree"]
    git(wt, "switch", "-q", "-c", "agent/a-1")
    git(wt, "config", "user.email", "t@example.com")
    git(wt, "config", "user.name", "T")
    (wt / "feature.py").write_text("x = 1\n")
    git(wt, "add", "feature.py")
    git(wt, "commit", "-qm", "feature")
    monkeypatch.setenv("ORCH_CONFIG", str(project["config"]))
    monkeypatch.setenv("ORCH_PYTHON", sys.executable)
    monkeypatch.setenv("ORCH_DESTINATION", "main")
    monkeypatch.setenv("ORCH_LOGS", str(tmp_path / "logs"))
    monkeypatch.setenv("ORCH_LAND_POLL", "0")
    monkeypatch.setenv("ORCH_LAND_TRIES", "3")
    monkeypatch.setenv("ORCH_RETRY_SLEEP", "0")
    monkeypatch.setenv("FAKE_BKT_DIR", str(tmp_path / "bkt"))
    monkeypatch.setenv("FAKE_ORIGIN", str(project["origin"]))
    return project


def configure(project, checks):
    quoted = ", ".join(f'"{c}"' for c in checks)
    project["config"].write_text(
        f'[project]\nname = "myapp"\nrepo = "{project["repo"]}"\n'
        f'[land]\nadapter = "bkt"\nchecks = [{quoted}]\n'
    )


def land(project):
    wt = project["worktree"]
    head = git(wt, "rev-parse", "--short", "HEAD")
    body = project["repo"].parent / "body.md"
    body.write_text("body")
    done = subprocess.run(
        [str(EXAMPLES / "land-bkt"), "land", str(wt), "agent/a-1", head, "feat: a-1", str(body)],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.strip().splitlines()[-1]


def test_failing_check(landing):
    configure(landing, ["true", "false"])
    assert land(landing) == "FAILED push: RESULT: FAILED at check 2: false (" + land_log(landing)


def land_log(project):
    wt = project["worktree"]
    head = git(wt, "rev-parse", "--short", "HEAD")
    return f"{project['repo'].parent / 'logs'}/push-agent-a-1-{head}.log)"


def test_success_pushes_and_opens_one_pr(landing, fake_env):
    configure(landing, ["test -f feature.py"])
    line = land(landing)
    pushed = git(landing["origin"], "rev-parse", "--short", "agent/a-1")
    assert line == f"LANDED PR #1 SUCCESSFUL {pushed}"
    line = land(landing)
    assert line.startswith("LANDED PR #1 SUCCESSFUL")
    assert fake_env.read_text().count("bkt pr create") == 1


def test_destination_moved_is_merged_before_checks(landing):
    repo = landing["repo"]
    (repo / "dest.txt").write_text("new\n")
    git(repo, "add", "dest.txt")
    git(repo, "commit", "-qm", "dest moved")
    git(repo, "push", "-q", "origin", "HEAD:main")
    configure(landing, ["test -f dest.txt"])
    assert land(landing).startswith("LANDED PR #1 SUCCESSFUL")
    assert git(landing["origin"], "cat-file", "-t", "agent/a-1:dest.txt") == "blob"


def test_failed_build(landing, monkeypatch):
    configure(landing, [])
    monkeypatch.setenv("FAKE_BUILD", "FAILED")
    assert " FAILED " in land(landing) + " "


def test_example_conforms(landing):
    assert conform.land(Land(EXAMPLES / "land-bkt")) == []


def test_logged_out_fails_conform(landing, monkeypatch):
    monkeypatch.setenv("FAKE_BKT_LOGGED_OUT", "1")
    assert conform.land(Land(EXAMPLES / "land-bkt")) == ["auth: not logged in to the forge"]
