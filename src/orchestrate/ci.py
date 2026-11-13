import re
from dataclasses import dataclass, field

COMMAND_KEYS = ("script", "run", "commands")
NOT_FOLLOWED = ("include", "extends", "uses")
KEY = re.compile(r"^(?P<lead>\s*(?:-\s+)?)(?P<key>[\w-]+):(?:\s+(?P<value>.*?))?\s*$")
ITEM = re.compile(r"^(?P<lead>\s*)-\s+(?P<value>.*?)\s*$")
BLOCK = ("|", ">", "|-", ">-", "|+", ">+")


@dataclass
class Steps:
    commands: list[str] = field(default_factory=list)
    unparsed: list[tuple[int, str, str]] = field(default_factory=list)


def indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def block(lines: list[str], start: int, column: int) -> tuple[list[str], int]:
    body = []
    i = start
    while i < len(lines) and (not lines[i].strip() or indent(lines[i]) > column):
        if lines[i].strip():
            body.append(lines[i].strip())
        i += 1
    return body, i


def items(lines: list[str], start: int, column: int, steps: Steps) -> int:
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        item = ITEM.match(line)
        if indent(line) < column or (item is None and indent(line) <= column):
            return i
        if item is None:
            steps.unparsed.append((i + 1, line.strip(), "a command continued on the next line"))
            i += 1
            continue
        value = item["value"]
        if value in BLOCK:
            body, i = block(lines, i + 1, indent(line))
            steps.commands += body
            continue
        steps.commands.append(unquote(value))
        i += 1
    return i


def steps(text: str) -> Steps:
    found = Steps()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = KEY.match(lines[i])
        if not match or lines[i].lstrip().startswith("#"):
            i += 1
            continue
        key, value, column = match["key"], match["value"] or "", len(match["lead"])
        if key in NOT_FOLLOWED:
            found.unparsed.append((i + 1, lines[i].strip(), f"`{key}` is not followed"))
        if key not in COMMAND_KEYS:
            i += 1
            continue
        if value in BLOCK:
            body, i = block(lines, i + 1, column)
            found.commands += body
        elif value:
            found.commands.append(unquote(value))
            i += 1
        else:
            i = items(lines, i + 1, column, found)
    return found


def normal(command: str) -> str:
    return " ".join(command.split())


def ignored(text: str, ignore: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in ignore)


def uncovered(commands: list[str], checks: tuple[str, ...], ignore: tuple[str, ...]) -> list[str]:
    local = "\n".join(normal(c) for c in checks)
    result = []
    for command in commands:
        text = normal(command)
        if text and not ignored(text, ignore) and text not in local and text not in result:
            result.append(text)
    return result
