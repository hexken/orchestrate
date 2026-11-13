import pytest

from orchestrate import conform, herdr
from orchestrate.adapters import Harness
from orchestrate.config import Role

from .conftest import EXAMPLES

CLAUDE = Role("claude", "claude-model", "high")
AGY = Role("agy", "agy-model", "medium", "print")


@pytest.mark.parametrize("name,role", [("claude", CLAUDE), ("agy", AGY)])
def test_examples_conform_live(fake_env, name, role):
    assert conform.harness(Harness(EXAMPLES / f"harness-{name}"), role, live=True) == []


def test_claude_start_argv(fake_env, tmp_path):
    session = Harness(EXAMPLES / "harness-claude").start(
        CLAUDE, "unit-a", "p1", str(tmp_path), "/b.txt", ["/ws"]
    )
    calls = fake_env.read_text()
    assert session == "sess-1"
    assert "--model claude-model --effort high --permission-mode auto --add-dir /ws" in calls
    assert "herdr-name unit-a p1" in calls
    assert "Your brief is the file /b.txt" in calls


def test_agy_print_argv(fake_env, tmp_path):
    prompt = tmp_path / "p.txt"
    prompt.write_text("hi")
    out = tmp_path / "o.md"
    assert Harness(EXAMPLES / "harness-agy").answer(AGY, str(prompt), str(out), str(tmp_path))
    assert "--model agy-model --mode plan --disable-slash-commands" in fake_env.read_text()


def test_agy_skills_sync_copies(fake_env, tmp_path):
    skill = tmp_path / "skills" / "plan"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("x")
    Harness(EXAMPLES / "harness-agy").skills_sync([str(skill)])
    copy = tmp_path / "agy-skills" / "plan" / "SKILL.md"
    assert copy.read_text() == "x" and not copy.is_symlink()


def broken(tmp_path, describe, print_body):
    path = tmp_path / "harness-broken"
    path.write_text(
        "#!/usr/bin/env bash\ncase $1 in\n"
        f"describe) echo '{describe}';;\n"
        f"print) {print_body};;\n"
        "*) echo conform-model conform-effort /conform/dir;;\nesac\n"
    )
    path.chmod(0o755)
    return Harness(path)


def test_partial_output_on_failure_fails_conform(fake_env, tmp_path):
    adapter = broken(
        tmp_path,
        '{"kind": "x", "interactive": false, "print": true}',
        'echo conform-model; [[ -n $ORCH_DRY_RUN ]] && exit 0; echo partial >"$3"; '
        "[[ $ORCH_MODEL == orch-no-such-model ]] && exit 1; exit 0",
    )
    problems = conform.harness(adapter, AGY, live=True)
    assert "print (live) wrote an output file on failure" in problems


def test_describe_without_kind_fails_conform(fake_env, tmp_path):
    adapter = broken(tmp_path, '{"interactive": true, "print": true}', "exit 0")
    assert conform.harness(adapter, AGY) == ["describe: 'kind' missing or not str"]


def test_herdr_refuses_outside_herdr(monkeypatch):
    monkeypatch.delenv("HERDR_ENV", raising=False)
    with pytest.raises(herdr.HerdrError, match="HERDR_ENV"):
        herdr.agent_state("x")


def test_herdr_agent_state(fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_AGENT_STATUS", "working")
    assert herdr.agent_state("x") == "working"
