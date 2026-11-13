import hashlib
import re
import subprocess
import tomllib

from orchestrate.cli import main
from orchestrate.config import load
from orchestrate.scaffold import WORKSPACE_FILES

from .conftest import ROOT

GUARDED = {
    "9c758eed31287539",
    "3e808ece8227f5d4",
    "82535cbd439cf3a5",
    "11750d3cce898a85",
    "dbea7e4dccf3e4c0",
    "3719bd0ef1cf2806",
    "550f0e73ba4a13a3",
    "4304d1ebe624b221",
    "8d291c7017252b07",
    "8137015431526046",
}
WORD = re.compile(r"[a-z0-9][a-z0-9/_.-]*")


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


def test_no_reference_project_terms():
    hits = []
    for name, text in tracked_text():
        words = WORD.findall(text)
        grams = words + [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)]
        for gram in grams:
            for candidate in {gram, gram.strip("./-_")}:
                if hashlib.sha256(candidate.encode()).hexdigest()[:16] in GUARDED:
                    hits.append(name)
    assert hits == []
