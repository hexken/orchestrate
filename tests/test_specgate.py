from dataclasses import replace

from orchestrate.config import SpecGate
from orchestrate.specgate import install, scan, sync, titles

from .conftest import git

SPEC = """# Spec

**G1** Every version is immutable.
**G2** Approval is recorded.

## 11. Scenarios

### 11.1 Versions

- A committed version never changes (G1)
- Two drafts commit in order

### 11.2 Approval

- Approval moves the pointer (G2)

## 12. Notes

- Not a title
"""

TEST_OK = """import pytest


@pytest.mark.guarantee("G1")
def test_a_committed_version_never_changes():
    pass


def test_two_drafts_commit_in_order():
    pass
"""


def setup(tmp_path, test_text, milestone=2):
    spec = tmp_path / "spec.md"
    spec.write_text(SPEC)
    acceptance = tmp_path / "tests" / "acceptance"
    acceptance.mkdir(parents=True)
    (acceptance / "test_versions.py").write_text(test_text)
    return SpecGate(enabled=True, spec=spec, milestone=milestone)


def test_titles_follow_their_section(tmp_path):
    found = titles(SPEC, SpecGate())
    assert [(t.text, t.milestone, t.refs) for t in found] == [
        ("A committed version never changes", 1, ("G1",)),
        ("Two drafts commit in order", 1, ()),
        ("Approval moves the pointer", 2, ("G2",)),
    ]


def test_scan_passes_with_current_milestone_untested(tmp_path):
    result = scan(setup(tmp_path, TEST_OK), tmp_path)
    assert result.ok
    assert "untested title (milestone 2): Approval moves the pointer" in result.reported
    assert "untested guarantee: G2" in result.reported


def test_untested_earlier_milestone_title_fails(tmp_path):
    result = scan(setup(tmp_path, TEST_OK, milestone=3), tmp_path)
    assert not result.ok
    assert result.failures == ["untested title (milestone 2): Approval moves the pointer"]


def test_unknown_marker_and_unmatched_test_are_errors(tmp_path):
    text = TEST_OK + '\n\n@pytest.mark.guarantee("G9")\ndef test_something_else():\n    pass\n'
    result = scan(setup(tmp_path, text), tmp_path)
    assert "test_versions.py: marker names unknown G9" in result.errors
    assert "test_versions.py::test_something_else matches no scenario title" in result.errors


def test_property_tests_need_no_title(tmp_path):
    gate = setup(tmp_path, TEST_OK)
    props = tmp_path / "tests" / "acceptance" / "properties"
    props.mkdir()
    (props / "test_digest.py").write_text('@pytest.mark.guarantee("G2")\ndef test_x():\n    pass\n')
    result = scan(gate, tmp_path)
    assert result.ok and "untested guarantee: G2" not in result.reported


def repo_with_acceptance(project):
    wt = project["worktree"]
    git(wt, "switch", "-q", "-c", "agent/a-1")
    git(wt, "config", "user.email", "t@example.com")
    git(wt, "config", "user.name", "T")
    acceptance = wt / "tests" / "acceptance"
    acceptance.mkdir(parents=True)
    (acceptance / "test_a.py").write_text("def test_a():\n    pass\n")
    git(wt, "add", "tests")
    git(wt, "commit", "-qm", "acceptance")
    return wt


def test_install_failing_check_restores_and_commits_nothing(project):
    wt = repo_with_acceptance(project)
    gate = SpecGate(enabled=True, install_checks=("true", "false"))
    sync(gate, wt)
    drafts = wt / "scratch" / "acceptance"
    (drafts / "test_b.py").write_text("def test_b():\n    pass\n")
    (drafts / "COMMIT_MSG").write_text("test(acceptance): add b\n")
    head = git(wt, "rev-parse", "HEAD")
    ok, message = install(gate, wt)
    assert not ok and "check failed: false" in message
    assert not (wt / "tests" / "acceptance" / "test_b.py").exists()
    assert git(wt, "rev-parse", "HEAD") == head


def test_install_commits_only_acceptance(project):
    wt = repo_with_acceptance(project)
    gate = SpecGate(enabled=True, install_checks=("true",))
    sync(gate, wt)
    drafts = wt / "scratch" / "acceptance"
    (drafts / "test_b.py").write_text("def test_b():\n    pass\n")
    (drafts / "COMMIT_MSG").write_text("test(acceptance): add b\n")
    (wt / "app.py").write_text("print(3)\n")
    ok, message = install(replace(gate), wt)
    assert ok, message
    assert git(wt, "log", "-1", "--format=%s") == "test(acceptance): add b"
    assert git(wt, "show", "--name-only", "--format=", "HEAD") == "tests/acceptance/test_b.py"
    assert git(wt, "status", "--porcelain", "app.py") == "M app.py"
