"""A generated website: sites/<name>/, its own git repo, plus .builder/ (state and attempt logs, not committed)."""
import json
import shutil
import subprocess
import time
from pathlib import Path

from . import roadmap as roadmaps
from .config import SITES_DIR

SITE_GITIGNORE = ".builder/\n__pycache__/\n*.db\n"


class Project:
    def __init__(self, name: str, base: Path = SITES_DIR):
        self.name = name
        self.dir = base / name
        self.meta = self.dir / ".builder"

    # ---- lifecycle -------------------------------------------------------
    @classmethod
    def create(cls, name: str, roadmap_name: str, base: Path = SITES_DIR) -> "Project":
        p = cls(name, base)
        if p.dir.exists():
            raise ValueError(f"{p.dir} already exists")
        roadmaps.load(roadmap_name)  # validate early
        p.meta.mkdir(parents=True)
        (p.dir / ".gitignore").write_text(SITE_GITIGNORE)
        p.git("init", "-q", "-b", "main")
        p.git("add", "-A")
        p.git("commit", "-q", "-m", f"Start project (roadmap: {roadmap_name})")
        p.save_state({"roadmap": roadmap_name, "stage_done": 0, "created": time.strftime("%Y-%m-%d %H:%M")})
        return p

    def exists(self) -> bool:
        return (self.meta / "state.json").exists()

    # ---- state -----------------------------------------------------------
    def state(self) -> dict:
        return json.loads((self.meta / "state.json").read_text())

    def save_state(self, state: dict):
        (self.meta / "state.json").write_text(json.dumps(state, indent=2))

    def roadmap(self):
        return roadmaps.load(self.state()["roadmap"])

    # ---- git ---------------------------------------------------------------
    def git(self, *args) -> str:
        out = subprocess.run(["git", *args], cwd=self.dir, capture_output=True, text=True)
        if out.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
        return out.stdout

    def commit_stage(self, stage, model: str, tries: int) -> str:
        self.git("add", "-A")
        # --allow-empty: a stage can pass without changes (e.g. the feature already worked); still record it.
        self.git("commit", "-q", "--allow-empty", "-m", f"Stage {stage.number}: {stage.title}",
                 "-m", f"Built by {model} in {tries} {'try' if tries == 1 else 'tries'}.")
        return self.git("rev-parse", "--short", "HEAD").strip()

    def discard_changes(self):
        """Throw away a failed stage: back to the last passing commit (.builder/ is untouched)."""
        self.git("reset", "-q", "--hard")
        # Remove new files the failed attempt created. Plain -fd leaves ignored paths alone, which keeps
        # .builder/ (state + logs) safe; leftover __pycache__/*.db are harmless.
        self.git("clean", "-q", "-fd")

    def history(self) -> str:
        return self.git("log", "--format=%h  %ad  %s", "--date=format:%Y-%m-%d %H:%M")

    # ---- attempt log -----------------------------------------------------------
    def log_attempt(self, entry: dict, reply: str):
        d = self.meta / "attempts" / f"stage{entry['stage']}" / f"try{entry['attempt']}"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        (d / "reply.md").write_text(reply)
        (d / "result.json").write_text(json.dumps(entry, indent=2))
        with open(self.meta / "log.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")

    def attempts(self) -> list[dict]:
        log = self.meta / "log.jsonl"
        return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
