"""The build loop, version 3: builder2's plan-first loop, but existing files are changed with edits.

process(): one work item -> plan call -> one call per planned file (edits for existing files, the whole file
           for new ones) -> cumulative checks -> retry with a new plan -> release or roll back.
run():     same clock and queue as builder/build.py.

Also new: try folders keep counting across runs (try7, try8, ...), so a restart never overwrites old tries.
"""
import json
import random
import re
import shutil
import time

from builder import deps, llm
from builder.build import advance_tick, fail
from builder.config import MAX_REPAIRS, SYSTEM_PROMPT, ModelConfig
from builder.files import current_code, lines_of_code
from builder.items import WorkItem
from builder.project import Project
from builder2.build import run_checks
from builder2.files import parse_one, write_file
from builder2.plan import check_plan, file_prompt, parse_plan, plan_prompt

from .edits import apply_edits, parse_edits
from .prompts import edit_prompt


def write_planned_files(project: Project, paths, prompt_for, ask) -> tuple[list[str], list[str], dict, dict | None]:
    """Ask for each planned file in its own call: edits for a file that exists, the whole file for a new one.

    Stops at the first file that can't be written. Returns (files written, raw replies, how each file was
    written, failure or None).
    """
    written, replies, how = [], [], {}
    for path in paths:
        target = project.dir / path
        existing = target.read_text(errors="ignore") if target.is_file() else None
        gen = ask(path, prompt_for(path, existing is not None))
        replies.append(f"<!-- reply for {path} -->\n{gen['text']}")
        if existing is None:
            content = parse_one(gen["text"], path)
            if content is None:
                why = ("was cut off before the file ended, so it is too long for one reply. Make the file shorter"
                       if gen["truncated"] else "didn't contain the file as one code block")
                return written, replies, how, fail("file not written", f"Your reply for `{path}` {why}.")
            how[path] = "new"
        else:
            edits, broken = parse_edits(gen["text"])
            if not edits and not broken and not gen["truncated"]:
                content = parse_one(gen["text"], path)  # allowed: rewrote a (small) file whole anyway
                if content is None:
                    return written, replies, how, fail(
                        "edits", f"Your reply for `{path}` had no `<<<<<<< FIND` ... `>>>>>>> REPLACE` edit blocks.")
                how[path] = "whole"
            else:
                if broken or gen["truncated"]:
                    return written, replies, how, fail(
                        "edits", f"Your reply for `{path}` was cut off: " + (broken or "the last edit is incomplete.")
                        + " Use fewer, smaller edits.")
                content, errors = apply_edits(existing, edits, path)
                if errors:
                    return written, replies, how, fail(
                        "edits", f"`{path}` was not changed, because some edits didn't apply:\n\n" + "\n\n".join(errors))
                how[path] = f"{len(edits)} edits" if content != existing else "unchanged"
        write_file(project.dir, path, content)
        written.append(path)
    if written and all(h == "unchanged" for h in how.values()):
        return written, replies, how, fail(
            "edits", "Your edits changed nothing: every replacement was the same as its FIND text, so the code is "
                     "exactly as it was. Find what actually causes the error and change that.")
    return written, replies, how, None


def next_try_folder(project: Project, item_id: str) -> int:
    """The highest existing tryN folder for this item, so this run's tries are numbered after it."""
    d = project.meta / "attempts" / item_id
    nums = [int(m[1]) for p in d.iterdir() if (m := re.fullmatch(r"try(\d+)", p.name))] if d.exists() else []
    return max(nums, default=0)


def save_attempt(project: Project, entry: dict, reply: str, plan: str, folder: int):
    d = project.meta / "attempts" / entry["item"] / f"try{folder}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / "reply.md").write_text(reply)
    (d / "plan.md").write_text(plan)
    (d / "result.json").write_text(json.dumps(entry, indent=2))
    with open(project.meta / "log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def process(project: Project, item: WorkItem, cfg: ModelConfig, max_repairs: int = MAX_REPAIRS,
            log=print, chat=llm.chat) -> bool:
    """Do one work item. On success it's released and removed from the queue; on failure it stays queued."""
    st = project.state()
    level = item.feature if item.kind == "feature" else st["features_done"]
    log(f"\n== [{item.kind}] {item.title}  (tick {item.tick}, checks for features 1-{level})")
    libs = deps.docs_for_prompt(st["published"], st["deps"])
    error = prev_plan = None
    folder0 = next_try_folder(project, item.id)
    for attempt in range(1, max_repairs + 2):
        seed = random.randrange(1, 2**31)
        calls = []

        def ask(step, prompt):
            gen = chat(cfg, [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}], seed)
            calls.append({"step": step, "tokens": gen["tokens"], "prompt_tokens": gen["prompt_tokens"],
                          "tok_s": gen["tok_s"], "seconds": round(gen["seconds"], 1), "truncated": gen["truncated"]})
            return gen

        def prompt_for(path, exists):
            code = current_code(project.dir)
            if exists:
                return edit_prompt(item.request(), code, libs, plan, path, error)
            return file_prompt(item.request(), code, libs, plan, path, False, error)

        # 1. The plan: which files change and how they connect.
        plan = ask("plan", plan_prompt(item.request(), current_code(project.dir), libs, prev_plan, error))["text"]
        paths, plan_error = check_plan(parse_plan(plan), project.dir, item)
        # 2. One call per planned file: edits for existing files, whole files for new ones.
        written, replies, how, res = [], [], {}, fail("plan", plan_error) if plan_error else None
        if res is None:
            written, replies, how, res = write_planned_files(project, paths, prompt_for, ask)
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
        entry = {"item": item.id, "kind": item.kind, "attempt": attempt, "folder": f"try{folder0 + attempt}",
                 "tick": item.tick, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "model": cfg.model, "seed": seed,
                 "builder": "builder3", "passed": res["passed"], "total": res["total"], "failed": res["failed"],
                 "skipped": res.get("skipped", []), "error": res.get("error"),
                 "plan_files": paths, "files_written": written, "written_as": how, "files_skipped": [],
                 "tokens": sum(c["tokens"] for c in calls), "prompt_tokens": max(c["prompt_tokens"] for c in calls),
                 "ctx_used": ctx_used, "tok_s": calls[-1]["tok_s"], "seconds": round(seconds, 1),
                 "truncated": bool(truncated), "calls": calls}
        save_attempt(project, entry, "\n\n".join(replies), plan, folder0 + attempt)
        warn = " [CONTEXT NEARLY FULL]" if ctx_used > 0.9 * cfg.num_ctx else ""
        warn += f" [OUTPUT CUT OFF: {', '.join(truncated)}]" if truncated else ""
        shown = ", ".join(f"{p} ({h})" for p, h in how.items())
        log(f"  try {attempt}: planned {len(paths)} files, wrote {len(written)}"
            + (f" [{shown}]" if shown else "") + f"; {res['passed']}/{res['total']} checks"
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
