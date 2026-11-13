import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from orchestrate.config import SpecGate

HEADING = re.compile(r"^(#{1,6})\s")
TEST_DEF = re.compile(r"^\s*def\s+(test_\w+)\s*\(", re.M)


@dataclass(frozen=True)
class Title:
    text: str
    milestone: int
    refs: tuple[str, ...]

    @property
    def test_name(self) -> str:
        return "test_" + re.sub(r"[^a-z0-9]+", "_", self.text.lower()).strip("_")


@dataclass
class Scan:
    failures: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    reported: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures and not self.errors


def titles(spec: str, gate: SpecGate) -> list[Title]:
    section = re.compile(gate.title_section)
    title = re.compile(gate.title_pattern)
    found, milestone, level = [], None, 0
    for line in spec.splitlines():
        heading = HEADING.match(line)
        if heading:
            match = section.match(line)
            if match:
                milestone, level = int(match.group("milestone")), len(heading.group(1))
            elif milestone is not None and len(heading.group(1)) <= level:
                milestone = None
            continue
        if milestone is None:
            continue
        match = title.match(line)
        if match:
            refs = re.findall(r"[GC]\d+", match.group("refs") or "")
            found.append(Title(match.group("title").strip(), milestone, tuple(refs)))
    return found


def tests(acceptance: Path, gate: SpecGate) -> tuple[dict[str, Path], dict[str, list[Path]]]:
    names: dict[str, Path] = {}
    markers: dict[str, list[Path]] = {}
    marker = re.compile(gate.test_marker)
    for path in sorted(acceptance.rglob("test_*.py")):
        if gate.property_dir in path.relative_to(acceptance).parts[:-1]:
            for m in marker.finditer(path.read_text()):
                markers.setdefault(m.group("id"), []).append(path)
            continue
        text = path.read_text()
        for name in TEST_DEF.findall(text):
            names[name] = path
        for m in marker.finditer(text):
            markers.setdefault(m.group("id"), []).append(path)
    return names, markers


def scan(gate: SpecGate, repo: Path) -> Scan:
    result = Scan()
    if gate.spec is None or not gate.spec.exists():
        result.errors.append(f"spec not found: {gate.spec}")
        return result
    spec = gate.spec.read_text()
    known = set(re.findall(gate.guarantee_pattern, spec))
    known = {k if isinstance(k, str) else k[0] for k in known}
    listed = titles(spec, gate)
    names, markers = tests(repo / gate.acceptance_dir, gate)
    by_name = {t.test_name: t for t in listed}
    for t in listed:
        if t.test_name in names:
            continue
        line = f"untested title (milestone {t.milestone}): {t.text}"
        (result.failures if t.milestone < gate.milestone else result.reported).append(line)
    for name, path in names.items():
        if name not in by_name:
            result.errors.append(f"{path.name}::{name} matches no scenario title")
    for gid, paths in markers.items():
        if gid not in known:
            result.errors.append(f"{paths[0].name}: marker names unknown {gid}")
    cited = {ref for t in listed if t.test_name in names for ref in t.refs}
    for gid in sorted(known - set(markers) - cited, key=lambda g: (g[0], int(g[1:]))):
        result.reported.append(f"untested guarantee: {gid}")
    return result


def run(cmd: str, cwd: Path) -> int:
    return subprocess.run(cmd, shell=True, cwd=cwd, check=False).returncode


def sync(gate: SpecGate, worktree: Path) -> None:
    drafts, acceptance = worktree / gate.drafts_dir, worktree / gate.acceptance_dir
    message = drafts / "COMMIT_MSG"
    kept = message.read_text() if message.exists() else None
    if drafts.exists():
        shutil.rmtree(drafts)
    shutil.copytree(acceptance, drafts)
    if kept is not None:
        message.write_text(kept)


def install(gate: SpecGate, worktree: Path) -> tuple[bool, str]:
    drafts, acceptance = worktree / gate.drafts_dir, worktree / gate.acceptance_dir
    message = drafts / "COMMIT_MSG"
    if not message.exists() or not message.read_text().strip():
        return False, f"{message} is missing or empty"
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "acceptance"
        if acceptance.exists():
            shutil.copytree(acceptance, backup)
        shutil.copytree(
            drafts, acceptance, dirs_exist_ok=True, ignore=shutil.ignore_patterns("COMMIT_MSG")
        )
        failed = next((c for c in gate.install_checks if run(c, worktree)), None)
        if failed is not None:
            shutil.rmtree(acceptance)
            if backup.exists():
                shutil.copytree(backup, acceptance)
            return False, f"check failed: {failed}; {gate.acceptance_dir} restored"
    rel = str(acceptance.relative_to(worktree))
    if run(f"git add -- {rel}", worktree):
        return False, "git add failed"
    if (
        subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--", rel], cwd=worktree, check=False
        ).returncode
        == 0
    ):
        return True, "nothing to install"
    done = subprocess.run(
        ["git", "commit", "-q", "-F", str(message), "--", rel],
        cwd=worktree,
        check=False,
        capture_output=True,
        text=True,
    )
    if done.returncode:
        return False, f"commit failed: {done.stderr.strip()}"
    return True, "installed and committed"
