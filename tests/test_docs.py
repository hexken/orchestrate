from dataclasses import fields

from orchestrate import config

from .conftest import ROOT

SECTIONS = (
    config.Project,
    config.Herdr,
    config.Land,
    config.Timeouts,
    config.Review,
    config.Role,
    config.Pipeline,
    config.Source,
    config.Home,
    config.Breakpoints,
    config.SpecGate,
)


def test_every_config_key_is_in_the_readme():
    readme = ROOT.joinpath("README.md").read_text()
    keys = {f.name for cls in SECTIONS for f in fields(cls)} | {"paths", "share", "impl_docs"}
    missing = sorted(k for k in keys if f"`{k}`" not in readme)
    assert missing == []


def test_every_verb_is_in_the_readme():
    from orchestrate.cli import COMMANDS, STANDALONE

    readme = ROOT.joinpath("README.md").read_text()
    missing = sorted(v for v in {*COMMANDS, *STANDALONE} if f"`{v}" not in readme)
    assert missing == []
