"""The build loop.

process(): one work item -> prompt with the current code -> apply files -> cumulative checks -> repair
           (up to max_repairs) -> release (commit + tag) or roll back.
run():     advance the clock tick by tick, queueing each tick's features and library releases, and
           process the queue in order. Stops at the first item that can't be completed.
"""
import json
import os
import random
import subprocess
import time

from . import deps, llm
from .config import MAX_REPAIRS, PKG, SYSTEM_PROMPT, VENV_PY, ModelConfig
from .files import apply_files, current_code, lines_of_code
from .items import WorkItem, feature_item
from .project import Project

FORMAT_FIRST = """Reply with every file needed to run the app. Write each file as a heading line with its path, followed by a code block with the complete file contents, like this:

### File: app.py
```python
...
```"""

FORMAT_CHANGES = """Reply with the complete contents of every file you add or change. Write each file as a heading line with its path, followed by a code block with the complete file contents, like this:

### File: app.py
```python
...
```

Files you don't include stay exactly as they are."""


def build_prompt(request: str, code: str | None, error: str | None, libraries: str = "") -> str:
    libs = f"\n{libraries}\n" if libraries else ""
    if code is None and error is None:
        return f"{request}{libs}\n{FORMAT_FIRST}"
    msg = f"{request}{libs}\n"
    if code:
        msg += f"\nHere is the app's current code:\n\n{code}\n"
    if error:
        msg += ("\nI ran your latest version of the app and some checks failed:\n\n"
                f"```\n{error.strip()}\n```\n\nFix the problems.\n")
    return f"{msg}\n{FORMAT_CHANGES}"


# ---- checks ------------------------------------------------------------------------
def clear_dbs(project: Project):
    for db in project.dir.glob("*.db"):
        db.unlink(missing_ok=True)


def run_checks(project: Project, level: int, timeout=90) -> dict:
    """Run every roadmap check for features 1..level against the project's current files."""
    if level < 1:
        return {"passed": 0, "total": 0, "failed": [], "skipped": [], "failed_step": None, "error": None}
    clear_dbs(project)  # every check run starts from an empty database
    cmd = [str(VENV_PY), str(PKG / "checker.py"), str(project.dir), str(project.roadmap().checks), str(level)]
    env = {**os.environ, "PYTHONPATH": str(project.meta / "libs")}  # the site's homemade library versions
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return fail("timeout", f"The checks took longer than {timeout}s (the app may hang).")
    finally:
        clear_dbs(project)
    lines = [l for l in proc.stdout.strip().splitlines() if l.startswith("{")]
    if not lines:
        return fail("crash", (proc.stderr or proc.stdout)[-1500:])
    return json.loads(lines[-1])


def fail(step: str, error: str) -> dict:
    return {"passed": 0, "total": 1, "failed": [step], "skipped": [], "failed_step": step, "error": error}


# ---- one work item -------------------------------------------------------------------
def process(project: Project, item: WorkItem, cfg: ModelConfig, max_repairs: int = MAX_REPAIRS,
            log=print, chat=llm.chat) -> bool:
    """Do one work item. On success it's released and removed from the queue; on failure it stays queued."""
    st = project.state()
    level = item.feature if item.kind == "feature" else st["features_done"]
    log(f"\n== [{item.kind}] {item.title}  (tick {item.tick}, checks for features 1-{level})")
    error = None
    for attempt in range(1, max_repairs + 2):
        has_code = st["features_done"] > 0 or attempt > 1
        prompt = build_prompt(item.request(), current_code(project.dir) if has_code else None, error,
                              deps.docs_for_prompt(st["published"], st["deps"]))
        seed = random.randrange(1, 2**31)
        gen = chat(cfg, [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}], seed)
        applied = apply_files(gen["text"], project.dir)
        req = project.dir / "requirements.txt"
        new_deps, dep_errors = deps.resolve(req.read_text() if req.exists() else None, st["published"])
        if not applied["written"]:
            res = fail("no files found", "Your reply didn't contain any files in the `### File: <path>` format.")
        elif dep_errors:
            res = fail("requirements", "\n".join(dep_errors))
        elif item.kind == "dep_update" and new_deps.get(item.extra["lib"]) != item.extra["version"]:
            res = fail("upgrade", f"requirements.txt must pin {item.extra['lib']}=={item.extra['version']}"
                                  f" (it currently resolves to {new_deps.get(item.extra['lib'], 'nothing')}).")
        else:
            deps.install(project.meta / "libs", new_deps)
            res = run_checks(project, level)
        ctx_used = gen["prompt_tokens"] + gen["tokens"]
        entry = {"item": item.id, "kind": item.kind, "attempt": attempt, "tick": item.tick,
                 "when": time.strftime("%Y-%m-%d %H:%M:%S"), "model": cfg.model, "seed": seed,
                 "passed": res["passed"], "total": res["total"], "failed": res["failed"],
                 "skipped": res.get("skipped", []), "error": res.get("error"),
                 "files_written": applied["written"], "files_skipped": applied["skipped"],
                 "tokens": gen["tokens"], "prompt_tokens": gen["prompt_tokens"], "ctx_used": ctx_used,
                 "tok_s": gen["tok_s"], "seconds": round(gen["seconds"], 1), "truncated": gen["truncated"]}
        project.log_attempt(entry, gen["text"])
        warn = " [CONTEXT NEARLY FULL]" if ctx_used > 0.9 * cfg.num_ctx else ""
        warn += " [OUTPUT CUT OFF]" if gen["truncated"] else ""
        log(f"  try {attempt}: {res['passed']}/{res['total']} checks"
            + (f" (failed: {', '.join(res['failed'])})" if res["failed"] else "")
            + f"  {gen['seconds']:.0f}s, ctx {ctx_used}/{cfg.num_ctx}{warn}")
        if not res["failed"]:
            rel = project.release(item, cfg.model, attempt, new_deps)
            st = project.state()
            st["deps"] = new_deps
            st["queue"] = [d for d in st["queue"] if d["id"] != item.id]
            st["done"].append(item.id)
            if item.kind == "feature":
                st["features_done"] = max(st["features_done"], item.feature)
            project.save_state(st)
            log(f"  released {rel['version']} ({rel['commit']}): {item.kind}: {item.title}"
                f"  [{lines_of_code(project.dir)} lines of code]")
            return True
        error = res.get("error") or ", ".join(res["failed"])
    project.discard_changes()
    deps.install(project.meta / "libs", st["deps"])  # back to the last release's library versions
    log(f"  Failed after {max_repairs + 1} tries; rolled back to the last release. It stays at the front of the"
        f" queue. Every attempt is saved in {project.meta / 'attempts' / item.id}")
    return False


# ---- the clock --------------------------------------------------------------------------
def advance_tick(project: Project, log=print) -> int:
    """Move the clock forward one tick and queue that tick's events. Returns the new tick."""
    rm = project.roadmap()
    st = project.state()
    st["tick"] += 1
    t = rm.tick(st["tick"])
    events = []
    if t:
        for r in t.releases:  # libraries ship on their own schedule
            lib, version = r["lib"], r["version"]
            if version not in deps.all_versions(lib):
                raise ValueError(f"timeline publishes {lib} {version}, which isn't in ecosystem/{lib}/")
            st["published"].setdefault(lib, []).append(version)
            events.append(f"{lib} {version} released")
            current = st["deps"].get(lib)
            if current and deps.vkey(version) > deps.vkey(current):
                st["queue"].append(deps.dep_update_item(lib, version, current, st["tick"]).to_dict())
                events[-1] += " (upgrade queued)"
        for n in t.features:
            st["queue"].append(feature_item(rm.stage(n), st["tick"]).to_dict())
            events.append(f"feature {n} requested")
    project.save_state(st)
    log(f"\n-- tick {st['tick']}: " + (", ".join(events) if events else "nothing happens"))
    return st["tick"]


def run(project: Project, cfg: ModelConfig, ticks: int | None = None, max_repairs: int = MAX_REPAIRS,
        log=print, chat=llm.chat) -> bool:
    """Process the queue, then advance `ticks` ticks (default: to the end of the timeline), processing as we go."""
    rm = project.roadmap()
    advanced = 0
    while True:
        for item in project.queue():
            if not process(project, item, cfg, max_repairs, log, chat):
                return False
        if ticks is not None and advanced >= ticks:
            return True
        if project.state()["tick"] >= rm.last_tick:
            log("\nEnd of the roadmap timeline.")
            return True
        advance_tick(project, log)
        advanced += 1
