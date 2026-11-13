import json
from pathlib import Path

PROJECT = Path("{{repo}}")
SETTINGS = PROJECT / ".claude" / "settings.local.json"

ALLOW = [
    "Bash(git status:*)",
    "Bash(git log:*)",
    "Bash(git diff:*)",
    "Bash(git show:*)",
    "Bash(git branch:*)",
    "Bash(git rev-parse:*)",
    "Bash(git add:*)",
    "Bash(git commit:*)",
    "Bash(git fetch:*)",
    "Bash(git merge:*)",
    "Bash(git worktree list:*)",
    "Bash(ls:*)",
    "Bash(cat:*)",
    "Bash(head:*)",
    "Bash(tail:*)",
    "Bash(wc:*)",
    "Bash(grep:*)",
    "Bash(rg:*)",
    "Bash(find:*)",
    "Bash(herdr agent list:*)",
    "Bash(herdr agent get:*)",
    "Bash(herdr agent read:*)",
    "Bash(herdr agent prompt:*)",
    "Bash(herdr pane split:*)",
    "Bash(herdr-name:*)",
    "Bash({{workspace}}/bin/orch:*)",
]
ADDITIONAL_DIRECTORIES = ["{{workspace}}"]
AUTO_MODE_ALLOW = [
    "Pushing agent/* branches of this repository after the land checks pass; never a force "
    "push, never {{destination}} or another branch.",
    "Opening and editing pull requests from agent/* branches into {{destination}}.",
    "Merging the orchestrator's own pull requests into {{destination}} when the build is green "
    "and the reviews leave nothing open.",
]

data = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
permissions = data.setdefault("permissions", {})
allow = permissions.setdefault("allow", [])
allow += [rule for rule in ALLOW if rule not in allow]
dirs = permissions.setdefault("additionalDirectories", [])
dirs += [d for d in ADDITIONAL_DIRECTORIES if d not in dirs]
auto = data.setdefault("autoMode", {}).setdefault("allow", [])
auto += [s for s in AUTO_MODE_ALLOW if s not in auto]
SETTINGS.parent.mkdir(parents=True, exist_ok=True)
SETTINGS.write_text(json.dumps(data, indent=2) + "\n")
print(f"updated {SETTINGS}: {len(allow)} allow rules, {len(auto)} auto-mode sentences")
