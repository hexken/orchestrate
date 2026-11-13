import re
from dataclasses import dataclass, field

COMMAND_KEYS = (
    "script",
    "run",
    "commands",
    "before_script",
    "after_script",
    "before-script",
    "after-script",
)
NOT_FOLLOWED = ("include", "extends", "uses")
KEY = re.compile(r"^(?P<lead>\s*(?:-\s+)?)(?P<key>[\w-]+):(?:\s+(?P<value>.*?))?\s*$")
ITEM = re.compile(r"^(?P<lead>\s*)-\s+(?P<value>.*?)\s*$")
BLOCK = ("|", ">", "|-", ">-", "|+", ">+")


@dataclass
class Steps:
    commands: list[str] = field(default_factory=list)
    unparsed: list[tuple[int, str, str]] = field(default_factory=list)
    origins: list[int] = field(default_factory=list)


def indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def block(lines: list[str], start: int, column: int, style: str) -> tuple[list[str], int]:
    body = []
    i = start
    while i < len(lines) and (not lines[i].strip() or indent(lines[i]) > column):
        if lines[i].strip():
            body.append(lines[i].strip())
        i += 1
    if style.startswith(">") and body:
        return [" ".join(body)], i
    return body, i


def continued(lines: list[str], start: int, column: int, steps: Steps) -> int:
    i = start
    while i < len(lines) and lines[i].strip() and indent(lines[i]) > column:
        if KEY.match(lines[i]) or ITEM.match(lines[i]):
            break
        steps.unparsed.append((i + 1, lines[i].strip(), "a command continued on the next line"))
        i += 1
    return i


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
        if item is None and KEY.match(line):
            return i
        if item is None:
            steps.unparsed.append((i + 1, line.strip(), "a command continued on the next line"))
            i += 1
            continue
        value = item["value"]
        if value in BLOCK:
            body, i = block(lines, i + 1, indent(line), value)
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
        start, origin = len(found.commands), i
        if value in BLOCK:
            body, i = block(lines, i + 1, column, value)
            found.commands += body
        elif value:
            found.commands.append(unquote(value))
            i = continued(lines, i + 1, column, found)
        else:
            i = items(lines, i + 1, column, found)
        found.origins += [origin] * (len(found.commands) - start)
    directories(lines, found)
    return found


def step_of(lines: list[str], at: int, column: int) -> range | None:
    for j in range(at, -1, -1):
        line = lines[j]
        if not line.strip():
            continue
        match = KEY.match(line)
        if match and "-" in match["lead"] and len(match["lead"]) == column:
            end = j + 1
            while end < len(lines) and (not lines[end].strip() or indent(lines[end]) >= column):
                end += 1
            return range(j, end)
        if indent(line) < column:
            return None
    return None


def directories(lines: list[str], found: Steps) -> None:
    for at, line in enumerate(lines):
        match = KEY.match(line)
        if not match or match["key"] != "working-directory":
            continue
        column = len(match["lead"])
        step = step_of(lines, at, column)
        if step is None:
            found.unparsed.append((at + 1, line.strip(), "`working-directory` outside a step"))
            continue
        folder = unquote(match["value"] or "")
        for index, origin in enumerate(found.origins):
            key = KEY.match(lines[origin])
            if origin in step and key and len(key["lead"]) == column:
                found.commands[index] = f"cd {folder} && {found.commands[index]}"


def normal(command: str) -> str:
    return " ".join(command.split())


def ignored(text: str, ignore: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in ignore)


def folder(path: str) -> str:
    path = path.removeprefix("./").rstrip("/")
    return "" if path in ("", ".") else path


CD = re.compile(r"^cd\s+(\S+)$")


def pairs(command: str) -> list[tuple[str, str]]:
    result = []
    where = saved = ""
    for raw in re.split(r"\s*(?:&&|;)\s*", normal(command)):
        opens, closes = raw.startswith("("), raw.endswith(")")
        part = normal(raw.removeprefix("(").removesuffix(")"))
        if opens:
            saved = where
        result.append((where, part))
        cd = CD.match(part)
        if cd:
            where = folder(cd.group(1))
        if closes:
            where = saved
    return result


def in_place(commands: list[str], origins: list[int]) -> list[str]:
    result = []
    where, previous = "", None
    for index, command in enumerate(commands):
        origin = origins[index] if index < len(origins) else index
        if origin != previous:
            where, previous = "", origin
        text = normal(command)
        result.append(f"cd {where} && {text}" if where else text)
        for place, part in pairs(text):
            cd = CD.match(part)
            if cd and place == "":
                where = folder(cd.group(1))
    return result


def uncovered(
    commands: list[str],
    checks: tuple[str, ...],
    ignore: tuple[str, ...],
    origins: list[int] | None = None,
) -> list[str]:
    wholes = {normal(c) for c in checks}
    local = {pair for c in checks for pair in pairs(c)}
    placed = in_place(commands, origins if origins is not None else list(range(len(commands))))
    result = []
    for command, text in zip(commands, placed, strict=True):
        bare = normal(command)
        if not bare or ignored(bare, ignore) or text in wholes or text in result:
            continue
        if not all(pair in local for pair in pairs(text)):
            result.append(text)
    return result
