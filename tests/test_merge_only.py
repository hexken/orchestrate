import subprocess

import pytest

from orchestrate.config import load
from orchestrate.effects import Effects
from orchestrate.registry import Workspace

from .conftest import git


def commit(wt, name, text, message):
    (wt / name).write_text(text)
    git(wt, "add", name)
    git(wt, "commit", "-qm", message)
    return git(wt, "rev-parse", "--short", "HEAD")


@pytest.fixture
def setup(project, tmp_path):
    wt = project["worktree"]
    git(wt, "config", "user.email", "t@example.com")
    git(wt, "config", "user.name", "T")
    git(wt, "switch", "-qc", "agent/a-1")
    checked = commit(wt, "feature.py", "x = 1\n", "feature")
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(project["origin"]), str(other))
    git(other, "config", "user.email", "t@example.com")
    git(other, "config", "user.name", "T")
    commit(other, "sibling.py", "y = 1\n", "sibling")
    git(other, "push", "-q", "origin", "HEAD:main")
    git(wt, "fetch", "-q", "origin")
    config = load(project["config"])
    fx = Effects(config, Workspace(config.workspace))
    unit = {"worktree": str(wt), "branch": "agent/a-1"}
    return fx, unit, wt, checked, other


def test_a_clean_merge_of_the_destination_is_merge_only(setup):
    fx, unit, wt, checked, _ = setup
    git(wt, "merge", "-q", "--no-edit", "origin/main")
    assert fx.merge_only(unit, checked) is True


def test_an_edit_inside_the_merge_commit_is_not(setup):
    fx, unit, wt, checked, _ = setup
    git(wt, "merge", "-q", "--no-edit", "origin/main")
    (wt / "feature.py").write_text("x = 2\n")
    git(wt, "commit", "-qa", "--amend", "--no-edit")
    assert fx.merge_only(unit, checked) is False


def test_a_new_commit_is_not(setup):
    fx, unit, wt, checked, _ = setup
    git(wt, "merge", "-q", "--no-edit", "origin/main")
    commit(wt, "more.py", "z = 1\n", "more")
    assert fx.merge_only(unit, checked) is False


def test_a_branch_reset_behind_the_checked_head_is_not(setup):
    fx, unit, wt, checked, _ = setup
    git(wt, "reset", "-q", "--hard", "origin/main")
    assert fx.merge_only(unit, checked) is False


def test_a_conflict_resolved_by_hand_is_not(setup):
    fx, unit, wt, checked, other = setup
    commit(other, "feature.py", "x = 9\n", "clash")
    git(other, "push", "-q", "origin", "HEAD:main")
    git(wt, "fetch", "-q", "origin")
    subprocess.run(["git", "merge", "-q", "origin/main"], cwd=wt, capture_output=True)
    (wt / "feature.py").write_text("x = 9\n")
    git(wt, "add", "feature.py")
    git(wt, "commit", "-q", "--no-edit")
    assert fx.merge_only(unit, checked) is False


def test_the_destination_moving_after_the_merge_still_counts(setup):
    fx, unit, wt, checked, other = setup
    git(wt, "merge", "-q", "--no-edit", "origin/main")
    commit(other, "later.py", "w = 1\n", "later")
    git(other, "push", "-q", "origin", "HEAD:main")
    git(wt, "fetch", "-q", "origin")
    assert fx.merge_only(unit, checked) is True


def test_merge_base_is_short(setup):
    fx, unit, wt, checked, _ = setup
    base = fx.merge_base(unit)
    assert base == git(wt, "rev-parse", "--short", "origin/main~1")
