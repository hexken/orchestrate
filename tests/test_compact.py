from orchestrate.compact import scan, verify

LINE = "The limit is now 20 (changed from 10 at the owner's request)."


def test_narration_flagged():
    found = scan(f"# Limits\n\n{LINE}\n")
    assert [c.line for c in found] == [3]


def test_changelog_section_is_protected():
    text = f"# Spec\n\nPlain rule.\n\n## Changelog\n\n{LINE}\n\n## Rules\n\n{LINE}\n"
    assert [c.line for c in scan(text)] == [11]


def test_code_fences_ignored():
    assert scan(f"```\n{LINE}\n```\n") == []


def test_more_patterns():
    for line in [
        "Previously the queue held 5 items.",
        "Renamed to `orch` as requested.",
        "Retries were removed.",
        "Uses Postgres instead of SQLite.",
        "Added 2026-11-13: the gate blocks.",
        "**Update:** the cap is 3.",
    ]:
        assert scan(line), line
    assert scan("A version never changes.") == []


SPEC = """# Limits

**G7** A request must carry at most 20 items.

The limit is now 20 (changed from 10 at the owner's request).

| Key | Value |
|---|---|
| limit | 20 |

See [the plan](plan.md).
"""


def test_conservative_edit_passes():
    after = SPEC.replace(LINE, "The limit is 20.")
    assert verify(SPEC, after) == []


def test_dropping_an_id_fails():
    after = SPEC.replace(LINE, "The limit is 20.").replace("**G7** ", "")
    assert verify(SPEC, after) == ["dropped ID: G7"]


def test_dropping_a_must_sentence_fails():
    after = SPEC.replace("**G7** A request must carry at most 20 items.", "**G7**")
    problems = verify(SPEC, after)
    assert "dropped normative word: must" in problems
    assert "dropped normative word: at most" in problems
    assert "dropped quantity: 20items" in problems


def test_dropping_heading_row_link_or_block_fails():
    text = SPEC + "\n```\ncode\n```\n"
    after = (
        text.replace("# Limits\n", "")
        .replace("| limit | 20 |\n", "")
        .replace("[the plan](plan.md)", "the plan")
        .replace("```\ncode\n```\n", "")
    )
    problems = verify(text, after)
    assert {p.split(":")[0] for p in problems} >= {
        "dropped heading",
        "dropped table row",
        "dropped link",
        "dropped code block",
    }


def test_cli_verify_against_revision(project, capsys):
    from orchestrate.cli import main

    from .conftest import git

    repo = project["repo"]
    (repo / "spec.md").write_text(SPEC)
    git(repo, "add", "spec.md")
    git(repo, "commit", "-qm", "spec")
    (repo / "spec.md").write_text(SPEC.replace("**G7** ", ""))
    cfg = str(project["config"])
    assert main(["--config", cfg, "compact", "verify", "--rev", "HEAD", str(repo / "spec.md")]) == 1
    assert "dropped ID: G7" in capsys.readouterr().out
    assert main(["--config", cfg, "compact", "scan", str(repo / "spec.md")]) == 1
    assert "(unclassified): 1 candidate(s)" in capsys.readouterr().out
