import re

import pytest

from orchestrate.cli import COMMANDS, STANDALONE

from .conftest import ROOT

SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))
VERB = re.compile(r"(?:\borch|\bORCH)\s+([a-z][a-z-]+)")
LOCAL = re.compile(r"`((?:references|templates)/[\w./-]+)`")
FRONT = re.compile(r"\A---\nname: (?P<name>[\w-]+)\ndescription: (?P<desc>.+?)\n---\n", re.S)
EXPECTED = {
    "orchestrate",
    "orchestrate-onboard",
    "orchestrate-plan",
    "orchestrate-setup",
}


def test_expected_skills_exist():
    assert {p.parent.name for p in SKILLS} >= EXPECTED


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_frontmatter(path):
    match = FRONT.match(path.read_text())
    assert match, "frontmatter with name and description"
    assert match["name"] == path.parent.name
    assert 40 < len(match["desc"]) <= 1024


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_named_verbs_exist(path):
    verbs = set(COMMANDS) | set(STANDALONE) | {"verb"}
    named = set(VERB.findall(path.read_text()))
    for ref in path.parent.rglob("*.md"):
        named |= set(VERB.findall(ref.read_text()))
    assert named - verbs == set()


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_local_files_exist(path):
    for ref in LOCAL.findall(path.read_text()):
        assert (path.parent / ref).exists(), ref
