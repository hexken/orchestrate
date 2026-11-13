import os
import shutil

from orchestrate.cli import main

from .conftest import EXAMPLES


def test_missing_land_adapter(fake_env, project, capsys, monkeypatch):
    text = project["config"].read_text().replace('adapter = "fake"', 'adapter = "gh"')
    project["config"].write_text(text)
    shutil.copy(EXAMPLES / "harness-agy", project["ws"] / "adapters" / "harness-agy")
    assert main(["--config", str(project["config"]), "doctor"]) == 1
    out = capsys.readouterr().out
    assert "missing  land adapter gh" in out
    assert "write it with the orchestrate-setup skill" in out
    assert "ok       harness adapter claude" in out


def test_all_present(fake_env, project, capsys, monkeypatch, tmp_path):
    ws = project["ws"]
    shutil.copy(EXAMPLES / "harness-agy", ws / "adapters" / "harness-agy")
    shutil.copy(EXAMPLES / "land-bkt", ws / "adapters" / "land-bkt")
    text = project["config"].read_text().replace('adapter = "fake"', 'adapter = "bkt"')
    project["config"].write_text(text)
    monkeypatch.setenv("FAKE_BKT_DIR", str(tmp_path / "bkt"))
    code = main(["--config", str(project["config"]), "doctor"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "forge login" in out


def test_no_config(fake_env, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ORCH_CONFIG", raising=False)
    assert main(["doctor"]) == 1
    assert "missing  orchestrate.toml" in capsys.readouterr().out


def test_outside_herdr(fake_env, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HERDR_ENV", "0")
    main(["doctor"])
    assert "fail     inside Herdr" in capsys.readouterr().out
    assert os.environ["HERDR_ENV"] == "0"
