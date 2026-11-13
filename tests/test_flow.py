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

    def git(self, cwd, *args, check=True):
        return ""

    def agent_state(self, name):
        return self.states.get(name, "working")

    def dialog(self, name):
        return name in self.dialogs

    def prompt(self, name, message):
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
