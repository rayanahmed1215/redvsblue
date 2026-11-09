"""A roadmap is a folder:
  stages/stageN.md   feature requests, numbered in the order they must be built
  checks.py          tests for those features (cumulative)
  timeline.json      ticks: which features are requested and which library versions are published when
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import ROADMAPS_DIR


@dataclass
class Stage:
    number: int
    title: str
    text: str


@dataclass
class Tick:
    tick: int
    features: list[int] = field(default_factory=list)
    releases: list[dict] = field(default_factory=list)  # [{"lib": "mdlite", "version": "1.1.0"}]


@dataclass
class Roadmap:
    name: str
    path: Path
    stages: list[Stage]
    timeline: list[Tick]

    @property
    def checks(self) -> Path:
        return self.path / "checks.py"

    def stage(self, n: int) -> Stage:
        return self.stages[n - 1]

    def tick(self, t: int) -> Tick | None:
        return next((x for x in self.timeline if x.tick == t), None)

    @property
    def last_tick(self) -> int:
        return max((t.tick for t in self.timeline), default=0)


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
        stages.append(Stage(i, text.strip().splitlines()[0].rstrip("."), text))
    if not (path / "checks.py").exists():
        raise ValueError(f"Roadmap '{name}' has no checks.py")
    timeline = []
    if (path / "timeline.json").exists():
        timeline = [Tick(**t) for t in json.loads((path / "timeline.json").read_text())]
    else:  # default: one feature per tick
        timeline = [Tick(s.number, [s.number]) for s in stages]
    validate(stages, timeline)
    return Roadmap(name, path, stages, timeline)


def validate(stages, timeline):
    seen = [n for t in sorted(timeline, key=lambda t: t.tick) for n in t.features]
    if seen != sorted(seen) or len(seen) != len(set(seen)):
        raise ValueError("timeline must request each feature once, in order (features build on each other)")
    if any(n < 1 or n > len(stages) for n in seen):
        raise ValueError("timeline requests a feature number that has no stage file")
