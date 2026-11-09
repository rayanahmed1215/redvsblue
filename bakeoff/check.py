"""Pull files out of a model's markdown reply, write them to disk, and grade them."""
import json
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV_PY = HERE / ".venv" / "bin" / "python"
SMOKE = HERE / "smoke.py"

# A path line (e.g. "### File: app.py", "**templates/base.html**", "`app.py`:") followed by a fenced block.
FILE_BLOCK = re.compile(
    r"^[#*\s]*(?:File:\s*)?`?(?P<path>[\w./-]+\.[A-Za-z0-9]+)`?\**:?\s*\n+"
    r"```[^\n]*\n(?P<body>.*?)^```\s*$",
    re.MULTILINE | re.DOTALL,
)
LONE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL)


def parse_files(text: str) -> dict[str, str]:
    """Return {path: content}. Later blocks for the same path win."""
    files = {m["path"].removeprefix("./"): m["body"] for m in FILE_BLOCK.finditer(text)}
    if not files:  # fallback: a single unlabeled Python block is app.py
        blocks = LONE_BLOCK.findall(text)
        if len(blocks) == 1:
            files = {"app.py": blocks[0]}
    return files


def safe_path(root: Path, rel: str) -> Path | None:
    """Reject absolute paths and anything escaping the output folder."""
    p = (root / rel).resolve()
    return p if rel and not rel.startswith("/") and p.is_relative_to(root) else None


def write_files(text: str, out_dir: Path, base_dir: Path | None = None) -> dict:
    """Write the reply's files into out_dir, on top of a copy of base_dir if given (for repairs)."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    if base_dir:
        shutil.copytree(base_dir, out_dir, ignore=shutil.ignore_patterns("raw_output.txt", "blog.db", "__pycache__"))
    else:
        out_dir.mkdir(parents=True)
    (out_dir / "raw_output.txt").write_text(text)
    root = out_dir.resolve()
    written, skipped = [], []
    for rel, content in parse_files(text).items():
        dest = safe_path(root, rel)
        if dest is None:
            skipped.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        written.append(rel)
    loc = sum(
        p.read_text(errors="ignore").count("\n")
        for p in root.rglob("*")
        if p.is_file() and p.suffix in {".py", ".html", ".css", ".js"}
    )
    return {"parsed": bool(written), "files": written, "loc": loc, "skipped": skipped}


def grade(app_dir: Path, timeout=30) -> dict:
    db = app_dir / "blog.db"
    if db.exists():
        db.unlink()
    try:
        proc = subprocess.run(
            [str(VENV_PY), str(SMOKE), str(app_dir)],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"passed": 0, "failed_step": "timeout", "error": f"smoke test exceeded {timeout}s"}
    lines = [l for l in proc.stdout.strip().splitlines() if l.startswith("{")]
    if not lines:
        return {"passed": 0, "failed_step": "crash", "error": (proc.stderr or proc.stdout)[-1500:]}
    return json.loads(lines[-1])
