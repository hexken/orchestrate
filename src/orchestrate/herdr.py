import json
import os
import re
import subprocess
import time
from typing import Any

DIALOG = re.compile(r"Allow access|Yes, allow|No, deny|Allow this|Do you want to")


class HerdrError(RuntimeError):
    pass


def require_env() -> None:
    if os.environ.get("HERDR_ENV") != "1":
        raise HerdrError("not running inside a Herdr pane (HERDR_ENV is not 1)")


def call(*args: str, binary: str = "herdr") -> dict[str, Any] | None:
    require_env()
    for _ in (1, 2):
        try:
            done = subprocess.run(
                [binary, *args], capture_output=True, text=True, timeout=120, check=False
            )
        except subprocess.TimeoutExpired:
            continue
        for stream in (done.stdout, done.stderr):
            try:
                reply = json.loads(stream)
            except json.JSONDecodeError:
                continue
            if not isinstance(reply, dict):
                continue
            if "error" in reply:
                error = reply["error"]
                return {"error": error.get("code") if isinstance(error, dict) else str(error)}
            result = reply.get("result", {})
            return result if isinstance(result, dict) else {}
        time.sleep(2)
    return None


def text(*args: str, binary: str = "herdr") -> str:
    require_env()
    done = subprocess.run([binary, *args], capture_output=True, text=True, timeout=60, check=False)
    return done.stdout


def tab_create(workspace: str, cwd: str, label: str) -> tuple[str, str]:
    reply = (
        call(
            "tab", "create", "--workspace", workspace, "--cwd", cwd, "--label", label, "--no-focus"
        )
        or {}
    )
    tab = reply.get("tab") or {}
    pane = reply.get("root_pane") or {}
    if not tab.get("tab_id") or not pane.get("pane_id"):
        raise HerdrError(f"herdr tab create failed: {reply}")
    return str(tab["tab_id"]), str(pane["pane_id"])


def tab_close(tab: str) -> None:
    call("tab", "close", tab)


def split(beside: str, cwd: str, direction: str | None = None, ratio: float | None = None) -> str:
    if direction is None:
        layout = (call("pane", "layout", "--pane", beside) or {}).get("layout", {})
        rect = next(
            (p["rect"] for p in layout.get("panes", []) if p.get("pane_id") == beside),
            {"width": 80, "height": 40},
        )
        direction = "right" if rect["width"] > 2 * rect["height"] else "down"
    args = ["pane", "split", beside, "--direction", direction, "--cwd", cwd, "--no-focus"]
    if ratio is not None:
        args += ["--ratio", str(ratio)]
    pane = (call(*args) or {}).get("pane") or {}
    if not pane.get("pane_id"):
        raise HerdrError(f"could not split pane {beside}")
    return str(pane["pane_id"])


def pane_run(pane: str, command: str) -> None:
    call("pane", "run", pane, command)


def agent_state(name: str) -> str:
    result = call("agent", "get", name)
    if result is None:
        return "unknown"
    if result.get("error") == "agent_not_found":
        return "gone"
    return str((result.get("agent") or {}).get("agent_status") or "unknown")


def agent_session(name: str) -> str | None:
    agent = (call("agent", "get", name) or {}).get("agent") or {}
    value = (agent.get("agent_session") or {}).get("value")
    return str(value) if value else None


def agent_prompt(name: str, message: str) -> None:
    call("agent", "prompt", name, message)


def dialog(name: str) -> bool:
    return bool(DIALOG.search(text("agent", "read", name, "--source", "visible", "--lines", "25")))
