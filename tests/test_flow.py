import json
import os
import time
from pathlib import Path

import pytest

from orchestrate import flow, jobs
from orchestrate.config import load
from orchestrate.effects import Effects, matches
from orchestrate.registry import Workspace

REVIEW_BRIEF = "Review <UNIT> from <BASE> to <HEAD>. <DELIVER>\n"
LIGHT_BRIEF = "Light review of <UNIT>: <REVIEWS> from <BASE> to <HEAD>. <DELIVER>\n"


class FakeFx(Effects):
    def __init__(self, config, ws):
        super().__init__(config, ws)
        self.clock = time.time()
        self.heads = {}
        self.files = ["src/app.py"]
        self.states = {}
        self.dialogs = set()
        self.prompts = []
        self.started = []
        self.jobs_started = []
        self.merged = []
        self.ancestor = True
        self.ages = {}
        self.base_at = ""
        self.only_merges = False
        self.fail_prompt = set()

    def now(self):
        return self.clock

    def head(self, unit):
        return self.heads.get(unit["name"], "h1")

    def changed(self, unit):
        return self.files

    def fetch(self, unit):
        pass

    def is_ancestor(self, unit, older, newer):
        return self.ancestor

    def merge_base(self, unit):
        return self.base_at

    def merge_only(self, unit, since):
        return self.only_merges

    def git(self, cwd, *args, check=True):
        return ""

    def agent_state(self, name):
        return self.states.get(name, "working")

    def dialog(self, name):
        return name in self.dialogs

    def prompt(self, name, message):
        if name in self.fail_prompt:
            raise RuntimeError("herdr prompt failed")
        self.prompts.append((name, message))

    def split(self, pane, cwd):
        return f"pane-{len(self.started) + 2}"

    def tab_close(self, tab):
        pass

    def start_agent(self, role_name, name, pane, cwd, brief):
        self.started.append((role_name, name, Path(brief).read_text()))
        return f"session-{name}"

    def background(self, unit, label, cmd, role_name=None, cwd=None):
        log = self.ws.logs / f"{unit['name']}-{label}-{len(self.jobs_started)}.out"
        log.parent.mkdir(parents=True, exist_ok=True)
        unit.setdefault("jobs", {})[label] = {"log": str(log), "started": self.clock, "pid": None}
        self.jobs_started.append((label, cmd))
        return str(log)

    def too_old(self, unit):
        return jobs.too_old(unit, self.config.timeouts.job_hours * 3600, self.clock)

    def merge(self, pr):
        self.merged.append(pr)
        return True, "merged"

    def transcript_age(self, session):
        return self.ages.get(session)

    def transcripts(self, session):
        return []


def make_ctx(tmp_path, extra=""):
    cfg = tmp_path / "orchestrate.toml"
    cfg.write_text(
        f'[project]\nname = "myapp"\nrepo = "{tmp_path}/repo"\n[land]\nadapter = "fake"\n' + extra
    )
    config = load(cfg)
    ws = Workspace(config.workspace)
    ws.briefs.mkdir(parents=True, exist_ok=True)
    (ws.briefs / "review.md").write_text(REVIEW_BRIEF)
    (ws.briefs / "light.md").write_text(LIGHT_BRIEF)
    return flow.Ctx(config, ws, FakeFx(config, ws))


@pytest.fixture
def ctx(tmp_path):
    return make_ctx(tmp_path)


LIGHT_ON = (
    '[pipeline.claude]\nreviews = ["reviewer", "second_reviewer"]\nlight = "light_reviewer"\n'
)


@pytest.fixture
def unit(ctx, tmp_path):
    worktree = tmp_path / "wt"
    (worktree / "scratch" / "units").mkdir(parents=True)
    return {
        "unit": "A-1",
        "name": "a-1",
        "harness": "claude",
        "worktree": str(worktree),
        "branch": "agent/a-1",
        "base": "b0",
        "plan": "p.md",
        "status": "building",
        "started": ctx.fx.clock - 10,
        "pane": "p1",
        "tab": "t1",
        "sessions": {"a-1": "s0"},
    }


def write(ctx, path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.utime(path, (ctx.fx.clock, ctx.fx.clock))


def finish(unit, label, line, rc=0):
    log = unit["jobs"][label]["log"]
    Path(log).write_text(f"working\n{line}\n")
    Path(log + ".rc").write_text(f"{rc}\n")


def tick(ctx, unit, seconds=61):
    ctx.fx.clock += seconds
    return flow.step(ctx, unit)


def build_done(ctx, unit):
    write(ctx, flow.summary(ctx, unit), "# A-1\nbuilt\n")
    ctx.fx.states["a-1"] = "idle"
    assert flow.step(ctx, unit) is None
    assert tick(ctx, unit) is None
    assert unit["status"] == "reviewing"


def review_paths(ctx, unit):
    return {item["role"]: Path(item["path"]) for item in unit["required"]}


def test_summary_and_idle_twice_start_reviews_and_land(ctx, unit):
    build_done(ctx, unit)
    assert [label for label, _ in ctx.fx.jobs_started] == ["land", "second_reviewer"]
    assert ctx.fx.started[0][:2] == ("reviewer", "a-1-reviewer")
    assert "Review A-1 from b0 to h1" in ctx.fx.started[0][2]
    assert set(review_paths(ctx, unit)) == {"reviewer", "second_reviewer"}
    assert unit["sessions"]["a-1-reviewer"] == "session-a-1-reviewer"


def test_happy_path_merges_and_archives(ctx, unit):
    build_done(ctx, unit)
    ctx.fx.clock += 5
    for path in review_paths(ctx, unit).values():
        write(ctx, path, "clean\n")
    finish(unit, "land", "LANDED PR #3 SUCCESSFUL h1")
    assert tick(ctx, unit) == "merged"
    assert ctx.fx.merged == ["3"]
    assert unit["status"] == "merged"
    archived = json.loads((ctx.ws.archive / "A-1" / "unit.json").read_text())
    assert archived["pr"] == "3"


def test_hold_sends_fixes_then_lands_without_light_review(ctx, unit):
    build_done(ctx, unit)
    ctx.fx.clock += 5
    paths = review_paths(ctx, unit)
    write(ctx, paths["reviewer"], "Verdict: changes needed\n")
    write(ctx, paths["second_reviewer"], "clean\n")
    assert tick(ctx, unit) is None
    assert unit["status"] == "fixing"
    ctx.fx.clock += 5
    write(ctx, flow.summary(ctx, unit), "# A-1\nbuilt\n**Fixes**\n- fixed in h2\n")
    ctx.fx.heads["a-1"] = "h2"
    assert tick(ctx, unit) is None
    assert tick(ctx, unit) is None
    assert unit["status"] == "landing"
    assert unit["checked_head"] == "h2" and unit.get("reland") is True
    assert [s for s in ctx.fx.started if s[0] == "light_reviewer"] == []
    assert [j for j in ctx.fx.jobs_started if j[0] == "light_reviewer"] == []
    assert sum(1 for j in ctx.fx.jobs_started if j[0] == "land") == 1
    finish(unit, "land", "LANDED PR #3 SUCCESSFUL h1")
    assert tick(ctx, unit) is None
    assert unit["land_head"] == "h2" and "reland" not in unit
    finish(unit, "land", "LANDED PR #3 SUCCESSFUL h2")
    assert tick(ctx, unit) == "merged"
    assert any("fixes in at h2: landing" in what for _, what in unit["timeline"])


def test_a_bullet_starting_with_fixes_is_not_a_fixes_section(ctx, unit):
    unit.update(status="fixing", fixes_sent=ctx.fx.clock - 5, review_files=[])
    write(ctx, flow.summary(ctx, unit), "# A-1\n- fixes the flaky test from the last unit\n")
    ctx.fx.states["a-1"] = "idle"
    assert flow.step(ctx, unit) is None
    assert tick(ctx, unit) is None
    assert unit["status"] == "fixing"


def fixes_in(ctx, unit, review, fixes):
    build_done(ctx, unit)
    ctx.fx.clock += 5
    paths = review_paths(ctx, unit)
    write(ctx, paths["reviewer"], review)
    write(ctx, paths["second_reviewer"], "clean\n## Findings\n- None.\n")
    assert tick(ctx, unit) is None and unit["status"] == "fixing"
    ctx.fx.clock += 5
    write(ctx, flow.summary(ctx, unit), "# A-1\n## Fixes\n" + fixes)
    ctx.fx.heads["a-1"] = "h2"
    flow.step(ctx, unit)
    return tick(ctx, unit)


TWO = "changes needed\n## Findings\n1. high: race\n2. low: wording\n"


def test_a_declined_high_finding_is_an_event(ctx, unit):
    event = fixes_in(
        ctx,
        unit,
        TWO,
        "- reviewer #1 (high): race: declined: by design\n"
        "- reviewer #2 (low): wording: fixed in h2; fails without the fix: test_w\n",
    )
    assert "unsettled fixes" in event and "reviewer #1" in event
    assert unit["status"] == "waiting"


def test_missing_fixes_lines_are_an_event(ctx, unit):
    event = fixes_in(
        ctx, unit, TWO, "- reviewer #1 (high): race: fixed in h2; fails without the fix: test_r\n"
    )
    assert "unsettled fixes: 1 Fixes lines for 2 findings" in event


def test_a_deferred_low_finding_still_lands(ctx, unit):
    event = fixes_in(
        ctx,
        unit,
        TWO,
        "- reviewer #1 (high): race: fixed in h2; fails without the fix: test_r\n"
        "- reviewer #2 (low): wording: deferred: INBOX\n",
    )
    assert event is None and unit["status"] == "landing"


def test_resume_light_refused_without_light_review(ctx, unit):
    unit["status"] = "waiting"
    with pytest.raises(RuntimeError, match="no light review"):
        flow.resume(ctx, unit, "light")


def test_hold_sends_fixes_then_light_review_then_merge(tmp_path, unit):
    ctx = make_ctx(tmp_path, LIGHT_ON)
    unit["started"] = ctx.fx.clock - 10
    build_done(ctx, unit)
    ctx.fx.clock += 5
    paths = review_paths(ctx, unit)
    write(ctx, paths["reviewer"], "Verdict: changes needed\n")
    write(ctx, paths["second_reviewer"], "clean\n")
    assert tick(ctx, unit) is None
    assert unit["status"] == "fixing"
    assert ctx.fx.prompts[-1][0] == "a-1"
    ctx.fx.clock += 5
    write(ctx, flow.summary(ctx, unit), "# A-1\nbuilt\n## Fixes\n- fixed in h2\n")
    ctx.fx.heads["a-1"] = "h2"
    assert tick(ctx, unit) is None
    assert tick(ctx, unit) is None
    assert unit["status"] == "light"
    assert unit.get("reland") is True
    light = review_paths(ctx, unit)["light_reviewer"]
    assert light.name == "A-1-light.md"
    finish(unit, "land", "LANDED PR #3 SUCCESSFUL h1")
    assert tick(ctx, unit) is None
    assert ctx.fx.jobs_started[-1][0] == "land"
    ctx.fx.clock += 5
    write(ctx, light, "clean\n")
    finish(unit, "land", "LANDED PR #3 SUCCESSFUL h2")
    assert tick(ctx, unit) == "merged"


def test_light_hold_is_an_event(ctx, unit):
    unit.update(
        status="light",
        reviews_started=ctx.fx.clock,
        review_files=[],
        required=[
            {
                "path": str(flow.summary(ctx, unit, "-light")),
                "role": "light_reviewer",
                "kind": "light",
                "base": "h1",
                "producer": "agent:a-1-light",
            }
        ],
    )
    write(ctx, flow.summary(ctx, unit, "-light"), "hold\n")
    assert "light review holds" in tick(ctx, unit)
    assert unit["status"] == "waiting"


def landing(ctx, unit, line):
    unit.update(status="landing", checked_head="h1")
    ctx.fx.background(unit, "land", ["land"])
    unit["land_head"] = "h1"
    finish(unit, "land", line)


def test_destination_moved_lands_again(ctx, unit):
    landing(ctx, unit, "LANDED PR #3 SUCCESSFUL h1")
    ctx.fx.ancestor = False
    assert tick(ctx, unit) is None
    assert ctx.fx.merged == []
    assert len([j for j in ctx.fx.jobs_started if j[0] == "land"]) == 2


def test_branch_moved_past_reviewed_head(ctx, unit):
    landing(ctx, unit, "LANDED PR #3 SUCCESSFUL h1")
    ctx.fx.heads["a-1"] = "h9"
    assert "moved past the reviewed head" in tick(ctx, unit)


def test_branch_with_only_destination_merges_lands_again(ctx, unit):
    landing(ctx, unit, "LANDED PR #3 SUCCESSFUL h1")
    ctx.fx.heads["a-1"] = "h9"
    ctx.fx.only_merges = True
    assert tick(ctx, unit) is None
    assert unit["checked_head"] == "h9" and unit["land_head"] == "h9"
    assert unit["status"] == "landing" and ctx.fx.merged == []
    assert sum(1 for j in ctx.fx.jobs_started if j[0] == "land") == 2
    finish(unit, "land", "LANDED PR #3 SUCCESSFUL h9")
    assert tick(ctx, unit) == "merged"


def test_resume_landing_takes_the_current_head_as_checked(ctx, unit):
    landing(ctx, unit, "LANDED PR #3 SUCCESSFUL h1")
    ctx.fx.heads["a-1"] = "h9"
    assert "moved past" in tick(ctx, unit)
    flow.resume(ctx, unit, "landing")
    assert unit["checked_head"] == "h9" and unit["status"] == "landing"
    assert tick(ctx, unit) is None
    assert unit["land_head"] == "h9"


def test_resume_landing_after_a_land_failure_keeps_the_checked_head(ctx, unit):
    landing(ctx, unit, "LANDED PR #3 FAILED h1")
    assert tick(ctx, unit).startswith("land:")
    ctx.fx.heads["a-1"] = "h9"
    flow.resume(ctx, unit, "landing")
    assert unit["checked_head"] == "h1"
    flow.reland(ctx, unit)
    finish(unit, "land", "LANDED PR #3 SUCCESSFUL h9")
    assert "moved past" in tick(ctx, unit)
    assert ctx.fx.merged == []


def test_resume_landing_accepts_the_head_when_asked(ctx, unit):
    landing(ctx, unit, "LANDED PR #3 FAILED h1")
    tick(ctx, unit)
    ctx.fx.heads["a-1"] = "h9"
    flow.resume(ctx, unit, "landing", accept_head=True)
    assert unit["checked_head"] == "h9"
    assert any("accepted h9" in what for _, what in unit["timeline"])


def test_reviews_diff_against_the_merge_base(ctx, unit):
    ctx.fx.base_at = "mb7"
    build_done(ctx, unit)
    assert unit["base"] == "mb7" and unit["started_base"] == "b0"
    assert "Review A-1 from mb7 to h1" in ctx.fx.started[0][2]


def test_sibling_merge_prompts_builders_still_at_work(ctx, unit):
    def other(name, status):
        return {**unit, "unit": name.upper(), "name": name, "status": status}

    units = {
        "A-1": {**unit, "status": "merged", "pr": "7"},
        "B-1": other("b-1", "building"),
        "C-1": other("c-1", "landing"),
        "D-1": other("d-1", "fixing"),
        "E-1": other("e-1", "reviewing"),
        "F-1": other("f-1", "waiting"),
    }
    ctx.fx.fail_prompt.add("d-1")
    flow.refresh_siblings(ctx, units, units["A-1"])
    assert [name for name, _ in ctx.fx.prompts] == ["b-1"]
    assert "A-1 merged" in units["E-1"]["refresh_pending"]
    text = ctx.fx.prompts[0][1]
    assert "main moved: A-1 merged as pull request #7" in text
    assert "merge origin/main" in text.lower()
    assert "refresh prompt failed" in units["D-1"]["timeline"][-1][1]
    assert "told to merge main after A-1" in units["B-1"]["timeline"][-1][1]


def queued(ctx, unit):
    build_done(ctx, unit)
    units = {"Z-1": {**unit, "unit": "Z-1", "name": "z-1", "status": "merged", "pr": "7"}}
    units["A-1"] = unit
    flow.refresh_siblings(ctx, units, units["Z-1"])
    assert ctx.fx.prompts == [] and "refresh_pending" in unit
    ctx.fx.clock += 5
    return review_paths(ctx, unit)


def test_a_queued_refresh_goes_out_with_the_fixes(ctx, unit):
    paths = queued(ctx, unit)
    write(ctx, paths["reviewer"], "changes needed\n")
    write(ctx, paths["second_reviewer"], "clean\n")
    assert tick(ctx, unit) is None and unit["status"] == "fixing"
    assert [name for name, _ in ctx.fx.prompts] == ["a-1", "a-1"]
    assert "Z-1 merged" in ctx.fx.prompts[1][1] and "refresh_pending" not in unit


def test_a_queued_refresh_goes_out_when_the_reviews_are_clean(ctx, unit):
    paths = queued(ctx, unit)
    for path in paths.values():
        write(ctx, path, "clean\n")
    assert tick(ctx, unit) is None and unit["status"] == "landing"
    assert [name for name, _ in ctx.fx.prompts] == ["a-1"]
    assert "refresh_pending" not in unit


def test_refresh_uses_the_project_brief(ctx, unit):
    (ctx.ws.briefs / "refresh.md").write_text("<MERGED> is in <DESTINATION> (<PR>): merge it.\n")
    units = {"A-1": {**unit, "status": "merged", "pr": "7"}, "B-1": {**unit, "name": "b-1"}}
    flow.refresh_siblings(ctx, units, units["A-1"])
    assert ctx.fx.prompts == [("b-1", "A-1 is in main (#7): merge it.")]


def test_build_minutes_from_the_land_log_are_marked_once(ctx, unit):
    landing(ctx, unit, "LANDED PR #3 SUCCESSFUL h1")
    log = Path(unit["jobs"]["land"]["log"])
    log.write_text("pushed\nBUILD-MINUTES 17.5\nLANDED PR #3 SUCCESSFUL h1\n")
    ctx.fx.ancestor = False
    assert tick(ctx, unit) is None
    assert tick(ctx, unit) is None
    marks = [what for _, what in unit["timeline"] if what.startswith("build minutes")]
    assert marks == ["build minutes 17.5"]


def test_land_without_build_minutes_marks_nothing(ctx, unit):
    landing(ctx, unit, "LANDED PR #3 SUCCESSFUL h1")
    assert tick(ctx, unit) == "merged"
    assert not any(what.startswith("build minutes") for _, what in unit["timeline"])


def test_failed_build_is_an_event(ctx, unit):
    landing(ctx, unit, "LANDED PR #3 FAILED h1")
    assert tick(ctx, unit) == "land: LANDED PR #3 FAILED h1"


def test_pr_step_failure_retried_once(ctx, unit):
    landing(ctx, unit, "FAILED pr-create: boom")
    assert tick(ctx, unit) is None
    finish(unit, "land", "FAILED pr-create: boom")
    assert tick(ctx, unit) == "land: FAILED pr-create: boom"


def test_print_review_with_no_output_retried_once(ctx, unit):
    build_done(ctx, unit)
    write(ctx, review_paths(ctx, unit)["reviewer"], "clean\n")
    finish(unit, "second_reviewer", "review rc 1", rc=1)
    assert tick(ctx, unit) is None
    assert [j[0] for j in ctx.fx.jobs_started].count("second_reviewer") == 2
    finish(unit, "second_reviewer", "review rc 1", rc=1)
    assert "ended with no output" in tick(ctx, unit)


def test_review_without_verdict_is_an_event(ctx, unit):
    build_done(ctx, unit)
    ctx.fx.clock += 5
    write(ctx, review_paths(ctx, unit)["reviewer"], "# Review\nlooks fine\n")
    assert "no verdict" in tick(ctx, unit)


def test_stalled_builder(ctx, unit):
    ctx.fx.states["a-1"] = "idle"
    assert flow.step(ctx, unit) is None
    assert "stalled" in tick(ctx, unit, 21 * 60)


def test_gone_and_blocked_builder(ctx, unit):
    ctx.fx.states["a-1"] = "gone"
    assert flow.step(ctx, unit) == "builder a-1 is gone"
    unit["status"] = "building"
    ctx.fx.states["a-1"] = "blocked"
    assert "blocked" in flow.step(ctx, unit)


def test_agy_builder_on_a_dialog(ctx, unit):
    unit["harness"] = "agy"
    ctx.fx.states["a-1"] = "idle"
    ctx.fx.dialogs.add("a-1")
    assert "dialog" in flow.step(ctx, unit)


def test_wedged_builder(ctx, unit):
    ctx.fx.ages["s0"] = 50 * 60
    assert "wedged" in flow.step(ctx, unit)


def test_job_over_limit(ctx, unit):
    unit["status"] = "landing"
    ctx.fx.background(unit, "land", ["land"])
    assert "has run over 4 hours" in tick(ctx, unit, 5 * 3600)


def test_docs_only_change_skips_reviews(ctx, unit):
    ctx.fx.files = ["docs/guide.md", "README.md"]
    build_done(ctx, unit)
    assert unit["required"] == []
    assert [label for label, _ in ctx.fx.jobs_started] == ["land"]
    finish(unit, "land", "LANDED PR #4 SUCCESSFUL h1")
    assert tick(ctx, unit) == "merged"


def test_agy_built_unit_uses_its_pipeline(ctx, unit):
    unit["harness"] = "agy"
    build_done(ctx, unit)
    assert set(review_paths(ctx, unit)) == {"reviewer"}


@pytest.mark.parametrize(
    "path,docs",
    [("docs/a.md", True), ("README.md", True), ("prompts/judge.md", False), ("src/x.py", False)],
)
def test_docs_only_globs(path, docs):
    assert matches(path, ("docs/**", "*.md")) is docs


def test_supervisor_refreshes_siblings_after_a_merge(ctx, unit, monkeypatch):
    from orchestrate import cli

    landing(ctx, unit, "LANDED PR #3 SUCCESSFUL h1")
    sibling = {**unit, "unit": "B-1", "name": "b-1", "status": "building", "jobs": {}}
    ctx.ws.save({"A-1": unit, "B-1": sibling})
    ctx.fx.states["b-1"] = "working"
    events = cli.supervise_once(ctx)
    assert "EVENT: A-1 merged" in events
    assert [name for name, _ in ctx.fx.prompts] == ["b-1"]
    assert "told to merge main after A-1" in ctx.ws.load()["B-1"]["timeline"][-1][1]


def test_hand_merge_refreshes_siblings(ctx, unit):
    import argparse

    from orchestrate import cli

    landing(ctx, unit, "LANDED PR #3 SUCCESSFUL h1")
    sibling = {**unit, "unit": "B-1", "name": "b-1", "status": "fixing", "jobs": {}}
    ctx.ws.save({"A-1": unit, "B-1": sibling})
    assert cli.cmd_merge(ctx, argparse.Namespace(unit="A-1", force=False)) == 0
    assert ctx.fx.merged == ["3"] and [name for name, _ in ctx.fx.prompts] == ["b-1"]
    assert ctx.ws.load()["A-1"]["status"] == "merged"
