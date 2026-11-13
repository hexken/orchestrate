from orchestrate import ci
from orchestrate.config import load
from orchestrate.doctor import ci_steps

LIST_OF_STEPS = """image: python:3.13
definitions:
  steps:
    - step: &checks
        name: checks
        script:
          - uv sync
          - uv run ruff check .
          - "uv run mypy"
          - |
            cd web
            npm run build
pipelines:
  default:
    - step: *checks
    - step:
        script:
          - uv run pytest -q
        after-script:
          - echo done
"""

ACTIONS = """jobs:
  test:
    steps:
      - uses: actions/checkout@v4
      - run: uv run ruff check .
      - name: tests
        run: |
          uv run pytest -q
          uv run mypy
"""


def test_list_of_steps_shape():
    found = ci.steps(LIST_OF_STEPS)
    assert found.commands == [
        "uv sync",
        "uv run ruff check .",
        "uv run mypy",
        "cd web",
        "npm run build",
        "uv run pytest -q",
    ]
    assert found.unparsed == []


def test_run_keys_shape():
    found = ci.steps(ACTIONS)
    assert found.commands == ["uv run ruff check .", "uv run pytest -q", "uv run mypy"]


def test_what_is_not_parsed_is_reported():
    text = "include:\n  - other.yml\nbuild:\n  script:\n    - make\n      --jobs 4\n"
    found = ci.steps(text)
    assert found.commands == ["make"]
    assert [(n, why) for n, _, why in found.unparsed] == [
        (1, "`include` is not followed"),
        (6, "a command continued on the next line"),
    ]


def test_uncovered_commands():
    checks = ("uv run ruff format . && uv run ruff check .", "uv run  pytest -q")
    commands = ["uv sync", "uv run ruff check .", "uv run pytest -q", "npm run build"]
    assert ci.uncovered(commands, checks, (r"^uv sync$",)) == ["npm run build"]


def config(tmp_path, land):
    repo = tmp_path / "myapp"
    repo.mkdir(exist_ok=True)
    path = tmp_path / "orchestrate.toml"
    path.write_text(f'[project]\nname = "myapp"\nrepo = "{repo}"\n[land]\n{land}')
    return load(path)


def test_doctor_lists_ci_steps_without_local_checks(tmp_path):
    cfg = config(
        tmp_path,
        'ci_config = "ci.yml"\nchecks = ["uv run ruff check . && uv run mypy"]\n'
        'ci_ignore = ["^uv sync$", "^cd web$"]\n',
    )
    (tmp_path / "myapp" / "ci.yml").write_text(LIST_OF_STEPS)
    lines = [str(line) for line in ci_steps(cfg)]
    assert [line.split("check: ")[1].split("  (")[0] for line in lines] == [
        "npm run build",
        "uv run pytest -q",
    ]
    assert all(line.startswith("missing") for line in lines)


def test_doctor_ci_covered_unset_and_unparsable(tmp_path):
    assert ci_steps(config(tmp_path, "")) == []
    cfg = config(tmp_path, 'ci_config = "ci.yml"\nchecks = ["make"]\n')
    ci_file = tmp_path / "myapp" / "ci.yml"
    ci_file.write_text("build:\n  script:\n    - make\n")
    assert [line.state for line in ci_steps(cfg)] == ["ok"]
    ci_file.write_text("stages: [build]\n")
    lines = ci_steps(cfg)
    assert [line.state for line in lines] == ["fail"] and "no steps found" in lines[0].what
    ci_file.write_text("include:\n  - other.yml\nbuild:\n  script:\n    - make\n")
    assert [line.state for line in ci_steps(cfg)] == ["fail"]
    cfg = config(tmp_path, 'ci_config = "ci.yml"\nchecks = ["make"]\nci_ignore = ["^include:"]\n')
    assert [line.state for line in ci_steps(cfg)] == ["ok"]
    cfg = config(tmp_path, 'ci_config = "gone.yml"\n')
    assert [line.state for line in ci_steps(cfg)] == ["missing"]
