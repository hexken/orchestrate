import json

from orchestrate.cli import main
from orchestrate.registry import Workspace
from orchestrate.report import build, markdown


def unit_folder(ws, unit, timeline, files, transcripts=None):
    folder = ws.archive / unit["unit"]
    folder.mkdir(parents=True)
    unit["timeline"] = timeline
    (folder / "unit.json").write_text(json.dumps(unit))
    for name, text in files.items():
        (folder / name).write_text(text)
    for agent, records in (transcripts or {}).items():
        (folder / f"{agent}.jsonl").write_text("\n".join(json.dumps(r) for r in records))


def usage(model, i, o):
    return {"message": {"model": model, "usage": {"input_tokens": i, "output_tokens": o}}}


def fixture(tmp_path):
    ws = Workspace(tmp_path)
    unit_folder(
        ws,
        {"unit": "A-1", "name": "a-1", "harness": "claude", "status": "merged"},
        [
            ["2026-01-01 10:00:00", "started on agent/a-1 at b0"],
            ["2026-01-01 10:40:00", "summary written at h1"],
            ["2026-01-01 10:40:00", "reviews started at h1 (2 required)"],
            ["2026-01-01 11:00:00", "fixes sent to the builder"],
            [
                "2026-01-01 11:10:00",
                "waiting: builder a-1 idle 20 minutes with nothing new: stalled",
            ],
            ["2026-01-01 11:15:00", "light review started at h2"],
            ["2026-01-01 11:25:00", "reviews clean"],
            ["2026-01-01 11:30:00", "build minutes 12.5"],
            ["2026-01-01 11:36:00", "build minutes 4"],
            ["2026-01-01 11:37:00", "merged PR #3"],
        ],
        {
            "A-1.md": "# A-1\n## Fixes\n- A-1-second_reviewer.md #1: fixed in abc\n"
            "- A-1-second_reviewer.md #2: fixed in abd\n"
            "- A-1-reviewer.md #1: declined: out of scope\n",
            "A-1-reviewer.md": "changes needed\n## Findings\n1. src/a.py:10 race\n",
            "A-1-second_reviewer.md": "hold\n- high src/a.py:12 bug\n- medium src/b.py:3 gap\n",
            "A-1-light.md": "clean\n",
        },
        {
            "a-1": [usage("opus", 100, 10), usage("opus", 50, 5), {"type": "user"}],
            "a-1-reviewer": [usage("opus", 30, 3)],
        },
    )
    unit_folder(
        ws,
        {"unit": "B-1", "name": "b-1", "harness": "agy", "status": "merged"},
        [
            ["2026-01-02 09:00:00", "started on agent/b-1 at b0"],
            ["2026-01-02 09:30:00", "summary written at h1"],
            ["2026-01-02 09:30:00", "reviews started at h1 (1 required)"],
            ["2026-01-02 09:45:00", "reviews clean"],
            ["2026-01-02 09:50:00", "merged PR #4"],
        ],
        {"B-1.md": "# B-1\n", "B-1-reviewer.md": "clean\n"},
    )
    return ws


def test_report(tmp_path):
    data = build(fixture(tmp_path))
    a = data["units"][0]
    assert a["stages"] == {
        "building": 40.0,
        "reviewing": 20.0,
        "fixing": 15.0,
        "light": 10.0,
        "landing": 12.0,
    }
    assert a["fix_rounds"] == 1
    assert a["build_minutes"] == 16.5 and data["units"][1]["build_minutes"] == 0
    assert a["events"] == {"stalled": 1}
    assert a["reviews"]["A-1-second_reviewer.md"] == {
        "role": "second_reviewer",
        "findings": 2,
        "fixed": 2,
        "declined": 0,
        "deferred": 0,
        "severities": {"unlabelled": 2},
    }
    assert data["reviewers"]["reviewer"] == {
        "findings": 1,
        "fixed": 0,
        "declined": 1,
        "deferred": 0,
        "reviews": 2,
    }
    assert data["tokens"]["builder / opus"]["input_tokens"] == 150
    assert data["tokens"]["reviewer / opus"]["output_tokens"] == 3
    assert "| A-1 | claude | merged | 40 | 20 | 15 | 10 | 12 | 1 | 16.5 | stalled 1 |" in markdown(
        data
    )


def test_stages_without_light_review():
    from orchestrate.report import stage_minutes

    timeline = [
        ["2026-01-01 10:00:00", "started on agent/a-1 at b0"],
        ["2026-01-01 10:30:00", "summary written at h1"],
        ["2026-01-01 10:30:00", "reviews started at h1 (2 required)"],
        ["2026-01-01 10:50:00", "fixes sent to the builder"],
        ["2026-01-01 11:05:00", "fixes in at h2: landing"],
        ["2026-01-01 11:25:00", "merged PR #3"],
    ]
    assert stage_minutes(timeline) == {
        "building": 30.0,
        "reviewing": 20.0,
        "fixing": 15.0,
        "landing": 20.0,
    }


def test_report_since(tmp_path):
    data = build(fixture(tmp_path), since="2026-01-02")
    assert [u["unit"] for u in data["units"]] == ["B-1"]


def test_report_cli_json(project, capsys):
    fixture(project["ws"])
    assert main(["--config", str(project["config"]), "report", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["units"]) == 2


RED = "; fails without the fix: "
SUMMARY = (
    "# A-1\nbuilt it\n\n## Fixes\n"
    f"- reviewer #1 (high): concurrent commit corrupts a version: fixed in 0eb0f21{RED}test_race\n"
    "  - the lock is taken before the read\n"
    "- reviewer #2 (medium): reader returns None for an empty member: "
    f"fixed in 1b590ea, 2c4d6e8{RED}test_empty_member\n"
    "- **second_reviewer #1 (low): fixed-size buffer: notes**: declined: out of scope\n"
    "- reviewer #3 (nit): wording: deferred: INBOX for a later unit\n"
    f"- light #1 (medium): the fix misses the retry path: fixed in 3d5f7a9{RED}test_retry\n"
    "- Merged origin/main at 9e8d7c6 (no conflicts).\n"
    "- Checks: ruff, mypy, pytest pass.\n"
    "\n## Notes\n"
    "- reviewer #9 (low): not a fix line: fixed in abc\n"
)


def test_fixes_lines_parsed(tmp_path):
    from orchestrate.report import fixes

    path = tmp_path / "A-1.md"
    path.write_text(SUMMARY)
    assert fixes(path, "A-1") == [
        {"reviewer": "reviewer", "n": "1", "severity": "high", "outcome": "fixed"},
        {"reviewer": "reviewer", "n": "2", "severity": "medium", "outcome": "fixed"},
        {"reviewer": "second_reviewer", "n": "1", "severity": "low", "outcome": "declined"},
        {"reviewer": "reviewer", "n": "3", "severity": "nit", "outcome": "deferred"},
        {"reviewer": "light", "n": "1", "severity": "medium", "outcome": "fixed"},
    ]


def test_old_fixes_shape_still_parsed(tmp_path):
    from orchestrate.report import fixes

    path = tmp_path / "A-1.md"
    path.write_text("**Fixes**\n- A-1-reviewer.md #2: declined: wrong\n")
    assert fixes(path, "A-1") == [
        {"reviewer": "reviewer", "n": "2", "severity": "unlabelled", "outcome": "declined"}
    ]


def test_review_yield_with_light_review(tmp_path):
    ws = Workspace(tmp_path)
    unit_folder(
        ws,
        {"unit": "A-1", "name": "a-1", "harness": "claude", "status": "merged"},
        [["2026-01-01 10:00:00", "started on agent/a-1 at b0"]],
        {
            "A-1.md": SUMMARY,
            "A-1-reviewer.md": "changes needed\n## Findings\n1. high race\n2. medium None\n"
            "3. nit wording\n",
            "A-1-second_reviewer.md": "hold\n## Findings\n1. low buffer\n",
            "A-1-light.md": "hold\n## Findings\n1. retry path missed\n   - detail\n",
        },
    )
    reviews = build(ws)["units"][0]["reviews"]
    assert reviews["A-1-reviewer.md"]["findings"] == 3
    assert reviews["A-1-reviewer.md"]["fixed"] == 2
    assert reviews["A-1-reviewer.md"]["deferred"] == 1
    assert reviews["A-1-reviewer.md"]["severities"] == {"high": 1, "medium": 1, "nit": 1}
    assert reviews["A-1-second_reviewer.md"]["declined"] == 1
    assert reviews["A-1-light.md"]["findings"] == 1
    assert reviews["A-1-light.md"]["fixed"] == 1


def test_fixes_ignores_nested_bullets_and_reads_every_round(tmp_path):
    from orchestrate.report import fixes

    path = tmp_path / "A-1.md"
    path.write_text(
        "# A-1\n## Fixes\n"
        "- reviewer #1 (high): race: fixed in abc1234; fails without the fix: test_race\n"
        "  - fixes the lock order first\n"
        "- reviewer #2 (low): gap: declined: out of scope\n"
        "## Checks\n- fixes nothing: fixed in x\n"
        "## Fixes (round 2)\n"
        "- second_reviewer #1 (medium): retry: fixed in bcd2345; fails without the fix: test_r\n"
    )
    assert [(f["reviewer"], f["n"], f["outcome"]) for f in fixes(path, "A-1")] == [
        ("reviewer", "1", "fixed"),
        ("reviewer", "2", "declined"),
        ("second_reviewer", "1", "fixed"),
    ]


def test_the_first_strict_status_wins(tmp_path):
    from orchestrate.report import fixes

    path = tmp_path / "A-1.md"
    path.write_text(
        "## Fixes\n- reviewer #1 (high): race: declined: fixed elsewhere in abc1234\n"
        "- reviewer #2 (low): the fixed: header: deferred: INBOX\n"
    )
    assert [f["outcome"] for f in fixes(path, "A-1")] == ["declined", "deferred"]


def test_a_sentence_starting_with_fixes_is_no_section(tmp_path):
    from orchestrate.report import fixes

    path = tmp_path / "A-1.md"
    path.write_text("# A-1\nFixes the race in commit.\n- reviewer #1 (high): x: fixed in a1b2c3d\n")
    assert fixes(path, "A-1") == []
    path.write_text("# A-1\nFixes:\n- reviewer #1 (high): x: fixed in a1b2c3d\n")
    assert len(fixes(path, "A-1")) == 1


def test_replay_prints_every_archived_review(tmp_path, capsys):
    from orchestrate.config import Review
    from orchestrate.report import replay

    ws = fixture(tmp_path)
    rows = replay(ws, Review())
    assert rows == [
        ("A-1", "A-1-light.md", "clean", 0),
        ("A-1", "A-1-reviewer.md", "hold", 1),
        ("A-1", "A-1-second_reviewer.md", "hold", 2),
        ("B-1", "B-1-reviewer.md", "clean", 0),
    ]


def test_verdict_replay_cli(project, capsys):
    fixture(project["ws"])
    assert main(["--config", str(project["config"]), "verdict", "--replay"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "A-1/A-1-light.md\tclean\t0" and len(out) == 4


def test_verdict_of_given_files(project, tmp_path, capsys):
    review = tmp_path / "r.md"
    review.write_text("clean\n## Findings\n1. high: race\n")
    assert main(["--config", str(project["config"]), "verdict", str(review)]) == 0
    assert capsys.readouterr().out == f"{review}\thold\t1\n"


def test_median_stage_times_by_size(tmp_path):
    data = build(fixture(tmp_path), sizes={"A-1": "M", "B-1": "S"})
    assert data["sizes"]["M"] == {
        "units": 1,
        "median": {
            "building": 40.0,
            "reviewing": 20.0,
            "fixing": 15.0,
            "light": 10.0,
            "landing": 12.0,
            "total": 97.0,
        },
    }
    assert data["sizes"]["S"]["median"]["total"] == 50.0
    assert "| S | 1 | 30 | 15 | 0 | 0 | 5 | 50 |" in markdown(data)
    assert "sizes" not in build(fixture(tmp_path / "x"))
