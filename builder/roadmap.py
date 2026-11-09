"""A roadmap is a folder: stages/stageN.md (feature requests, in order) + checks.py (tests for those features)."""
import re
from dataclasses import dataclass
from pathlib import Path

from .config import ROADMAPS_DIR


@dataclass
class Stage:
    number: int
    title: str
    text: str


@dataclass
class Roadmap:
    name: str
    path: Path
    stages: list[Stage]

    @property
    def checks(self) -> Path:
        return self.path / "checks.py"

    def stage(self, n: int) -> Stage:
        return self.stages[n - 1]


def available() -> list[str]:
    return sorted(p.name for p in ROADMAPS_DIR.iterdir() if (p / "stages").is_dir())


def load(name: str) -> Roadmap:
    path = ROADMAPS_DIR / name
    if not (path / "stages").is_dir():
        raise ValueError(f"Unknown roadmap '{name}'. Available: {', '.join(available())}")
    files = sorted((path / "stages").glob("stage*.md"), key=lambda p: int(re.search(r"\d+", p.stem)[0]))
    stages = []
    for i, f in enumerate(files, start=1):
        text = f.read_text()
        title = text.strip().splitlines()[0].rstrip(".")
        stages.append(Stage(i, title, text))
    if not (path / "checks.py").exists():
        raise ValueError(f"Roadmap '{name}' has no checks.py")
    return Roadmap(name, path, stages)
