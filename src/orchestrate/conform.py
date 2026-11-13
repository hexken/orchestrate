import os
import tempfile
from pathlib import Path

from orchestrate.adapters import Adapter, AdapterError, Harness, Land, role_env
from orchestrate.config import Role

PROBE = Role("probe", "conform-model", "conform-effort")
NO_MODEL = "orch-no-such-model"


def dry(role: Role = PROBE) -> dict[str, str]:
    return role_env(role, ORCH_DRY_RUN="1", ORCH_ADD_DIRS="/conform/dir")


def described(adapter: Adapter, keys: dict[str, type]) -> tuple[dict[str, object], list[str]]:
    try:
        reply = adapter.describe()
    except AdapterError as err:
        return {}, [str(err)]
    problems = [
        f"describe: '{key}' missing or not {kind.__name__}"
        for key, kind in keys.items()
        if not isinstance(reply.get(key), kind)
    ]
    return reply, problems


def harness(adapter: Harness, role: Role, live: bool = False) -> list[str]:
    reply, problems = described(adapter, {"kind": str, "interactive": bool, "print": bool})
    if problems:
        return problems
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.md")
        prompt = os.path.join(tmp, "prompt.txt")
        Path(prompt).write_text("Reply with only the word ok.\n")
        if reply["interactive"]:
            done = adapter.run("start", "conform", "p0", tmp, prompt, env=dry())
            text = done.stdout
            if done.returncode:
                problems.append(f"start (dry run) exited {done.returncode}: {done.stderr.strip()}")
            elif "conform-model" not in text or "conform-effort" not in text:
                problems.append("start (dry run) does not pass ORCH_MODEL and ORCH_EFFORT")
            elif "/conform/dir" not in text and reply["kind"] == "claude":
                problems.append("start (dry run) does not pass ORCH_ADD_DIRS")
        if reply["print"]:
            done = adapter.run("print", prompt, out, env=dry())
            if done.returncode or "conform-model" not in done.stdout:
                problems.append("print (dry run) does not pass ORCH_MODEL")
            if os.path.exists(out):
                problems.append("print (dry run) wrote its output file")
        done = adapter.run("skills-sync", env={**dry(), "ORCH_SKILLS": ""})
        if done.returncode:
            problems.append(f"skills-sync (dry run) exited {done.returncode}")
        if live and reply["print"]:
            problems += live_print(adapter, role, prompt, tmp)
    return problems


def live_print(adapter: Harness, role: Role, prompt: str, tmp: str) -> list[str]:
    problems = []
    good = os.path.join(tmp, "good.md")
    if not adapter.answer(role, prompt, good, tmp) or not Path(good).read_text().strip():
        problems.append("print (live) wrote no answer")
    bad = os.path.join(tmp, "bad.md")
    broken = Role(role.harness, NO_MODEL, role.effort, role.mode)
    done = adapter.run("print", prompt, bad, env=role_env(broken), cwd=tmp)
    if done.returncode == 0:
        problems.append(f"print (live) exited 0 with model {NO_MODEL}")
    if os.path.exists(bad):
        problems.append("print (live) wrote an output file on failure")
    return problems


def land(adapter: Land) -> list[str]:
    _, problems = described(adapter, {"forge": str})
    if problems:
        return problems
    done = adapter.run("land", "/wt", "agent/x", "abc123", "title", "/dev/null", env=dry())
    if done.returncode:
        problems.append(f"land (dry run) exited {done.returncode}: {done.stderr.strip()}")
    done = adapter.run("merge", "1", env=dry())
    if done.returncode:
        problems.append(f"merge (dry run) exited {done.returncode}")
    if not adapter.auth():
        problems.append("auth: not logged in to the forge")
    return problems
