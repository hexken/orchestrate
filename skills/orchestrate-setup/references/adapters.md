# Adapter contracts

An adapter is an executable file in `.orchestrate/adapters/`. `orch` calls it with a verb and arguments and reads its exit code and output. Examples: `$ORCHESTRATE_HOME/examples/adapters/` (`harness-claude`, `harness-agy`, `land-bkt`).

## Harness adapter: `adapters/harness-<name>`

| Verb | Arguments | Does | Output and exit |
|---|---|---|---|
| `describe` | | Says what it supports | JSON on stdout: `kind` (the name `herdr agent start --kind` uses), `interactive` (bool), `print` (bool); optional `cli` (the binary, if not `kind`) |
| `start` | `<name> <pane> <cwd> <brief-file>` | Starts an interactive session in the existing Herdr pane, names it with `herdr-name <name> <pane>`, and prompts it to read and carry out the brief file | Last stdout line: the session id (empty if unknown); non-zero exit on failure |
| `print` | `<prompt-file> <out-file>` | Runs one non-interactive prompt in the current directory | Writes `<out-file>` **only** on complete success, exit 0; otherwise writes nothing and exits non-zero |
| `skills-sync` | | Copies the skills in `ORCH_SKILLS` (colon-separated folders) where the harness needs real files; may do nothing | Exit 0 |

Environment: `ORCH_MODEL`, `ORCH_EFFORT`, `ORCH_MODE` (`interactive` or `print`) from the role; `ORCH_ADD_DIRS` (colon-separated folders the session must be able to read, at least the workspace).

**Dry run**: when `ORCH_DRY_RUN=1`, every verb prints the commands it would run (one per line) instead of running them, and exits 0. `orch conform` relies on this to check the model and effort reach the command without starting a session.

## Land adapter: `adapters/land-<name>`

| Verb | Arguments | Does | Output and exit |
|---|---|---|---|
| `describe` | | | JSON: `forge`; optional `cli` |
| `auth` | | Checks the forge CLI is logged in | Exit 0 when logged in |
| `land` | `<worktree> <branch> <commit> <title> <body-file>` | Pushes through the shared push step, opens the pull request if none is open for the branch, waits for the build of the pushed commit | Last line, always one of: `LANDED PR #<n> SUCCESSFUL <sha>`, `LANDED PR #<n> FAILED <sha>`, `LANDED PR #<n> TIMEOUT <sha>`, `FAILED <step>: <detail>` (use `FAILED pr-<step>` for a forge step that may be retried) |
| `merge` | `<pr>` | Merges the pull request; exit 0 also when it is already merged | Exit code |

The shared push step: `"$ORCH_PYTHON" -m orchestrate.push <worktree> <branch> <commit> <log>`. It merges the branch and the destination into the worktree's clean push checkout, runs `[land].checks`, pushes, and prints `RESULT: PUSHED <sha>` or `RESULT: FAILED at <step>`. Environment from `orch`: `ORCH_CONFIG`, `ORCH_PYTHON`, `ORCH_DESTINATION`, `ORCH_LOGS`, `ORCH_LAND_TRIES` (polls of the build, 30 seconds apart by default, `ORCH_LAND_POLL` overrides).

## Writing a new adapter

1. Copy the closest example.
2. From the tool's official documentation, find: the flags for model and effort (or the nearest equivalent); the non-interactive mode and how it reports failure; whether a session can raise a permission dialog that would stall it; where it reads rules and skills.
3. Keep the dry-run branch for every verb.
4. Run `orch conform harness <name> --role <role>` (or `orch conform land <name>`) until it passes; `--live` only with the user's yes.

## Pitfalls

- A print-mode run that is cut off must not leave a partial answer: write to a temporary file and move it into place on success.
- Some harnesses raise a dialog for a file outside the workspace even in auto mode; only a person can answer it. Grant the folders the agents need in the harness's own settings.
- Some harnesses ignore symlinked skills outside the workspace: copy them (`skills-sync`) and re-copy after changes.
- Never put a token or secret in an adapter. Adapters rely on the CLI's own login (keychain or config), which the user performs.
