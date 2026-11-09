"""Pull files out of a model's markdown reply, write them into the project, and show the project as text."""
import re
from pathlib import Path

# A path line ("### File: app.py", "**templates/base.html**", "`app.py`:") followed by a fenced block.
FILE_BLOCK = re.compile(
    r"^[#*\s]*(?:File:\s*)?`?(?P<path>[\w./-]+\.[A-Za-z0-9]+)`?\**:?\s*\n+"
    r"```[^\n]*\n(?P<body>.*?)^```\s*$",
    re.MULTILINE | re.DOTALL,
)
LONE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL)

CODE_SUFFIXES = {".py", ".html", ".css", ".js", ".txt", ".md"}
SKIP_DIRS = {".git", ".builder", "__pycache__"}
LANG = {".py": "python", ".html": "html", ".css": "css", ".js": "javascript"}


def parse_files(text: str) -> dict[str, str]:
    """Return {path: content}. Later blocks for the same path win."""
    files = {m["path"].removeprefix("./"): m["body"] for m in FILE_BLOCK.finditer(text)}
    if not files:  # fallback: a single unlabeled Python block is app.py
        blocks = LONE_BLOCK.findall(text)
        if len(blocks) == 1:
            files = {"app.py": blocks[0]}
    return files


def safe_path(root: Path, rel: str) -> Path | None:
    """Reject absolute paths, paths escaping the project, and the project's own git/builder folders."""
    if not rel or rel.startswith("/") or Path(rel).parts[0] in SKIP_DIRS:
        return None
    p = (root / rel).resolve()
    return p if p.is_relative_to(root) else None


def apply_files(text: str, project: Path) -> dict:
    """Write the reply's files into the project (in place). Returns {written, skipped}."""
    root = project.resolve()
    written, skipped = [], []
    for rel, content in parse_files(text).items():
        dest = safe_path(root, rel)
        if dest is None:
            skipped.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        written.append(rel)
    return {"written": written, "skipped": skipped}


def project_files(project: Path) -> list[Path]:
    return sorted(p for p in project.rglob("*")
                  if p.is_file() and p.suffix in CODE_SUFFIXES and not SKIP_DIRS & set(p.relative_to(project).parts))


def current_code(project: Path) -> str:
    """Every source file in the project, in the same `### File:` format the model replies with."""
    parts = []
    for p in project_files(project):
        rel = p.relative_to(project)
        parts.append(f"### File: {rel}\n```{LANG.get(p.suffix, '')}\n{p.read_text(errors='ignore')}\n```")
    return "\n\n".join(parts)


def lines_of_code(project: Path) -> int:
    return sum(p.read_text(errors="ignore").count("\n") for p in project_files(project))
