from orchestrate.cli import main


def test_help_runs(capsys):
    assert main([]) == 0
    assert "orch" in capsys.readouterr().out
