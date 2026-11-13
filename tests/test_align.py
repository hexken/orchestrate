from orchestrate import align
from orchestrate.cli import main
from orchestrate.config import load

from .conftest import git


def configure(project, tmp_path, spec, plan, memory):
    planning = tmp_path / "myapp-plans"
    planning.mkdir()
    (planning / "spec.md").write_text(spec)
    (planning / "plan.md").write_text(plan)
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "note.md").write_text(memory)
    repo = project["repo"]
    (repo / "app.py").write_text("def build_version():\n    return 1\n")
    git(repo, "add", "app.py")
    git(repo, "commit", "-qm", "code")
    project["config"].write_text(
        f'[project]\nname = "myapp"\nrepo = "{repo}"\nplanning_repo = "{planning}"\n'
        '[[sources.entries]]\npath = "spec.md"\nkind = "spec"\nowner = "owner"\nroot = "planning"\n'
        '[[sources.entries]]\npath = "plan.md"\nkind = "plan"\nroot = "planning"\n'
        f'[[sources.entries]]\npath = "{mem}/*.md"\nkind = "memory"\n'
        '[[homes]]\nquestion = "What the product does"\npath = "spec.md"\n'
    )
    return load(project["config"])


SPEC = "# Spec\n\n## Glossary\n\n| Term | Meaning |\n|---|---|\n| Version | a fixed copy |\n"


def test_findings_name_file_and_line(project, tmp_path):
    config = configure(
        project,
        tmp_path,
        SPEC,
        "# Plan\n\n**Version** is a fixed copy.\n\nSee `app.py:400` and `build_version()`.\n",
        "# Note\n\nThe helper `old_helper()` builds versions.\n",
    )
    found = {(f.kind, f.where.split("/")[-1], f.what) for f in align.run(config).findings}
    assert (
        "dead reference",
        "plan.md:5",
        "`app.py:400` is past the end of the file (2 lines)",
    ) in found
    assert ("dead reference", "note.md:3", "`old_helper()` is not in the implementation") in found
    assert any(k == "defined twice" and "'version'" in w for k, _, w in found)
    assert not any("build_version" in w for _, _, w in found)


def test_clean_sources_give_empty_worklist(project, tmp_path, capsys):
    configure(
        project,
        tmp_path,
        SPEC,
        "# Plan\n\nSee `app.py:1` and `build_version()`.\n",
        "# Note\n\nVersions are built by `build_version()`.\n",
    )
    assert main(["--config", str(project["config"]), "align"]) == 0
    assert "0 item(s)" in capsys.readouterr().out


def test_unclassified_planning_file(project, tmp_path):
    config = configure(project, tmp_path, SPEC, "# Plan\n", "# Note\n")
    (tmp_path / "myapp-plans" / "stray.md").write_text("# Stray\n")
    kinds = [(f.kind, f.where.split("/")[-1]) for f in align.run(config).findings]
    assert ("unclassified", "stray.md") in kinds


def test_code_fences_are_not_references(project, tmp_path):
    config = configure(project, tmp_path, SPEC, "# Plan\n\n```\n`gone_function()`\n```\n", "# N\n")
    assert align.run(config).findings == []
