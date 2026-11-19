"""The plan step: the model says which files it will touch and how they connect, before writing any code.

Only the `## Files` list is read by the Builder. The rest of the plan (connections, libraries) is passed
back to the model with every file it writes, so all the files follow the same script.
"""
import re
from pathlib import Path

from builder.files import LANG, safe_path
from builder.items import WorkItem

MAX_PLAN_FILES = 12

PLAN_FORMAT = """Do not write any code yet. First write a short plan for this work, with exactly these three sections:

## Files
One line for every file you will create or change, and no other files:
- app.py (change): what changes in it
- templates/example.html (new): what it shows

## Connections
Every name that more than one file relies on, saying where it is defined and where it is used:
- routes: the URL, its function name in app.py, the template it renders and the variables it passes in
- Jinja filters and helper functions that templates call
- form field names, and database tables and columns
If a file uses something that changes, that file must be listed under Files.

## Libraries
The libraries the app uses and the exact requirements.txt lines. If they change, list requirements.txt under Files.

Keep the plan short: a few lines per file and no code blocks. Files you don't list stay exactly as they are."""

SECTION = re.compile(r"^#+\s*Files\b.*?\n(?P<body>.*?)(?=^#+\s|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE)
FILE_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s*[`*]*(?P<path>[\w./-]+\.[A-Za-z0-9]+)[`*]*", re.MULTILINE)


def parse_plan(text: str) -> list[str]:
    """The paths listed under `## Files`, in order, without duplicates."""
    m = SECTION.search(text)
    paths = [p.removeprefix("./") for p in FILE_LINE.findall(m["body"] if m else text)]
    return list(dict.fromkeys(paths))


def check_plan(paths: list[str], project: Path, item: WorkItem) -> tuple[list[str], str | None]:
    """Returns (files in the order to write them, error). Files that others depend on come first."""
    paths = list(paths)
    if item.kind == "dep_update" and "requirements.txt" not in paths:
        paths.append("requirements.txt")  # an upgrade always changes the pin
    if not paths:
        return [], "Your plan didn't list any files. Put one `- path (new|change): ...` line per file under `## Files`."
    root = project.resolve()
    unsafe = [p for p in paths if safe_path(root, p) is None]
    if unsafe:
        return [], f"Your plan lists files outside the project or in protected folders: {', '.join(unsafe)}."
    if len(paths) > MAX_PLAN_FILES:
        return [], f"Your plan lists {len(paths)} files; change at most {MAX_PLAN_FILES} at a time."
    rank = lambda p: 0 if p == "requirements.txt" else 1 if p.endswith(".py") else 2  # noqa: E731
    return sorted(paths, key=rank), None


def _base(request: str, code: str | None, libraries: str, error: str | None) -> str:
    msg = request + (f"\n{libraries}\n" if libraries else "")
    if code:
        msg += f"\nHere is the app's current code:\n\n{code}\n"
    if error:
        msg += f"\nYour last attempt (the code above) didn't work:\n\n```\n{error.strip()}\n```\n"
    return msg


def plan_prompt(request: str, code: str | None, libraries: str = "", prev_plan: str | None = None,
                error: str | None = None) -> str:
    msg = _base(request, code, libraries, error)
    if error and prev_plan:
        msg += f"\nThis was your plan for that attempt:\n\n{prev_plan.strip()}\n"
    if error:
        msg += "\nPlan the fix. List only the files that need to change to fix it.\n"
    return f"{msg}\n{PLAN_FORMAT}"


def file_prompt(request: str, code: str | None, libraries: str, plan: str, path: str, exists: bool,
                error: str | None = None) -> str:
    msg = _base(request, code, libraries, error)
    what = f"It replaces the current `{path}`." if exists else "It is a new file."
    return (f"{msg}\nHere is the plan for this work:\n\n{plan.strip()}\n\n"
            f"Write `{path}` now. {what} Follow the plan exactly: use the same names it gives for routes, "
            f"functions, templates, variables, form fields and database columns. Reply with only this one "
            f"file, complete, like this:\n\n### File: {path}\n```{LANG.get(Path(path).suffix, '')}\n...\n```")
