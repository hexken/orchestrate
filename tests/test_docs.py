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


def test_scaffold_template_matches_config_defaults():
    import tomllib

    from orchestrate.scaffold import TEMPLATES

    data = tomllib.loads((TEMPLATES / "orchestrate.toml").read_text())
    sections = {
        "herdr": config.Herdr(),
        "land": config.Land(),
        "timeouts": config.Timeouts(),
        "review": config.Review(),
        "breakpoints": config.Breakpoints(),
        "spec_gate": config.SpecGate(),
        "sources": config.Sources(),
    }
    mismatched = []
    for name, defaults in sections.items():
        for key, value in data.get(name, {}).items():
            if isinstance(value, str) and "{{" in value:
                continue
            expected = getattr(defaults, key)
            got = tuple(value) if isinstance(value, list) else value
            if got == "" and expected is None:
                continue
            if got != expected:
                mismatched.append(f"{name}.{key}")
    assert mismatched == []
