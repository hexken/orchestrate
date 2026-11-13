import argparse
import fcntl
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from orchestrate import conform, doctor, flow, scaffold, watch
from orchestrate.adapters import Harness, Land, adapter_path
from orchestrate.config import ConfigError, load
from orchestrate.effects import Effects
from orchestrate.registry import ACTIVE, Unit, Workspace

CONFIG_NAME = "orchestrate.toml"


def find_config(given: str | None) -> Path:
    if given:
        return Path(given)
    if os.environ.get("ORCH_CONFIG"):
        return Path(os.environ["ORCH_CONFIG"])
    here = Path.cwd()
    for folder in (here, *here.parents):
        for candidate in (folder / CONFIG_NAME, folder / ".orchestrate" / CONFIG_NAME):
            if candidate.exists():
                return candidate
    raise ConfigError(f"no {CONFIG_NAME} found: pass --config or set ORCH_CONFIG")


def context(args: argparse.Namespace) -> flow.Ctx:
    config = load(find_config(args.config))
    ws = Workspace(config.workspace)
    return flow.Ctx(config, ws, Effects(config, ws))


def edit(ctx: flow.Ctx, name: str, change: Callable[[Unit], None]) -> None:
    with ctx.ws.lock():
        units = ctx.ws.load()
        if name not in units:
            raise RuntimeError(f"no unit {name}")
        change(units[name])
        ctx.ws.save(units)


def cmd_start(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    unit = flow.start_unit(ctx, args.unit, args.worktree, args.plan, args.role, args.scope)
    print(
        f"{unit['unit']} started: tab {unit['tab']}, pane {unit['pane']}, branch {unit['branch']}"
    )
    return 0


def supervise_once(ctx: flow.Ctx) -> list[str]:
    events = []
    with ctx.ws.lock():
        units = ctx.ws.load()
        for key, unit in units.items():
            if unit["status"] not in ACTIVE or unit["status"] == "starting":
                continue
            try:
                event = flow.step(ctx, unit)
            except Exception as err:
                event = ctx.ws.wait(unit, f"error: {err}")
            if event:
                events.append(f"EVENT: {key} {event}")
        ctx.ws.save(units)
    if not events and not any(u["status"] in ACTIVE for u in units.values()):
        events.append("EVENT: - no active units")
    return events


def cmd_supervise(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    ctx.ws.root.mkdir(parents=True, exist_ok=True)
    with open(ctx.ws.supervisor, "a+") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("EVENT: - another supervisor is running")
            return 0
        guard.seek(0)
        guard.truncate()
        guard.write(f"{os.getpid()}\n")
        guard.flush()
        while True:
            events = supervise_once(ctx)
            if events:
                print("\n".join(events), flush=True)
                return 0
            if args.once:
                return 0
            time.sleep(ctx.config.timeouts.poll_seconds)


def supervisor_pid(ws: Workspace) -> int | None:
    try:
        text = ws.supervisor.read_text().strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def cmd_stop(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    pid = supervisor_pid(ctx.ws)
    if pid is None:
        print("no supervisor recorded for this workspace")
        return 0
    command = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False
    ).stdout
    if "supervise" not in command:
        print(f"no supervisor running (pid {pid} is not one)")
        return 0
    os.kill(pid, signal.SIGTERM)
    ctx.ws.note("-", f"orchestrator: supervisor {pid} stopped")
    print(f"stopped supervisor {pid}; its review and land jobs keep running")
    return 0


def cmd_status(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    for key, unit in ctx.ws.load().items():
        extra = f" ({unit.get('event')})" if unit["status"] == "waiting" else ""
        print(
            f"{key:14} {unit['status']:10} {unit.get('harness', ''):7} {unit['branch']:28} "
            f"tab {unit.get('tab')} pr {unit.get('pr')}{extra}"
        )
    return 0


def cmd_timeline(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    previous = None
    for stamp, what in ctx.ws.load()[args.unit].get("timeline", []):
        now = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
        gap = f"+{int((now - previous).total_seconds() // 60)} min" if previous else ""
        print(f"{stamp}  {gap:>9}  {what}")
        previous = now
    return 0


def cmd_resume(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    edit(ctx, args.unit, lambda unit: flow.resume(ctx, unit, args.status))
    return 0


def cmd_reland(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    edit(ctx, args.unit, lambda unit: flow.reland(ctx, unit))
    return 0


def cmd_merge(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    edit(ctx, args.unit, lambda unit: flow.merge(ctx, unit, args.force))
    return 0


def cmd_close(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    def change(unit: Unit) -> None:
        flow.close(ctx, unit, "closed")
        ctx.ws.mark(unit, "closed")

    edit(ctx, args.unit, change)
    return 0


def cmd_note(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    text = " ".join(args.text)
    if args.unit == "-":
        ctx.ws.note("-", text)
    else:
        edit(ctx, args.unit, lambda unit: ctx.ws.mark(unit, f"note: {text}"))
    return 0


def cmd_roles(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    for name, role in ctx.config.roles.items():
        print(f"{name:22} {role.harness:8} {role.model:28} {role.effort:8} {role.mode}")
    for harness, pipe in ctx.config.pipeline.items():
        print(
            f"built by {harness}: reviews {', '.join(pipe.reviews) or 'none'}; light {pipe.light}"
        )
    return 0


def cmd_conform(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    if args.kind == "harness":
        role = ctx.config.roles[args.role]
        path = adapter_path(ctx.ws.root, "harness", args.name)
        problems = conform.harness(Harness(path), role, live=args.live)
    else:
        problems = conform.land(Land(adapter_path(ctx.ws.root, "land", args.name)))
    for problem in problems:
        print(f"FAIL {problem}")
    print("conforms" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def cmd_watch(ctx: flow.Ctx, args: argparse.Namespace) -> int:
    return watch.loop(ctx.ws, ctx.config.review, args.unit)


def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        config = load(find_config(args.config))
    except ConfigError:
        config = None
    lines, code = doctor.run(config)
    for line in lines:
        print(line)
    return code


def cmd_scaffold(args: argparse.Namespace) -> int:
    answers = scaffold.Answers(
        Path(args.repo),
        args.name or Path(args.repo).resolve().name,
        args.destination,
        args.planning_repo or "",
        args.land or "",
    )
    for name, what in scaffold.scaffold(answers):
        print(f"{what:6} {name}")
    return 0


COMMANDS: dict[str, Callable[[flow.Ctx, argparse.Namespace], int]] = {
    "start": cmd_start,
    "supervise": cmd_supervise,
    "stop": cmd_stop,
    "status": cmd_status,
    "timeline": cmd_timeline,
    "resume": cmd_resume,
    "reland": cmd_reland,
    "merge": cmd_merge,
    "close": cmd_close,
    "note": cmd_note,
    "roles": cmd_roles,
    "conform": cmd_conform,
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="orch", description="Orchestrate coding-agent build units in Herdr."
    )
    root.add_argument("--config", help="path to orchestrate.toml")
    sub = root.add_subparsers(dest="verb")
    start = sub.add_parser("start", help="start a unit's builder in a new Herdr tab")
    start.add_argument("unit")
    start.add_argument("--worktree", required=True)
    start.add_argument("--plan", required=True)
    start.add_argument("--role", default="builder")
    start.add_argument("--scope")
    supervise = sub.add_parser("supervise", help="run the unit flow until an event")
    supervise.add_argument("--once", action="store_true")
    sub.add_parser("stop", help="stop this workspace's supervisor; jobs keep running")
    sub.add_parser("status", help="list units")
    sub.add_parser("doctor", help="check the prerequisites")
    build = sub.add_parser("scaffold", help="write the .orchestrate workspace into a repository")
    build.add_argument("--repo", required=True)
    build.add_argument("--name")
    build.add_argument("--destination", default="main")
    build.add_argument("--planning-repo")
    build.add_argument("--land")
    sub.add_parser("watch", help="live view of one unit (opened in its Herdr tab)").add_argument(
        "unit"
    )
    sub.add_parser("roles", help="print the role table and review pipelines")
    for verb in ("timeline", "reland", "close"):
        sub.add_parser(verb).add_argument("unit")
    resume = sub.add_parser("resume", help="put a unit back in a status after an event")
    resume.add_argument("unit")
    resume.add_argument("status")
    merge = sub.add_parser("merge", help="merge a unit's PR by hand")
    merge.add_argument("unit")
    merge.add_argument("--force", action="store_true")
    note = sub.add_parser("note", help="record an owner input or intervention")
    note.add_argument("unit")
    note.add_argument("text", nargs="+")
    check = sub.add_parser("conform", help="check an adapter against its contract")
    check.add_argument("kind", choices=("harness", "land"))
    check.add_argument("name")
    check.add_argument("--role", default="builder")
    check.add_argument("--live", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.verb is None:
        parser().print_help()
        return 0
    if args.verb == "doctor":
        return cmd_doctor(args)
    if args.verb == "scaffold":
        return cmd_scaffold(args)
    try:
        return COMMANDS[args.verb](context(args), args)
    except (ConfigError, RuntimeError) as err:
        print(f"orch: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
