"""Multi-stage Builder bake-off: build the blog in 5 stages, re-testing everything at each stage.

  python bakeoff/run_stages.py --models qwen3:8b --runs 2
  python bakeoff/run_stages.py --models moe --runs 2 --note "n-cpu-moe=36"   # needs llama-server on :8081

Each stage request contains the feature request plus the current code. If the app fails any
check (including checks from earlier stages), the model gets up to MAX_REPAIRS more tries. Each
repair is a fresh request (feature + latest code + error), so prompts don't grow with every retry.
A run stops at the first stage it can't pass.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backends import TEMPERATURE, TOP_K, TOP_P, llamacpp_chat, ollama_chat  # noqa: E402
from check import VENV_PY, write_files  # noqa: E402
from run import MODELS, SEEDS, SYSTEM, slug  # noqa: E402

HERE = Path(__file__).resolve().parent
STAGES = sorted((HERE / "stages").glob("stage*.md"))
RESULTS_JSON = HERE / "results_stages.json"
RESULTS_MD = HERE / "results_stages.md"
MAX_REPAIRS = 3
# Don't mention app.app_context() here: it's the Flask-SQLAlchemy idiom and pulled qwen3 toward that library.
STAGE_SYSTEM = SYSTEM + (" This is Flask 3.x, where before_first_request no longer exists: create the database "
                         "tables with a plain function that app.py calls once at import time, using Python's "
                         "built-in sqlite3 module.")
SAMPLING = f"temperature {TEMPERATURE}, top_p {TOP_P}, top_k {TOP_K}"
CODE_SUFFIXES = {".py", ".html", ".css", ".js", ".txt"}

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


def current_code(app_dir: Path) -> str:
    parts = []
    for p in sorted(app_dir.rglob("*")):
        if p.is_file() and p.suffix in CODE_SUFFIXES and p.name != "raw_output.txt" and "__pycache__" not in p.parts:
            rel = p.relative_to(app_dir)
            lang = {".py": "python", ".html": "html", ".css": "css", ".js": "javascript"}.get(p.suffix, "")
            parts.append(f"### File: {rel}\n```{lang}\n{p.read_text(errors='ignore')}\n```")
    return "\n\n".join(parts)


def build_prompt(stage_text, code_dir, error=None):
    if code_dir is None and error is None:
        return f"{stage_text}\n{FORMAT_FIRST}"
    msg = f"{stage_text}\n"
    if code_dir is not None:
        msg += f"\nHere is the app's current code:\n\n{current_code(code_dir)}\n"
    if error:
        msg += ("\nI ran your latest version of the app and some checks failed:\n\n"
                f"```\n{error.strip()}\n```\n\nFix the problems.\n")
    return f"{msg}\n{FORMAT_CHANGES}"


def grade_stage(app_dir: Path, stage: int, timeout=60) -> dict:
    for f in ("blog.db",):
        (app_dir / f).unlink(missing_ok=True)
    try:
        proc = subprocess.run([str(VENV_PY), str(HERE / "stage_smoke.py"), str(app_dir), str(stage)],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"passed": 0, "total": 1, "failed": ["timeout"], "failed_step": "timeout", "error": f"checks took over {timeout}s"}
    lines = [l for l in proc.stdout.strip().splitlines() if l.startswith("{")]
    if not lines:
        return {"passed": 0, "total": 1, "failed": ["crash"], "failed_step": "crash", "error": (proc.stderr or proc.stdout)[-1500:]}
    return json.loads(lines[-1])


def run_one(name, cfg, seed, num_ctx):
    label = cfg.get("label", name)
    base = HERE / "out_stages" / slug(label) / f"seed{seed}"
    row = {"model": label, "seed": seed, "when": time.strftime("%Y-%m-%d %H:%M"), "stages": [], "num_ctx": num_ctx, "sampling": SAMPLING}
    code_dir = None  # last passing version
    tokens = gen_s = seconds = 0.0
    print(f"  {label} seed={seed}")
    for i, stage_file in enumerate(STAGES, start=1):
        stage_text = stage_file.read_text()
        st = {"stage": i, "attempts": [], "passed": False}
        latest_dir, error = code_dir, None
        for attempt in range(1, MAX_REPAIRS + 2):
            messages = [{"role": "system", "content": STAGE_SYSTEM},
                        {"role": "user", "content": build_prompt(stage_text, latest_dir, error)}]
            # A distinct seed per attempt: with a fixed seed, an identical retry prompt gives an identical reply.
            gen_seed = seed * 100 + i * 10 + attempt
            try:
                if cfg["backend"] == "ollama":
                    gen = ollama_chat(name, messages, gen_seed, think=cfg.get("think"), num_ctx=num_ctx)
                else:
                    gen = llamacpp_chat(messages, gen_seed)
            except Exception as e:  # noqa: BLE001
                st["attempts"].append({"backend_error": str(e)})
                print(f"    stage {i} try {attempt}: backend error {e}")
                break
            tokens += gen["tokens"]
            seconds += gen["seconds"]
            if gen["tok_s"]:
                gen_s += gen["tokens"] / gen["tok_s"]
            out_dir = base / f"stage{i}" / f"try{attempt}"
            stats = write_files(gen["text"], out_dir, base_dir=latest_dir)
            res = grade_stage(out_dir, i) if stats["parsed"] else \
                {"passed": 0, "total": 1, "failed": ["no files found"], "failed_step": "no files found",
                 "error": "Your reply didn't contain any files in the `### File: <path>` format."}
            ctx_used = gen["prompt_tokens"] + gen["tokens"]
            st["attempts"].append({"passed": res["passed"], "total": res["total"], "failed": res["failed"],
                                   "error": res.get("error"), "prompt_tokens": gen["prompt_tokens"],
                                   "tokens": gen["tokens"], "ctx_used": ctx_used, "truncated": gen["truncated"],
                                   "seconds": round(gen["seconds"], 1), "files": stats["files"]})
            warn = " [CONTEXT NEARLY FULL]" if ctx_used > 0.95 * num_ctx else ""
            warn += " [OUTPUT CUT OFF]" if gen["truncated"] else ""
            print(f"    stage {i} try {attempt}: {res['passed']}/{res['total']} checks"
                  + (f" (failed: {', '.join(res['failed'])})" if res["failed"] else "")
                  + f"  {gen['seconds']:.0f}s, ctx {ctx_used}{warn}", flush=True)
            if not res["failed"]:
                st["passed"] = True
                code_dir = out_dir
                break
            latest_dir, error = out_dir, res.get("error") or ", ".join(res["failed"])
        row["stages"].append(st)
        if not st["passed"]:
            break
    row["stages_passed"] = sum(s["passed"] for s in row["stages"])
    row["generations"] = sum(len(s["attempts"]) for s in row["stages"])
    row["tokens"] = int(tokens)
    row["tok_s"] = tokens / gen_s if gen_s else None
    row["seconds"] = round(seconds, 1)
    row["max_ctx_used"] = max((a.get("ctx_used", 0) for s in row["stages"] for a in s["attempts"]), default=0)
    print(f"  => {row['stages_passed']}/{len(STAGES)} stages, {row['generations']} generations, "
          f"{row['seconds'] / 60:.1f} min, max context {row['max_ctx_used']}")
    return row


def render(rows):
    by_model = {}
    for r in rows:
        by_model.setdefault(r["model"], []).append(r)
    avg = lambda xs: sum(xs) / len(xs) if xs else 0  # noqa: E731
    n = len(STAGES)
    lines = [
        "# Multi-stage Builder bake-off", "",
        f"{n} stages (`bakeoff/stages/`), each graded on every feature so far. Up to {MAX_REPAIRS} repairs per stage;",
        "a run stops at the first stage it can't pass.",
        f"Sampling: {SAMPLING}. The system prompt includes a Flask 3 hint (no before_first_request; create tables with sqlite3 at import).", "",
        "| Model | Runs | Avg stages passed | Finished all | Tries per attempted stage (avg) | Avg minutes/run | Stages per hour | Avg tok/s | Max context used | Notes |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model, rs in by_model.items():
        passed = [r["stages_passed"] for r in rs]
        total_min = sum(r["seconds"] for r in rs) / 60
        tries = [len(s["attempts"]) for r in rs for s in r["stages"]]  # includes the stage it got stuck on
        notes = sorted({r.get("note") for r in rs if r.get("note")})
        lines.append(
            f"| {model} | {len(rs)} | {avg(passed):.1f}/{n} | {passed.count(n)}/{len(rs)} | {avg(tries):.1f} | "
            f"{total_min / len(rs):.1f} | {sum(passed) / (total_min / 60) if total_min else 0:.1f} | "
            f"{avg([r['tok_s'] for r in rs if r.get('tok_s')]):.1f} | {max(r['max_ctx_used'] for r in rs)} / {rs[0]['num_ctx']} | "
            f"{'; '.join(notes)} |")
    lines += ["", "## Stage by stage", ""]
    for r in rows:
        cells = []
        for s in r["stages"]:
            mark = "✅" if s["passed"] else "❌"
            cells.append(f"S{s['stage']} {mark} {len(s['attempts'])} tr{'y' if len(s['attempts']) == 1 else 'ies'}")
        lines.append(f"- **{r['model']}** seed {r['seed']}: " + " · ".join(cells))
        for s in r["stages"]:
            if not s["passed"] and s["attempts"]:
                last = s["attempts"][-1]
                lines.append(f"  - stuck on stage {s['stage']}: failed checks {last.get('failed')}")
    RESULTS_MD.write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, help="comma list, e.g. qwen3:8b or moe")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--ctx", type=int, default=16384, help="context window (llama-server must be started with the same -c)")
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    names = [n.strip() for n in args.models.split(",")]
    for n in names:
        if n not in MODELS:
            sys.exit(f"Unknown model {n}. Known: {list(MODELS)}")
    rows = json.loads(RESULTS_JSON.read_text()) if RESULTS_JSON.exists() else []
    for name in names:
        print(f"== {MODELS[name].get('label', name)}")
        for seed in SEEDS[: args.runs]:
            row = run_one(name, MODELS[name], seed, args.ctx)
            if args.note:
                row["note"] = args.note
            rows = [r for r in rows if not (r["model"] == row["model"] and r["seed"] == seed)] + [row]
            RESULTS_JSON.write_text(json.dumps(rows, indent=2))
            render(rows)
    print(f"\nResults: {RESULTS_MD}")


if __name__ == "__main__":
    main()
