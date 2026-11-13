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


def git(cwd, *args):
    import subprocess

    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def project(tmp_path):
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    repo = tmp_path / "myapp"
    git(tmp_path, "clone", "-q", str(origin), str(repo))
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    (repo / "app.py").write_text("print(1)\n")
    git(repo, "add", "app.py")
    git(repo, "commit", "-qm", "init")
    git(repo, "push", "-q", "origin", "HEAD:main")
    worktree = tmp_path / "myapp-wt1"
    git(repo, "worktree", "add", "-q", "--detach", str(worktree), "origin/main")
    ws = repo / ".orchestrate"
    (ws / "briefs").mkdir(parents=True)
    (ws / "adapters").mkdir()
    (ws / "briefs" / "builder.md").write_text("Build <UNIT> on <BRANCH> from <BASE>.\n")
    import shutil

    shutil.copy(EXAMPLES / "harness-claude", ws / "adapters" / "harness-claude")
    config = ws / "orchestrate.toml"
    config.write_text(f'[project]\nname = "myapp"\nrepo = "{repo}"\n[land]\nadapter = "fake"\n')
    return {"repo": repo, "worktree": worktree, "config": config, "ws": ws, "origin": origin}
