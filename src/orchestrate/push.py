import fcntl
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from pathlib import Path
from typing import TextIO

from orchestrate.config import Config, load


class Failed(Exception):
    pass


@contextmanager
def flock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


class Push:
    def __init__(self, config: Config, worktree: Path, branch: str, commit: str, log: TextIO):
        self.config = config
        self.worktree = worktree
        self.branch = branch
        self.commit = commit
        self.log = log
        self.checkout = Path(f"{worktree}{config.land.push_suffix}")
        self.destination = config.project.destination

    def say(self, text: str) -> None:
        self.log.write(f"=== {time.strftime('%H:%M:%S')} {text}\n")
        self.log.flush()

    def run(self, *cmd: str, cwd: Path | None = None, shell: bool = False) -> int:
        self.log.flush()
        env = {**os.environ, "ORCH_HEAVY_LOCK_HELD": "1"}
        args: str | list[str] = cmd[0] if shell else list(cmd)
        return subprocess.run(
            args,
            cwd=cwd or self.checkout,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            shell=shell,
            env=env,
            check=False,
        ).returncode

    def git(self, *args: str, cwd: Path | None = None) -> int:
        return self.run("git", *args, cwd=cwd)

    def out(self, *args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=self.checkout, capture_output=True, text=True, check=False
        )
        return done.stdout.strip() if done.returncode == 0 else ""

    def heavy(self) -> AbstractContextManager[None]:
        lock = self.config.land.heavy_lock
        return flock(lock) if lock else nullcontext()

    def merge_in(self, ref: str) -> None:
        if self.git("merge", "-q", "--no-edit", ref) == 0:
            return
        conflicts = set(self.out("diff", "--name-only", "--diff-filter=U").splitlines())
        theirs = set(self.config.land.theirs_on_conflict)
        if conflicts and conflicts <= theirs:
            for path in conflicts:
                self.git("checkout", "--theirs", path)
                self.git("add", path)
            if self.git("commit", "-q", "--no-edit") == 0:
                return
        self.git("merge", "--abort")
        raise Failed(f"merge {ref}")

    def prepare(self) -> None:
        if self.git("fetch", "-q", "origin", cwd=self.worktree):
            raise Failed("fetch")
        if self.checkout.exists():
            self.git("merge", "--abort")
            if self.git("reset", "-q", "--hard") or self.git(
                "checkout", "-q", "--detach", self.commit
            ):
                raise Failed("checkout")
        elif self.git(
            "worktree", "add", "-q", "--detach", str(self.checkout), self.commit, cwd=self.worktree
        ):
            raise Failed("worktree")
        self.git("reset", "-q", "--hard", self.commit)
        self.git("clean", "-qfd", "-e", ".venv")
        remote = f"origin/{self.branch}"
        if self.out("rev-parse", "-q", "--verify", remote) and self.git(
            "merge-base", "--is-ancestor", remote, "HEAD"
        ):
            self.say(f"merge {remote} into {self.commit}")
            self.merge_in(remote)
        if self.git("merge-base", "--is-ancestor", f"origin/{self.destination}", "HEAD"):
            self.say(f"merge origin/{self.destination} into {self.commit}")
            self.merge_in(f"origin/{self.destination}")

    def checks(self) -> None:
        with self.heavy():
            for number, check in enumerate(self.config.land.checks, 1):
                self.say(f"check {number}: {check}")
                if self.run(check, shell=True):
                    raise Failed(f"check {number}: {check}")
        paths = list(self.config.land.commit_paths)
        if paths:
            self.git("add", "--", *paths)
            if self.git("diff", "--cached", "--quiet", "--", *paths):
                head = self.out("rev-parse", "--short", "HEAD")
                if self.git("commit", "-q", "-m", f"chore: check results at {head}"):
                    raise Failed("commit")

    def push(self) -> str:
        remote = f"origin/{self.branch}"
        if self.out("rev-parse", "HEAD") == self.out("rev-parse", "-q", "--verify", remote):
            self.say("nothing new to push: an empty commit starts a fresh build")
            if self.git("commit", "-q", "--allow-empty", "-m", "ci: run the build again"):
                raise Failed("commit")
        self.say("push")
        target = f"HEAD:refs/heads/{self.branch}"
        with self.heavy():
            if self.git("push", "origin", target):
                log = Path(self.log.name).read_text() if hasattr(self.log, "name") else ""
                if "pre-push:" in log:
                    raise Failed("push (the pre-push hook refused it; see above)")
                self.say("the push failed without a hook refusal: retrying once")
                time.sleep(float(os.environ.get("ORCH_RETRY_SLEEP", "30")))
                if self.git("push", "origin", target):
                    raise Failed("push")
        return self.out("rev-parse", "--short", "HEAD")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 4:
        print("usage: python -m orchestrate.push <worktree> <branch> <commit> <log>")
        return 2
    worktree, branch, commit, log_path = args
    config = load(Path(os.environ["ORCH_CONFIG"]))
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as log:
        job = Push(config, Path(worktree).resolve(), branch, commit, log)
        with flock(Path(f"{job.checkout}.lock")):
            try:
                job.prepare()
                job.checks()
                pushed = job.push()
            except Failed as err:
                log.write(f"RESULT: FAILED at {err}\n")
                print(f"RESULT: FAILED at {err}")
                return 1
        log.write(f"RESULT: PUSHED {pushed}\n")
    print(f"RESULT: PUSHED {pushed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
