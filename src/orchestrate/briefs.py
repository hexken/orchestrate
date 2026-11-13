import re
from pathlib import Path

PLACEHOLDER = re.compile(r"<([A-Z][A-Z_]+)>")


class BriefError(ValueError):
    pass


def fill(template: Path, values: dict[str, str], scope: Path | None = None) -> str:
    text = Path(template).read_text()
    for key, value in values.items():
        text = text.replace(f"<{key}>", value)
    left = sorted(set(PLACEHOLDER.findall(text)))
    if left:
        raise BriefError(f"{Path(template).name} has unfilled placeholders: {', '.join(left)}")
    if scope is not None:
        text = Path(scope).read_text().rstrip() + "\n\n" + text
    return text


def write(template: Path, out: Path, values: dict[str, str], scope: Path | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(fill(template, values, scope))
    return out
