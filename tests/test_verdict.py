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
    ("Verdict: clean\n## Findings\nNone\n  - nested note\n", "clean"),
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
