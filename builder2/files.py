"""One-file replies: pull a single file out of a model's reply and write it into the project."""
import re
from pathlib import Path

from builder.files import FILE_BLOCK, safe_path

ANY_BLOCK = re.compile(r"^```[^\n]*\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL)


def parse_one(text: str, path: str) -> str | None:
    """The contents of `path` in the reply: its labelled block, or else the reply's only code block.

    Returns None if the file isn't there, e.g. the reply was cut off before the closing fence.
    """
    labelled = [m["body"] for m in FILE_BLOCK.finditer(text) if m["path"].removeprefix("./") == path]
    if labelled:
        return labelled[-1]
    blocks = ANY_BLOCK.findall(text)
    return blocks[0] if len(blocks) == 1 else None


def write_file(project: Path, rel: str, content: str) -> bool:
    dest = safe_path(project.resolve(), rel)
    if dest is None:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    return True
