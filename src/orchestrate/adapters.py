import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from orchestrate.config import Role

HARNESS_VERBS = ("describe", "start", "print", "skills-sync")
LAND_VERBS = ("describe", "land", "merge", "auth")


class AdapterError(RuntimeError):
    pass


def adapter_path(workspace: Path, kind: str, name: str) -> Path:
    return workspace / "adapters" / f"{kind}-{name}"


def role_env(role: Role, **extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(ORCH_MODEL=role.model, ORCH_EFFORT=role.effort, ORCH_MODE=role.mode, **extra)
    return env


@dataclass(frozen=True)
class Adapter:
    path: Path

    def run(
        self,
        *args: str,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess[str]:
        if not os.access(self.path, os.X_OK):
            raise AdapterError(f"{self.path} is missing or not executable")
        return subprocess.run(
            [str(self.path), *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=timeout,
            check=False,
        )

    def describe(self) -> dict[str, object]:
        done = self.run("describe")
        try:
            reply = json.loads(done.stdout)
        except json.JSONDecodeError as err:
            raise AdapterError(f"{self.path.name} describe printed no JSON") from err
        if done.returncode or not isinstance(reply, dict):
            raise AdapterError(f"{self.path.name} describe failed")
        return reply


@dataclass(frozen=True)
class Harness(Adapter):
    def start(
        self, role: Role, name: str, pane: str, cwd: str, brief: str, add_dirs: list[str]
    ) -> str:
        env = role_env(role, ORCH_ADD_DIRS=os.pathsep.join(add_dirs))
        done = self.run("start", name, pane, cwd, brief, env=env, cwd=cwd, timeout=300)
        if done.returncode:
            raise AdapterError(f"{self.path.name} start failed: {done.stderr.strip()[-400:]}")
        lines = done.stdout.strip().splitlines()
        return lines[-1] if lines else ""

    def print_command(
        self, role: Role, prompt_file: str, out: str
    ) -> tuple[list[str], dict[str, str]]:
        return [str(self.path), "print", prompt_file, out], role_env(role)

    def answer(self, role: Role, prompt_file: str, out: str, cwd: str) -> bool:
        done = self.run("print", prompt_file, out, env=role_env(role), cwd=cwd, timeout=4 * 3600)
        return done.returncode == 0 and Path(out).exists()

    def skills_sync(self, skills: list[str]) -> None:
        done = self.run("skills-sync", env={**os.environ, "ORCH_SKILLS": os.pathsep.join(skills)})
        if done.returncode:
            raise AdapterError(f"{self.path.name} skills-sync failed: {done.stderr.strip()}")


@dataclass(frozen=True)
class Land(Adapter):
    def auth(self) -> bool:
        return self.run("auth").returncode == 0

    def merge(self, pr: str) -> tuple[bool, str]:
        done = self.run("merge", pr, timeout=300)
        return done.returncode == 0, (done.stdout + done.stderr).strip()
