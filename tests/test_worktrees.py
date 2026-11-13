from orchestrate.cli import main
from orchestrate.config import load


def test_worktrees_created_linked_and_recorded(project, capsys):
    repo = project["repo"]
    (repo / "CLAUDE.local.md").write_text("local\n")
    text = project["config"].read_text() + '[worktrees]\nshare = ["CLAUDE.local.md"]\n'
    project["config"].write_text(text)
    assert main(["--config", str(project["config"]), "worktrees", "--count", "2"]) == 0
    for i in (1, 2):
        path = repo.parent / f"myapp-wt{i}"
        assert (path / "app.py").exists()
        assert (repo.parent / f"myapp-wt{i}-push" / "app.py").exists()
        assert (path / ".orchestrate").resolve() == project["ws"].resolve()
        assert (path / "CLAUDE.local.md").read_text() == "local\n"
    config = load(project["config"])
    assert [p.name for p in config.worktrees] == ["myapp-wt1", "myapp-wt2"]
    assert config.share == ("CLAUDE.local.md",)


def test_worktrees_second_run_is_a_no_op(project, capsys):
    args = ["--config", str(project["config"]), "worktrees", "--count", "1"]
    main(args)
    before = project["config"].read_text()
    capsys.readouterr()
    main(args)
    out = capsys.readouterr().out
    assert "added" not in out and "linked" not in out
    assert project["config"].read_text() == before
