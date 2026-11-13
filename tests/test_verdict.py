import pytest

from orchestrate.briefs import BriefError, fill
from orchestrate.config import Review
from orchestrate.verdict import verdict

CASES = [
    ("I ran the review. ruff and mypy pass.\n\n**Verdict: hold**\n", "hold"),
    (
        "# Review\n\nThe new test is correct, but the route is not.\n\nVerdict: changes needed\n",
        "hold",
    ),
    ("- uv run mypy: pass\n- verdict: hold\n", "hold"),
    ("# Review of UNIT-A (first pass)\n\nVerdict: hold\n", "hold"),
    ("**Verdict: clean**\n", "clean"),
    ("meets its outcome\n\nfindings...\n", "clean"),
    ("Verdict: not clean\n", "hold"),
    ("Error: quota exceeded\n", "unreadable"),
    ("One-line verdict: hold\n- Clean up the temp dir\n", "hold"),
    ("Overall verdict: changes needed\n", "hold"),
    ("Verdict: rejected\n- Clean up the temp dir\n- Meets its outcome: no\n", "unreadable"),
    ("# Review\n- Clean up the temp dir\n", "unreadable"),
    ("Verdict: meets its outcome: no, G7 fails\n", "unreadable"),
    ("Running the tests now; waiting for the run to finish.\nclean\n\n## Findings\n", "clean"),
    ("# Review\nnote\n## Findings\nclean\n", "unreadable"),
    ("Waiting for task-15.\n" * 12 + "hold\n\n## Commands run\n", "hold"),
    ("clean\n\n## Findings\n1. low: a missing test\n", "hold"),
    ("clean\n\n## Findings\nNone.\n", "clean"),
    ("clean\n\n## Findings\n1. medium: the reader returns None for an empty member\n", "hold"),
    ("clean\n\n## Findings\n- None.\n", "clean"),
    ("clean\n\n## Findings\n- No findings\n- nothing to report\n", "clean"),
    ("clean\n\n## Commands run\n- uv run mypy\n", "clean"),
    ("clean\n\n## 2. Findings\n- **high** src/a.py:3 race\n", "hold"),
    ("clean\n## Findings\n- None.\n## Commands run\n- pytest: pass\n", "clean"),
    ("Verdict: clean\n## Findings\nNone\n  - nested note\n", "hold"),
    ("clean\n## Findings\n### 1. medium: race in commit\nThe lock is late.\n", "hold"),
    ("clean\n## Findings\nNone.\n## Commands\n### pytest\n- pass\n", "clean"),
    ("clean\n## Findings\nThe route answers 500 on an empty body.\n", "hold"),
    ("clean\n## Findings\n  1. bug\n", "hold"),
    ("clean\n## Findings\n+ x\n", "hold"),
    ("clean\n## Findings\n| severity | what |\n|---|---|\n| high | race |\n", "hold"),
    ("clean\n## Findings\n| severity | what |\n|---|---|\n", "clean"),
    ("clean\n\n**Findings**\n- a.py:1 bug\n", "hold"),
    ("clean\n## Blocking findings\n- race\n", "hold"),
    ("clean\n## Findings\n```sh\n# comment\n```\n- race\n", "hold"),
    ("clean\n## Findings\nNone.\n```\nx = 1\n```\n", "clean"),
    ("clean\n## Findings\nNo findings.\n", "clean"),
    ("clean\n**No findings.**\n", "clean"),
    ("clean\n## Findings: none\n", "clean"),
    ("clean\n## Findings\n### High\n- None.\n### Medium\n- None\n", "clean"),
    ("", None),
]


@pytest.mark.parametrize("text,want", CASES)
def test_verdict(tmp_path, text, want):
    path = tmp_path / "review.md"
    path.write_text(text)
    assert verdict(path, Review()) == want


def test_finding_items():
    from orchestrate.verdict import finding_items

    text = "hold\n## Findings\n1. a.py:1 bug\n   - detail\n2. None of the rows load\n- None.\n"
    assert finding_items(text) == ["1. a.py:1 bug", "2. None of the rows load"]
    assert finding_items("clean\n- a.py:1 bug\n") is None
    text = "hold\n## Findings\n### 1. race\nThe lock is late.\n### 2. gap\n## Commands\n- x\n"
    assert finding_items(text) == ["### 1. race", "### 2. gap"]
    severities = "hold\n## Findings\n### High\n1. a\n2. b\n### Medium\n1. c\n"
    assert finding_items(severities) == ["1. a", "2. b", "1. c"]
    detail = "hold\n## Findings\n1. race\n   the lock is late\n   - nested\n2. gap\nmore of 2\n"
    assert finding_items(detail) == ["1. race", "2. gap"]


def test_missing_file(tmp_path):
    assert verdict(tmp_path / "none.md", Review()) is None


def test_verdict_beyond_search_lines(tmp_path):
    path = tmp_path / "review.md"
    path.write_text("progress\n" * 61 + "clean\n")
    assert verdict(path, Review()) == "unreadable"


def test_custom_words(tmp_path):
    path = tmp_path / "review.md"
    path.write_text("Verdict: ship it\n")
    assert verdict(path, Review(clean=("ship it",), hold=("block",))) == "clean"


def test_fill_replaces_and_prepends_scope(tmp_path):
    template = tmp_path / "builder.md"
    template.write_text("Build <UNIT> on <BRANCH>.\n")
    scope = tmp_path / "scope.md"
    scope.write_text("Scope: tiny.\n")
    text = fill(template, {"UNIT": "A-1", "BRANCH": "agent/a-1"}, scope)
    assert text == "Scope: tiny.\n\nBuild A-1 on agent/a-1.\n"


def test_fill_refuses_leftover_placeholder(tmp_path):
    template = tmp_path / "builder.md"
    template.write_text("Build <UNIT> at <BASE>; keep <file:line> as is.\n")
    with pytest.raises(BriefError, match="BASE"):
        fill(template, {"UNIT": "A-1"})


def test_verdict_line_anywhere(tmp_path):
    path = tmp_path / "review.md"
    path.write_text("progress\n" * 70 + "Verdict: hold\n")
    assert verdict(path, Review()) == "hold"


def test_paragraphs_are_ignored_once_a_section_has_a_list():
    from orchestrate.verdict import finding_items

    text = (
        "hold\n## Findings\nTwo issues, most serious first:\n\n"
        "1. high: race in commit\n\n   The lock is taken late.\n\n"
        "A detail paragraph after a blank line.\n\n2. low: wording\n"
    )
    assert finding_items(text) == ["1. high: race in commit", "2. low: wording"]
    assert finding_items("hold\n## Findings\nThe route answers 500.\n") == [
        "The route answers 500."
    ]


def test_a_severity_heading_with_only_none_is_dropped():
    from orchestrate.verdict import finding_items

    text = "hold\n## Findings\n### High\n- None.\n### Low\n1. wording\n"
    assert finding_items(text) == ["1. wording"]


def test_findings_carry_their_severity():
    from orchestrate.verdict import findings

    text = (
        "hold\n## Findings\n### High\n1. race\n### Medium\n1. gap\n"
        "## Other findings\n1. low-level detail, nit: naming\n2. something\n"
    )
    assert [(f.text, f.severity) for f in findings(text)] == [
        ("1. race", "high"),
        ("1. gap", "medium"),
        ("1. low-level detail, nit: naming", "nit"),
        ("2. something", None),
    ]
