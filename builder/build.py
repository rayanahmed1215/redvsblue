"""The build loop: for each remaining stage, ask for the feature, run the checks, repair, commit."""
import json
import random
import subprocess
import time

from . import llm
from .config import MAX_REPAIRS, PKG, SYSTEM_PROMPT, VENV_PY, ModelConfig
from .files import apply_files, current_code, lines_of_code
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


def build_prompt(stage_text: str, code: str | None, error: str | None) -> str:
    if code is None and error is None:
        return f"{stage_text}\n{FORMAT_FIRST}"
    msg = f"{stage_text}\n"
    if code:
        msg += f"\nHere is the app's current code:\n\n{code}\n"
    if error:
        msg += ("\nI ran your latest version of the app and some checks failed:\n\n"
                f"```\n{error.strip()}\n```\n\nFix the problems.\n")
    return f"{msg}\n{FORMAT_CHANGES}"


def clear_dbs(project: Project):
    for db in project.dir.glob("*.db"):
        db.unlink(missing_ok=True)


def run_checks(project: Project, stage: int, timeout=90) -> dict:
    clear_dbs(project)  # every check run starts from an empty database
    cmd = [str(VENV_PY), str(PKG / "checker.py"), str(project.dir), str(project.roadmap().checks), str(stage)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"passed": 0, "total": 1, "failed": ["timeout"], "skipped": [], "failed_step": "timeout",
                "error": f"The checks took longer than {timeout}s (the app may hang)."}
    finally:
        clear_dbs(project)
    lines = [l for l in proc.stdout.strip().splitlines() if l.startswith("{")]
    if not lines:
        return {"passed": 0, "total": 1, "failed": ["crash"], "skipped": [], "failed_step": "crash",
                "error": (proc.stderr or proc.stdout)[-1500:]}
    return json.loads(lines[-1])


def build(project: Project, cfg: ModelConfig, until: int | None = None, max_repairs: int = MAX_REPAIRS,
          log=print, chat=llm.chat) -> bool:
    """Build stages after the last completed one, up to `until`. Returns True if every requested stage passed."""
    rm = project.roadmap()
    state = project.state()
    last = min(until or len(rm.stages), len(rm.stages))
    if state["stage_done"] >= last:
        log(f"Nothing to do: stage {state['stage_done']}/{len(rm.stages)} already done.")
        return True

    for n in range(state["stage_done"] + 1, last + 1):
        stage = rm.stage(n)
        log(f"\n== Stage {n}/{len(rm.stages)}: {stage.title}")
        error = None
        for attempt in range(1, max_repairs + 2):
            has_code = n > 1 or attempt > 1
            prompt = build_prompt(stage.text, current_code(project.dir) if has_code else None, error)
            seed = random.randrange(1, 2**31)
            messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
            gen = chat(cfg, messages, seed)
            applied = apply_files(gen["text"], project.dir)
            if applied["written"]:
                res = run_checks(project, n)
            else:
                res = {"passed": 0, "total": 1, "failed": ["no files found"], "skipped": [],
                       "failed_step": "no files found",
                       "error": "Your reply didn't contain any files in the `### File: <path>` format."}
            ctx_used = gen["prompt_tokens"] + gen["tokens"]
            entry = {"stage": n, "attempt": attempt, "when": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "model": cfg.model, "seed": seed, "passed": res["passed"], "total": res["total"],
                     "failed": res["failed"], "skipped": res.get("skipped", []), "error": res.get("error"),
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
                sha = project.commit_stage(stage, cfg.model, attempt)
                state["stage_done"] = n
                project.save_state(state)
                log(f"  committed {sha}: Stage {n}: {stage.title} ({lines_of_code(project.dir)} lines of code)")
                break
            error = res.get("error") or ", ".join(res["failed"])
        else:
            project.discard_changes()
            log(f"  Stage {n} failed after {max_repairs + 1} tries. Rolled back to the last passing commit;"
                f" every attempt is saved in {project.meta / 'attempts' / f'stage{n}'}")
            return False
    return True
