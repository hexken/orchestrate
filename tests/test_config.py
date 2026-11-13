from pathlib import Path

import pytest

from orchestrate.config import ConfigError, load


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "orchestrate.toml"
    path.write_text(text)
    return path


MINIMAL = '[project]\nname = "myapp"\nrepo = "~/Dev/myapp"\nplanning_repo = "~/Dev/myapp-plans"\n'


def test_minimal_file_gets_defaults(tmp_path):
    config = load(write(tmp_path, MINIMAL))
    assert config.project.repo == Path.home() / "Dev/myapp"
    assert config.project.destination == "main"
    assert config.project.planning_repo == Path.home() / "Dev/myapp-plans"
    assert config.project.branch_prefix == "agent/"
    assert config.workspace == Path.home() / "Dev/myapp/.orchestrate"
    assert config.timeouts.stall_minutes == 20
    assert config.timeouts.job_hours == 4
    assert config.timeouts.poll_seconds == 30
    assert "meets its outcome" in config.review.clean
    assert "changes needed" in config.review.hold
    assert config.review.verdict_lines == 60
    assert config.roles["builder"].harness == "claude"
    assert config.roles["second_reviewer"].mode == "print"
    assert config.pipeline["claude"].reviews == ("reviewer", "second_reviewer")
    assert config.pipeline["claude"].light == "" and config.pipeline["agy"].light == ""
    assert config.breakpoints.steps == ("freeze", "align", "compact", "digest")
    assert config.spec_gate.enabled is False
    assert config.sources.impl_docs == "deferred"


def test_role_override_keeps_other_defaults(tmp_path):
    text = MINIMAL + '[roles.builder]\nharness = "agy"\nmodel = "m1"\neffort = "high"\n'
    config = load(write(tmp_path, text))
    assert config.roles["builder"].model == "m1"
    assert config.roles["reviewer"].harness == "claude"


def test_bad_harness_name(tmp_path):
    text = MINIMAL + '[roles.builder]\nharness = "Bad Name"\nmodel = "m"\n'
    with pytest.raises(ConfigError, match=r"roles\.builder\.harness"):
        load(write(tmp_path, text))


def test_role_without_model(tmp_path):
    text = MINIMAL + '[roles.scout]\nharness = "claude"\n'
    with pytest.raises(ConfigError, match=r"roles\.scout\.model"):
        load(write(tmp_path, text))


def test_light_review_can_be_turned_back_on(tmp_path):
    text = MINIMAL + '[pipeline.claude]\nreviews = ["reviewer"]\nlight = "light_reviewer"\n'
    config = load(write(tmp_path, text))
    assert config.pipeline["claude"].light == "light_reviewer"
    assert config.pipeline["agy"].light == ""


def test_pipeline_naming_undefined_role(tmp_path):
    text = MINIMAL + '[pipeline.claude]\nreviews = ["ghost"]\nlight = "reviewer"\n'
    with pytest.raises(ConfigError, match=r"pipeline\.claude\.reviews"):
        load(write(tmp_path, text))


def test_missing_repo(tmp_path):
    with pytest.raises(ConfigError, match=r"project\.repo"):
        load(write(tmp_path, '[project]\nname = "x"\n'))


def test_source_entries(tmp_path):
    text = MINIMAL + (
        '[[sources.entries]]\npath = "spec.md"\nkind = "spec"\nowner = "owner"\n'
        'compact = "conservative"\n'
        '[[homes]]\nquestion = "What the product does"\npath = "spec.md"\n'
    )
    config = load(write(tmp_path, text))
    assert config.sources.entries[0].owner == "owner"
    assert config.homes[0].path == "spec.md"


def test_bad_source_kind(tmp_path):
    text = MINIMAL + '[[sources.entries]]\npath = "x"\nkind = "poem"\n'
    with pytest.raises(ConfigError, match=r"sources\.entries\[0\]\.kind"):
        load(write(tmp_path, text))
