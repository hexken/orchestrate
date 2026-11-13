import os
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

from orchestrate.cli import main
from orchestrate.config import load
from orchestrate.scaffold import WORKSPACE_FILES

from .conftest import ROOT

GUARD_FILES = (
    os.environ.get("ORCH_GUARD_TERMS", ""),
    os.path.expanduser("~/.config/git-scrub/map.tsv"),
)


def scaffold(project, *extra):
    return main(["scaffold", "--repo", str(project["repo"]), "--name", "myapp", *extra])


def test_scaffold_writes_workspace(project, capsys):
    ws = project["repo"] / ".orchestrate"
    (ws / "orchestrate.toml").unlink()
    (ws / "briefs" / "builder.md").unlink()
    assert scaffold(project, "--land", "bkt") == 0
    for name in WORKSPACE_FILES:
        text = (ws / name).read_text()
        assert "{{" not in text, name
    assert (ws / "bin" / "orch").stat().st_mode & 0o111
    config = load(ws / "orchestrate.toml")
    assert config.land.adapter == "bkt" and config.project.name == "myapp"
    assert config.land.heavy_lock is None and config.project.planning_repo is None
    assert "<UNIT>" in (ws / "briefs" / "builder.md").read_text()
    exclude = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=project["repo"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    lines = (project["repo"] / exclude / "info" / "exclude").read_text().splitlines()
    assert "/.orchestrate" in lines and "/scratch/" in lines


def test_scaffold_twice_changes_nothing(project, capsys):
    scaffold(project)
    ws = project["repo"] / ".orchestrate"
    before = {p: p.read_bytes() for p in ws.rglob("*") if p.is_file()}
    capsys.readouterr()
    scaffold(project)
    out = capsys.readouterr().out
    assert "wrote" not in out
    assert {p: p.read_bytes() for p in ws.rglob("*") if p.is_file()} == before


def test_template_config_parses():
    tomllib.loads((ROOT / "src/orchestrate/templates/orchestrate.toml").read_text())


def tracked_text():
    names = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    for name in names:
        path = ROOT / name
        if path.suffix in {".lock"} or not path.is_file():
            continue
        try:
            yield name, path.read_text().lower()
        except UnicodeDecodeError:
            continue


def guarded_terms():
    path = next((p for p in GUARD_FILES if p and os.path.exists(p)), None)
    if path is None:
        return None
    terms = []
    for line in Path(path).read_text().splitlines():
        term = line.split("\t", 1)[0].strip().lower()
        if term and not term.startswith("#"):
            terms.append(term)
    return terms


def test_no_private_terms():
    terms = guarded_terms()
    if terms is None:
        pytest.skip("no private-terms file: set ORCH_GUARD_TERMS or keep a git-scrub map")
    patterns = [re.compile(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])") for t in terms]
    hits = sorted({name for name, text in tracked_text() if any(p.search(text) for p in patterns)})
    assert hits == [], "files holding a private term (terms not shown)"
