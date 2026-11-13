import json
import re
import shlex
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from orchestrate import breakpoints, briefs, report
from orchestrate.adapters import adapter_path
from orchestrate.config import Config
from orchestrate.effects import EffectError, Effects, matches
from orchestrate.registry import Unit, Workspace
from orchestrate.scaffold import TEMPLATES
from orchestrate.verdict import FIXES_HEADING, findings, verdict

LOW = ("low", "nit")
MOVED = "the branch moved past the reviewed head with new commits"
BUILD_MINUTES = re.compile(r"^BUILD-MINUTES\s+(\d+(?:\.\d+)?)\s*$", re.M)
FIXES = FIXES_HEADING
PRINT_DELIVER = (
    "Write no file: your whole final answer is the review, in Markdown, and it is saved for "
    "you. This checkout is a throwaway worktree, so checkouts in it are safe."
)


@dataclass
class Ctx:
    config: Config
    ws: Workspace
    fx: Effects


def scratch(ctx: Ctx, unit: Unit, name: str) -> Path:
    return Path(unit["worktree"]) / ctx.config.project.scratch / name


def summary(ctx: Ctx, unit: Unit, suffix: str = "") -> Path:
    return scratch(ctx, unit, f"units/{unit['unit']}{suffix}.md")


def fresh(path: Path, since: float) -> bool:
    return path.exists() and path.stat().st_size > 0 and path.stat().st_mtime >= since


def agent_name(unit: Unit, role: str) -> str:
    return f"{unit['name']}-{role.replace('_', '-')}"[:32]


def values(ctx: Ctx, unit: Unit, **extra: str) -> dict[str, str]:
    base = {
        "UNIT": unit["unit"],
        "NAME": unit["name"],
        "WORKTREE": unit["worktree"],
        "BRANCH": unit["branch"],
        "BASE": unit.get("base", ""),
        "PLAN": unit.get("plan", ""),
        "DESTINATION": ctx.config.project.destination,
        "WORKSPACE": str(ctx.ws.root),
        "SCRATCH": ctx.config.project.scratch,
        "SUMMARY": str(summary(ctx, unit)),
        "DATE": date.today().isoformat(),
    }
    return {**base, **extra}


def template(ctx: Ctx, role: str, kind: str) -> Path:
    own = ctx.ws.briefs / f"{role}.md"
    return own if own.exists() else ctx.ws.briefs / f"{kind}.md"


def scope_of(unit: Unit) -> Path | None:
    return Path(unit["scope"]) if unit.get("scope") else None


def reset_timers(unit: Unit) -> None:
    for key in [k for k in unit if k.startswith(("idle_since:", "stall_since:"))]:
        del unit[key]


def deliver(ctx: Ctx, unit: Unit, role: str, out: Path, head: str) -> str:
    if ctx.config.roles[role].mode == "print":
        return PRINT_DELIVER
    return (
        "Run checkouts and tests in a throwaway detached worktree in your scratchpad "
        f"(`git worktree add --detach <scratchpad>/review {head}`), never in the unit's worktree, "
        f"and remove it when done. Write the review to {out} once, when every check has "
        "finished; keep any draft in your scratchpad."
    )


def print_script(
    ctx: Ctx, unit: Unit, role: str, brief: Path, out: Path, base: str, head: str
) -> Path:
    q = shlex.quote
    repo = ctx.config.project.repo
    path = repo.parent / f"{repo.name}-review-{unit['name']}-{role.replace('_', '-')}"
    sc = ctx.config.project.scratch
    adapter = adapter_path(ctx.ws.root, "harness", ctx.config.roles[role].harness)
    copies = [str(summary(ctx, unit))] + [f["path"] for f in unit.get("review_files", [])]
    context = " ".join(q(c) for c in ctx.config.review.context)
    script = ctx.ws.logs / f"{unit['name']}-{role}.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        f"""#!/usr/bin/env bash
set -uo pipefail
wt={q(unit["worktree"])} path={q(str(path))} out={q(str(out))}
[[ -d $path ]] && git -C "$wt" worktree remove --force "$path"
git -C "$wt" worktree add -q --detach "$path" {q(head)} || exit 1
mkdir -p "$path/{sc}/units" "$path/{sc}/context"
cp {q(str(brief))} "$path/{sc}/brief.txt"
for f in {" ".join(q(c) for c in copies)}; do cp "$f" "$path/{sc}/units/" 2>/dev/null; done
for f in {context}; do cp "$f" "$path/{sc}/context/" 2>/dev/null; done
git -C "$path" diff {q(base)} {q(head)} > "$path/{sc}/unit.diff"
git -C "$path" log --oneline {q(base)}..{q(head)} > "$path/{sc}/unit-log.txt"
cd "$path" && {q(str(adapter))} print "$path/{sc}/brief.txt" "$out"
rc=$?
git -C "$wt" worktree remove --force "$path"
echo "review rc $rc"
exit $rc
"""
    )
    script.chmod(0o755)
    return script


def start_review(
    ctx: Ctx, unit: Unit, role: str, kind: str, base: str, extra: dict[str, str]
) -> None:
    out = summary(ctx, unit, f"-{role}" if kind == "review" else "-light")
    head = ctx.fx.head(unit)
    text = values(
        ctx,
        unit,
        BASE=base,
        HEAD=head,
        OUT=str(out),
        DELIVER=deliver(ctx, unit, role, out, head),
        **extra,
    )
    brief = scratch(ctx, unit, f"{unit['name']}-{role}-brief.txt")
    briefs.write(
        template(ctx, role, kind), brief, text, scope_of(unit) if kind == "review" else None
    )
    item = {"path": str(out), "role": role, "kind": kind, "base": base}
    if ctx.config.roles[role].mode == "print":
        script = print_script(ctx, unit, role, brief, out, base, head)
        ctx.fx.background(unit, role, ["bash", str(script)], role_name=role)
        item["producer"] = f"print:{role}"
    else:
        agent = agent_name(unit, role)
        pane = ctx.fx.split(unit["pane"], unit["worktree"])
        session = ctx.fx.start_agent(role, agent, pane, unit["worktree"], str(brief))
        unit.setdefault("sessions", {})[agent] = session
        item["producer"] = f"agent:{agent}"
    unit["required"].append(item)


def code_changed(ctx: Ctx, unit: Unit) -> bool:
    return any(not matches(n, ctx.config.review.docs_only) for n in ctx.fx.changed(unit))


def land(ctx: Ctx, unit: Unit) -> None:
    body = ctx.ws.logs / f"{unit['name']}-pr-body.md"
    body.parent.mkdir(parents=True, exist_ok=True)
    body.write_text(
        f"Unit {unit['unit']}. The builder's summary and the reviews are in the unit's worktree "
        f"under `{ctx.config.project.scratch}/units/`.\n"
    )
    unit["land_head"] = ctx.fx.head(unit)
    adapter = adapter_path(ctx.ws.root, "land", ctx.config.land.adapter)
    cmd = [
        str(adapter),
        "land",
        unit["worktree"],
        unit["branch"],
        unit["land_head"],
        f"feat: unit {unit['unit']}",
        str(body),
    ]
    ctx.fx.background(unit, "land", cmd)
    ctx.ws.mark(unit, f"land started at {unit['land_head']}")


def fetch_twice(ctx: Ctx, unit: Unit) -> str | None:
    try:
        ctx.fx.fetch(unit)
        return None
    except EffectError:
        pass
    try:
        ctx.fx.fetch(unit)
        return None
    except EffectError as err:
        return str(err)


def same_commit(one: str, other: str) -> bool:
    return bool(one and other) and (one.startswith(other) or other.startswith(one))


def start_reviews(ctx: Ctx, unit: Unit) -> str | None:
    problem = fetch_twice(ctx, unit)
    if problem:
        return ctx.ws.wait(
            unit,
            f"fetch failed twice before the reviews: {problem}; check the remote, then "
            "`resume <UNIT> building`",
        )
    unit["status"], unit["required"] = "reviewing", []
    reset_timers(unit)
    unit["reviews_started"] = ctx.fx.now()
    unit["reviewed_head"] = unit["checked_head"] = ctx.fx.head(unit)
    since = ctx.fx.merge_base(unit)
    if since and not same_commit(since, unit["base"]):
        unit.setdefault("started_base", unit["base"])
        unit["base"] = since
    needs = code_changed(ctx, unit)
    roles = ctx.config.pipeline[unit["harness"]].reviews if needs else ()
    ctx.ws.mark(unit, f"reviews started at {unit['reviewed_head']} ({len(roles)} required)")
    land(ctx, unit)
    for role in roles:
        start_review(ctx, unit, role, "review", unit["base"], {})
    unit["review_files"] = [dict(item) for item in unit["required"]]
    return None


def start_fixes(ctx: Ctx, unit: Unit) -> None:
    files = " and ".join(f["path"] for f in unit["review_files"])
    unit["status"], unit["fixes_sent"] = "fixing", ctx.fx.now()
    reset_timers(unit)
    ctx.fx.prompt(
        unit["name"],
        f"The reviews are in: {files}. Fix every finding as your brief says, append a "
        "'## Fixes' section to your summary, then stop.",
    )
    ctx.ws.mark(unit, "fixes sent to the builder")
    send_refresh(ctx, unit)


def land_checked(ctx: Ctx, unit: Unit) -> None:
    if ctx.fx.job(unit, "land") is None and "land" in unit.get("jobs", {}):
        unit["reland"] = True
    else:
        land(ctx, unit)


def start_landing(ctx: Ctx, unit: Unit) -> None:
    unit["status"], unit["required"] = "landing", []
    reset_timers(unit)
    unit["checked_head"] = ctx.fx.head(unit)
    ctx.ws.mark(unit, f"fixes in at {unit['checked_head']}: landing")
    land_checked(ctx, unit)


def start_light(ctx: Ctx, unit: Unit) -> None:
    unit["status"], unit["required"], unit["reviews_started"] = "light", [], ctx.fx.now()
    reset_timers(unit)
    unit["checked_head"] = ctx.fx.head(unit)
    ctx.ws.mark(unit, f"light review started at {unit['checked_head']}")
    land_checked(ctx, unit)
    reviews = ", ".join(f["path"] for f in unit["review_files"])
    role = ctx.config.pipeline[unit["harness"]].light
    start_review(ctx, unit, role, "light", unit["reviewed_head"], {"REVIEWS": reviews})


def idle_twice(ctx: Ctx, unit: Unit, name: str) -> bool:
    key = f"idle_since:{name}"
    if ctx.fx.agent_state(name) not in ("idle", "done"):
        unit.pop(key, None)
        return False
    unit.setdefault(key, ctx.fx.now())
    return bool(ctx.fx.now() - unit[key] >= ctx.config.timeouts.idle_seconds)


def stalled(ctx: Ctx, unit: Unit, name: str, label: str, harness: str) -> str | None:
    limits = ctx.config.timeouts
    state = ctx.fx.agent_state(name)
    if state == "working":
        age = ctx.fx.transcript_age(unit.get("sessions", {}).get(name))
        if age is not None and age > limits.wedged_minutes * 60:
            return (
                f"{label} {name} shows working but has written nothing for {int(age // 60)} "
                "minutes: wedged (interrupt it, then prompt it to carry on)"
            )
    if state == "gone":
        return f"{label} {name} is gone"
    if state == "blocked" or (harness != "claude" and ctx.fx.dialog(name)):
        return f"{label} {name} is blocked or on a dialog (only the owner answers a dialog)"
    key = f"stall_since:{name}"
    if state in ("idle", "done"):
        unit.setdefault(key, ctx.fx.now())
        if ctx.fx.now() - unit[key] > limits.stall_minutes * 60:
            return f"{label} {name} idle {limits.stall_minutes} minutes with nothing new: stalled"
    else:
        unit.pop(key, None)
    return None


def pr_number(line: str | None) -> str | None:
    found = re.search(r"PR #(\d+)", line or "")
    return found.group(1) if found else None


def archive(ctx: Ctx, unit: Unit) -> None:
    folder = ctx.ws.archive / unit["unit"]
    try:
        folder.mkdir(parents=True, exist_ok=True)
        units = scratch(ctx, unit, "units")
        found = list(units.glob(f"{unit['unit']}*.md")) if units.exists() else []
        found += list(scratch(ctx, unit, "").glob(f"{unit['name']}*-brief.txt"))
        for path in found:
            shutil.copy2(path, folder)
        for name, session in (unit.get("sessions") or {}).items():
            for path in ctx.fx.transcripts(session) if session else []:
                shutil.copy2(path, folder / f"{name}.jsonl")
        log = ctx.fx.git(
            unit["worktree"],
            "log",
            "--stat",
            "--format=%h %ad %s",
            "--date=iso",
            f"{unit.get('base', 'HEAD')}..{unit['branch']}",
            check=False,
        )
        (folder / "commits.txt").write_text(log)
        (folder / "unit.json").write_text(json.dumps(unit, indent=1))
    except OSError as err:
        ctx.ws.mark(unit, f"archive incomplete: {err}")


def close(ctx: Ctx, unit: Unit, status: str) -> None:
    if unit.get("tab"):
        ctx.fx.tab_close(unit["tab"])
    unit["status"] = status
    archive(ctx, unit)


def merge(ctx: Ctx, unit: Unit, force: bool = False) -> None:
    line = ctx.fx.job(unit, "land") or ""
    pr = pr_number(line)
    if pr is None:
        raise RuntimeError(f"no PR for {unit['unit']}: {line!r}")
    if not force and not line.startswith(f"LANDED PR #{pr} SUCCESSFUL"):
        raise RuntimeError(f"the last land of {unit['unit']} is not green: {line!r}")
    ok, out = ctx.fx.merge(pr)
    if not ok:
        raise RuntimeError(f"merge of PR #{pr} failed: {out[-300:]}")
    unit["pr"] = pr
    close(ctx, unit, "merged")
    ctx.ws.mark(unit, f"merged PR #{pr}")


def record_minutes(ctx: Ctx, unit: Unit) -> None:
    info = unit.get("jobs", {}).get("land")
    if not info or unit.get("minutes_read") == info["log"] or ctx.fx.job(unit, "land") is None:
        return
    unit["minutes_read"] = info["log"]
    log = Path(info["log"])
    found = BUILD_MINUTES.findall(log.read_text()) if log.exists() else []
    if found:
        ctx.ws.mark(unit, f"build minutes {float(found[-1]):g}")


def landed(ctx: Ctx, unit: Unit) -> str | None:
    line = ctx.fx.job(unit, "land")
    if line is None:
        return None
    log = unit["jobs"]["land"]["log"]
    if line.startswith("FAILED pr-") and unit.get("retried:land") != log:
        land(ctx, unit)
        unit["retried:land"] = unit["jobs"]["land"]["log"]
        ctx.ws.mark(unit, f"land retried once after: {line}")
        return None
    if not line.startswith("LANDED") or " SUCCESSFUL " not in f"{line} ":
        return ctx.ws.wait(unit, f"land: {line}")
    head = ctx.fx.head(unit)
    if head != unit.get("checked_head", head):
        ctx.fx.fetch(unit)
        if not ctx.fx.merge_only(unit, unit["checked_head"]):
            unit["moved_head"] = head
            return ctx.ws.wait(
                unit,
                f"{MOVED}: review them, then `resume <UNIT> landing` (it lands the current "
                "head) or `resume <UNIT> fixing`",
            )
        ctx.ws.mark(unit, f"refreshed with {ctx.config.project.destination} at {head}: landing")
        unit["checked_head"] = head
    if unit["land_head"] != head:
        land(ctx, unit)
        return None
    pushed = line.split()[-1]
    ctx.fx.fetch(unit)
    destination = f"origin/{ctx.config.project.destination}"
    if not ctx.fx.is_ancestor(unit, destination, pushed):
        ctx.ws.mark(unit, f"{ctx.config.project.destination} moved since the land: landing again")
        land(ctx, unit)
        return None
    merge(ctx, unit)
    return "merged"


def restart_print(ctx: Ctx, unit: Unit, item: dict[str, str]) -> None:
    unit["required"].remove(item)
    extra = {"REVIEWS": ", ".join(f["path"] for f in unit["review_files"])}
    start_review(
        ctx,
        unit,
        item["role"],
        item["kind"],
        item["base"],
        extra if item["kind"] == "light" else {},
    )


def reviews_step(ctx: Ctx, unit: Unit) -> str | None:
    verdicts = []
    for item in list(unit["required"]):
        path = Path(item["path"])
        v = verdict(path, ctx.config.review) if fresh(path, unit["reviews_started"]) else None
        if v == "unreadable":
            return ctx.ws.wait(unit, f"no verdict on any line of {path}")
        if v is None:
            kind, _, who = item["producer"].partition(":")
            if kind == "print":
                ended = ctx.fx.job(unit, who)
                if ended is not None:
                    log = unit["jobs"][who]["log"]
                    if unit.get(f"retried:{who}") == log:
                        return ctx.ws.wait(unit, f"the {who} review ended with no output ({log})")
                    restart_print(ctx, unit, item)
                    unit[f"retried:{who}"] = unit["jobs"][who]["log"]
                    ctx.ws.mark(unit, f"{who} review retried once after: {ended}")
                    return None
            else:
                harness = ctx.config.roles[item["role"]].harness
                problem = stalled(ctx, unit, who, "reviewer", harness)
                if problem:
                    return ctx.ws.wait(unit, problem)
        verdicts.append(v)
    if None in verdicts:
        return None
    if "hold" in verdicts:
        if unit["status"] == "light":
            return ctx.ws.wait(
                unit,
                "the light review holds: move what's open to INBOX, then "
                "`resume <UNIT> landing` or `close`",
            )
        start_fixes(ctx, unit)
        return None
    unit["status"] = "landing"
    ctx.ws.mark(unit, "reviews clean")
    event = landed(ctx, unit)
    if event == "merged":
        unit.pop("refresh_pending", None)
    else:
        send_refresh(ctx, unit)
    return event


def expected_findings(unit: Unit) -> dict[tuple[str, str], str | None]:
    expected: dict[tuple[str, str], str | None] = {}
    for item in unit.get("review_files", []):
        path = Path(item["path"])
        reviewer = path.stem.removeprefix(f"{unit['unit']}-")
        found = findings(path.read_text()) if path.exists() else []
        if found is None:
            labels: list[str | None] = [None] * report.findings(path)
        else:
            labels = [f.severity for f in found]
        for number, label in enumerate(labels, 1):
            expected[(reviewer, str(number))] = label
    return expected


def unsettled(unit: Unit, summary_path: Path) -> str | None:
    expected = expected_findings(unit)
    answered = {(f["reviewer"], f["n"]): f for f in report.fixes(summary_path, unit["unit"])}
    after = "check them, then `resume <UNIT> landing --accept-head` or `resume <UNIT> fixing`"
    open_ = [
        f"{who} #{n} ({expected.get((who, n)) or 'unlabelled'}, {f['outcome']})"
        for (who, n), f in answered.items()
        if f["outcome"] in ("declined", "deferred") and expected.get((who, n)) not in LOW
    ]
    if open_:
        return f"unsettled fixes: {', '.join(open_)}: {after}"
    missing = [f"{who} #{n}" for who, n in expected if (who, n) not in answered]
    if missing:
        return f"unsettled fixes: no Fixes line for {', '.join(missing)}: {after}"
    return None


def step(ctx: Ctx, unit: Unit) -> str | None:
    status = unit["status"]
    record_minutes(ctx, unit)
    if unit.get("reland") and ctx.fx.job(unit, "land") is not None:
        unit.pop("reland")
        land(ctx, unit)
    too_old = ctx.fx.too_old(unit)
    if too_old:
        hours = ctx.config.timeouts.job_hours
        log = unit["jobs"][too_old]["log"]
        return ctx.ws.wait(unit, f"job {too_old} has run over {hours} hours: {log}")
    if status == "building":
        if fresh(summary(ctx, unit), unit["started"]) and idle_twice(ctx, unit, unit["name"]):
            ctx.ws.mark(unit, f"summary written at {ctx.fx.head(unit)}")
            return start_reviews(ctx, unit)
        problem = stalled(ctx, unit, unit["name"], "builder", unit["harness"])
        return ctx.ws.wait(unit, problem) if problem else None
    if status in ("reviewing", "light"):
        return reviews_step(ctx, unit)
    if status == "fixing":
        path = summary(ctx, unit)
        text = path.read_text() if path.exists() else ""
        written = fresh(path, unit.get("fixes_sent", 0)) and FIXES.search(text)
        if written and idle_twice(ctx, unit, unit["name"]):
            if ctx.config.pipeline[unit["harness"]].light:
                start_light(ctx, unit)
                return None
            problem = unsettled(unit, path)
            if problem:
                return ctx.ws.wait(unit, problem)
            start_landing(ctx, unit)
            return None
        problem = stalled(ctx, unit, unit["name"], "builder", unit["harness"])
        return ctx.ws.wait(unit, problem) if problem else None
    if status == "landing":
        return landed(ctx, unit)
    return None


UNIT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,30}")


def start_unit(
    ctx: Ctx,
    unit_id: str,
    worktree: str,
    plan: str,
    role: str = "builder",
    scope: str | None = None,
) -> Unit:
    if not UNIT_ID.fullmatch(unit_id):
        raise RuntimeError("a unit name is letters, digits and dashes, at most 31 characters")
    if role not in ctx.config.roles:
        raise RuntimeError(f"no role {role!r} in the config")
    worktree = str(Path(worktree).expanduser().resolve())
    name = unit_id.lower()
    plan_units = breakpoints.plan_units(ctx.config.project.work_plan)
    blocker = breakpoints.blocking(ctx.ws, unit_id, plan_units)
    if blocker:
        raise RuntimeError(f"breakpoint {blocker} is pending: {unit_id} waits for its pass")
    breakpoints.auto_milestone(ctx.ws, ctx.config.project.work_plan, unit_id)
    with ctx.ws.lock():
        units = ctx.ws.load()
        for key, other in units.items():
            if other["status"] not in ("merged", "closed", "error") and (
                other["worktree"] == worktree or key == unit_id
            ):
                raise RuntimeError(
                    f"{worktree} or {unit_id} is in use by {key} ({other['status']})"
                )
        if ctx.fx.git(worktree, "status", "--porcelain", "--untracked-files=no"):
            raise RuntimeError(f"{worktree} has uncommitted changes")
        unit: Unit = {
            "unit": unit_id,
            "name": name,
            "role": role,
            "harness": ctx.config.roles[role].harness,
            "worktree": worktree,
            "branch": f"{ctx.config.project.branch_prefix}{name}",
            "plan": plan,
            "scope": str(Path(scope).resolve()) if scope else None,
            "status": "starting",
            "started": ctx.fx.now(),
        }
        units[unit_id] = unit
        ctx.ws.save(units)
    try:
        for old in scratch(ctx, unit, "units").glob(f"{unit_id}*.md"):
            old.unlink()
        ctx.fx.fetch(unit)
        destination = f"origin/{ctx.config.project.destination}"
        ctx.fx.git(worktree, "switch", "-q", "-C", unit["branch"], destination)
        unit["base"] = ctx.fx.git(worktree, "rev-parse", "--short", "HEAD")
        plan_file = ctx.ws.root / "plans" / plan
        if not plan_file.exists():
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            plan_file.write_text(f"# {plan_file.stem}\n\nStatus: active\n")
        brief = scratch(ctx, unit, f"{name}-brief.txt")
        briefs.write(ctx.ws.briefs / "builder.md", brief, values(ctx, unit), scope_of(unit))
        unit["tab"], unit["pane"] = ctx.fx.tab_create(worktree, name)
        ctx.fx.watch(unit)
        unit["session"] = ctx.fx.start_agent(role, name, unit["pane"], worktree, str(brief))
        unit.setdefault("sessions", {})[name] = unit["session"]
        unit["status"] = "building"
        ctx.ws.mark(unit, f"started on {unit['branch']} at {unit['base']}")
    except BaseException as err:
        if unit.get("tab"):
            ctx.fx.tab_close(unit["tab"])
        unit["status"] = "error"
        ctx.ws.mark(unit, f"start failed: {err}")
        raise
    finally:
        with ctx.ws.lock():
            units = ctx.ws.load()
            units[unit_id] = unit
            ctx.ws.save(units)
    return unit


def restart_missing_reviews(ctx: Ctx, unit: Unit) -> None:
    since = unit.get("reviews_started", 0)
    required = list(unit.get("required", []))
    missing = [
        item
        for item in required
        if not fresh(Path(item["path"]), since)
        or verdict(Path(item["path"]), ctx.config.review) in (None, "unreadable")
    ]
    if missing and len(missing) == len(required):
        unit["reviews_started"] = ctx.fx.now()
    for item in missing:
        Path(item["path"]).unlink(missing_ok=True)
        kind, _, who = item["producer"].partition(":")
        if kind == "print" or ctx.fx.agent_state(who) == "gone":
            restart_print(ctx, unit, item)
        else:
            ctx.fx.prompt(
                who,
                f"Write your review to {item['path']} as your brief says, with the verdict first.",
            )


def resume(ctx: Ctx, unit: Unit, status: str, accept_head: bool = False) -> None:
    if status not in ("building", "reviewing", "fixing", "light", "landing"):
        raise RuntimeError("resume to building, reviewing, fixing, light or landing")
    if status == "light" and not ctx.config.pipeline[unit["harness"]].light:
        raise RuntimeError(f"the {unit['harness']} pipeline has no light review")
    moved = str(unit.get("event") or "").startswith(MOVED)
    if status == "landing" and moved and not accept_head:
        now = ctx.fx.head(unit)
        if now != unit.get("moved_head"):
            raise RuntimeError(
                f"the head moved again since the event (was {unit.get('moved_head')}, now "
                f"{now}): check it, then resume with --accept-head"
            )
    unit["status"], unit["event"] = status, None
    reset_timers(unit)
    if status == "fixing":
        unit["fixes_sent"] = ctx.fx.now()
        unit.setdefault("reviewed_head", unit.get("land_head", unit["base"]))
        unit.setdefault("review_files", unit.get("required", []))
    if status in ("reviewing", "light"):
        restart_missing_reviews(ctx, unit)
    else:
        send_refresh(ctx, unit)
    if status == "landing" and (accept_head or moved):
        unit["checked_head"] = ctx.fx.head(unit)
        ctx.ws.mark(unit, f"resumed to landing; accepted {unit['checked_head']} as checked")
        return
    ctx.ws.mark(unit, f"resumed to {status}")


REFRESHED = ("building", "fixing")
QUEUED = ("reviewing", "light")


def send_refresh(ctx: Ctx, unit: Unit) -> None:
    text = unit.pop("refresh_pending", None)
    if not text:
        return
    try:
        ctx.fx.prompt(unit["name"], text)
    except Exception as err:
        ctx.ws.mark(unit, f"refresh prompt failed: {err}")
        return
    ctx.ws.mark(unit, "queued refresh sent")


def refresh_siblings(ctx: Ctx, units: dict[str, Unit], merged: Unit) -> None:
    own = ctx.ws.briefs / "refresh.md"
    template = own if own.exists() else TEMPLATES / "briefs" / "refresh.md"
    text = briefs.fill(
        template,
        {
            "DESTINATION": ctx.config.project.destination,
            "MERGED": merged["unit"],
            "PR": f"#{merged.get('pr', '?')}",
        },
    ).strip()
    destination = ctx.config.project.destination
    for other in units.values():
        if other is merged:
            continue
        if other["status"] in QUEUED:
            other["refresh_pending"] = text
            ctx.ws.mark(other, f"refresh after {merged['unit']} queued until the reviews end")
            continue
        if other["status"] not in REFRESHED:
            continue
        try:
            ctx.fx.prompt(other["name"], text)
        except Exception as err:
            ctx.ws.mark(other, f"refresh prompt failed: {err}")
            continue
        ctx.ws.mark(other, f"told to merge {destination} after {merged['unit']}")


def reland(ctx: Ctx, unit: Unit) -> None:
    if "land" in unit.get("jobs", {}) and ctx.fx.job(unit, "land") is None:
        pid = unit["jobs"]["land"].get("pid")
        raise RuntimeError(f"a land of {unit['unit']} is still running (pid {pid})")
    land(ctx, unit)
    if unit["status"] == "waiting":
        unit["status"], unit["event"] = "landing", None
