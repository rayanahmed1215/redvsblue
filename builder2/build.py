"""The build loop, version 2: plan first, then write one file per model call.

process(): one work item -> plan call (which files, how they connect) -> one call per planned file ->
           cumulative checks -> retry with a new plan (up to max_repairs) -> release or roll back.
run():     same clock and queue as builder/build.py.

Everything that didn't change (the clock, releases, libraries, the model server) comes from `builder`.
"""
import json
import os
import random
import subprocess
import time
from pathlib import Path

from builder import deps, llm
from builder.build import advance_tick, clear_dbs, fail, remove_new_files
from builder.config import MAX_REPAIRS, SYSTEM_PROMPT, VENV_PY, ModelConfig
from builder.files import current_code, lines_of_code
from builder.items import WorkItem
from builder.project import Project

from .files import parse_one, write_file
from .plan import check_plan, file_prompt, parse_plan, plan_prompt

CHECKER = Path(__file__).resolve().parent / "checker.py"  # builder2's checker adds the "files agree" check


def run_checks(project: Project, level: int, timeout=90) -> dict:
    """Run every roadmap check for features 1..level against the project's current files."""
    if level < 1:
        return {"passed": 0, "total": 0, "failed": [], "skipped": [], "failed_step": None, "error": None}
    clear_dbs(project)  # every check run starts from an empty database
    before = {f for f in project.dir.rglob("*") if not ({".git", ".builder", ".venv"} & set(f.relative_to(project.dir).parts))}
    cmd = [str(VENV_PY), str(CHECKER), str(project.dir), str(project.roadmap().checks), str(level)]
    env = {**os.environ, "PYTHONPATH": str(project.meta / "libs")}  # the site's homemade library versions
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return fail("timeout", f"The checks took longer than {timeout}s (the app may hang).")
    finally:
        clear_dbs(project)
        remove_new_files(project, before)  # e.g. avatars the checks uploaded; don't commit test data
    lines = [l for l in proc.stdout.strip().splitlines() if l.startswith("{")]
    if not lines:
        return fail("crash", (proc.stderr or proc.stdout)[-1500:])
    return json.loads(lines[-1])


def write_planned_files(project: Project, paths, prompt_for, ask) -> tuple[list[str], list[str], dict | None]:
    """Ask for each planned file in its own call and write it. Stops at the first file that doesn't arrive.

    Returns (files written, raw replies, failure or None).
    """
    written, replies = [], []
    for path in paths:
        gen = ask(path, prompt_for(path))
        replies.append(f"<!-- reply for {path} -->\n{gen['text']}")
        content = parse_one(gen["text"], path)
        if content is None:
            why = ("was cut off before the file ended, so it is too long for one reply. Make the file shorter"
                   if gen["truncated"] else "didn't contain the file as one code block")
            return written, replies, fail("file not written", f"Your reply for `{path}` {why}.")
        write_file(project.dir, path, content)
        written.append(path)
    return written, replies, None


def process(project: Project, item: WorkItem, cfg: ModelConfig, max_repairs: int = MAX_REPAIRS,
            log=print, chat=llm.chat) -> bool:
    """Do one work item. On success it's released and removed from the queue; on failure it stays queued."""
    st = project.state()
    level = item.feature if item.kind == "feature" else st["features_done"]
    log(f"\n== [{item.kind}] {item.title}  (tick {item.tick}, checks for features 1-{level})")
    libs = deps.docs_for_prompt(st["published"], st["deps"])
    error = prev_plan = None
    for attempt in range(1, max_repairs + 2):
        seed = random.randrange(1, 2**31)
        calls = []

        def ask(step, prompt):
            gen = chat(cfg, [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}], seed)
            calls.append({"step": step, "tokens": gen["tokens"], "prompt_tokens": gen["prompt_tokens"],
                          "tok_s": gen["tok_s"], "seconds": round(gen["seconds"], 1), "truncated": gen["truncated"]})
            return gen

        # 1. The plan: which files change and how they connect.
        plan = ask("plan", plan_prompt(item.request(), current_code(project.dir), libs, prev_plan, error))["text"]
        paths, plan_error = check_plan(parse_plan(plan), project.dir, item)
        # 2. One call per planned file. Each call sees the files already written in this attempt.
        written, replies, res = [], [], fail("plan", plan_error) if plan_error else None
        if res is None:
            written, replies, res = write_planned_files(
                project, paths, ask=ask,
                prompt_for=lambda path: file_prompt(item.request(), current_code(project.dir), libs, plan, path,
                                                    (project.dir / path).exists(), error))
        # 3. Libraries, then the checks.
        req = project.dir / "requirements.txt"
        new_deps, dep_errors = deps.resolve(req.read_text() if req.exists() else None, st["published"])
        if res is None:
            if dep_errors:
                res = fail("requirements", "\n".join(dep_errors))
            elif item.kind == "dep_update" and new_deps.get(item.extra["lib"]) != item.extra["version"]:
                res = fail("upgrade", f"requirements.txt must pin {item.extra['lib']}=={item.extra['version']}"
                                      f" (it currently resolves to {new_deps.get(item.extra['lib'], 'nothing')}).")
            else:
                deps.install(project.meta / "libs", new_deps)
                res = run_checks(project, level)
        ctx_used = max(c["prompt_tokens"] + c["tokens"] for c in calls)
        seconds = sum(c["seconds"] for c in calls)
        truncated = [c["step"] for c in calls if c["truncated"]]
        entry = {"item": item.id, "kind": item.kind, "attempt": attempt, "tick": item.tick,
                 "when": time.strftime("%Y-%m-%d %H:%M:%S"), "model": cfg.model, "seed": seed,
                 "passed": res["passed"], "total": res["total"], "failed": res["failed"],
                 "skipped": res.get("skipped", []), "error": res.get("error"),
                 "plan_files": paths, "files_written": written, "files_skipped": [],
                 "tokens": sum(c["tokens"] for c in calls), "prompt_tokens": max(c["prompt_tokens"] for c in calls),
                 "ctx_used": ctx_used, "tok_s": calls[-1]["tok_s"], "seconds": round(seconds, 1),
                 "truncated": bool(truncated), "calls": calls}
        project.log_attempt(entry, "\n\n".join(replies))
        (project.meta / "attempts" / item.id / f"try{attempt}" / "plan.md").write_text(plan)
        warn = " [CONTEXT NEARLY FULL]" if ctx_used > 0.9 * cfg.num_ctx else ""
        warn += f" [OUTPUT CUT OFF: {', '.join(truncated)}]" if truncated else ""
        log(f"  try {attempt}: planned {len(paths)} files, wrote {len(written)}; {res['passed']}/{res['total']} checks"
            + (f" (failed: {', '.join(res['failed'])})" if res["failed"] else "")
            + f"  {len(calls)} calls, {seconds:.0f}s, largest ctx {ctx_used}/{cfg.num_ctx}{warn}")
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
        error, prev_plan = res.get("error") or ", ".join(res["failed"]), plan
    project.discard_changes()
    deps.install(project.meta / "libs", st["deps"])  # back to the last release's library versions
    log(f"  Failed after {max_repairs + 1} tries; rolled back to the last release. It stays at the front of the"
        f" queue. Every attempt is saved in {project.meta / 'attempts' / item.id}")
    return False


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
