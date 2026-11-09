"""Builder model bake-off: one first attempt, then one repair attempt if it failed.

  python bakeoff/run.py --models qwen2.5-coder:7b --runs 1
  python bakeoff/run.py --models ollama --runs 3      # all Ollama contenders
  python bakeoff/run.py --models moe --runs 3 --note "n-cpu-moe=34"   # needs llama-server on :8081

Results accumulate in bakeoff/results.json; bakeoff/results.md is regenerated each time.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backends import llamacpp_chat, ollama_chat  # noqa: E402
from check import grade, write_files  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS_JSON = HERE / "results.json"
RESULTS_MD = HERE / "results.md"
SEEDS = [11, 22, 33]

SYSTEM = "You are a web developer. You write complete, working code and reply in the exact format requested."

MODELS = {
    "qwen2.5-coder:7b": {"backend": "ollama"},
    "qwen3:8b": {"backend": "ollama", "think": False},
    "qwen3.5:9b": {"backend": "ollama", "think": False},
    "moe": {"backend": "llamacpp", "label": "qwen3-coder-30b-a3b (MoE)"},
}


def slug(name):
    return re.sub(r"[^a-zA-Z0-9.]+", "-", name).strip("-")


def repair_prompt(stats, result):
    if not stats["parsed"]:
        return (
            "I couldn't find any files in your reply. Reply again with every file, each as a "
            "`### File: <path>` line followed by a code block with the complete file."
        )
    return (
        f"I ran the app and it failed at the step \"{result['failed_step']}\". The error was:\n\n"
        f"```\n{(result.get('error') or 'no error output').strip()}\n```\n\n"
        "Fix the problem. Reply with the complete contents of every file you change, in the same "
        "`### File: <path>` format. Files you don't include stay as they are."
    )


def run_one(name, cfg, seed, prompt):
    label = cfg.get("label", name)
    base = HERE / "out" / slug(label) / f"seed{seed}"
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]

    def chat():
        if cfg["backend"] == "ollama":
            return ollama_chat(name, messages, seed, think=cfg.get("think"))
        return llamacpp_chat(messages, seed)

    print(f"  {label} seed={seed}: ", end="", flush=True)
    row = {"model": label, "seed": seed, "when": time.strftime("%Y-%m-%d %H:%M"), "out_dir": str(base.relative_to(HERE))}
    tokens = gen_s = seconds = 0.0
    prev_dir = None
    for attempt in (1, 2):
        try:
            gen = chat()
        except Exception as e:  # noqa: BLE001
            print(f"backend error: {e}")
            row["backend_error"] = str(e)
            return row
        tokens += gen["tokens"]
        seconds += gen["seconds"]
        if gen["tok_s"]:
            gen_s += gen["tokens"] / gen["tok_s"]
        out_dir = base / f"try{attempt}"
        stats = write_files(gen["text"], out_dir, base_dir=prev_dir)
        result = grade(out_dir) if stats["parsed"] else {"passed": 0, "failed_step": "no files found", "error": None}
        row[f"try{attempt}"] = {**result, "files": stats["files"], "loc": stats["loc"], "truncated": gen["truncated"]}
        print(f"try{attempt} {result['passed']}/5" + (f" ({result['failed_step']})" if result["passed"] < 5 else "") + "  ", end="", flush=True)
        if result["passed"] == 5:
            break
        messages += [{"role": "assistant", "content": gen["text"]}, {"role": "user", "content": repair_prompt(stats, result)}]
        prev_dir = out_dir
    row["final"] = row.get("try2", row["try1"])["passed"]
    row["tokens"] = int(tokens)
    row["tok_s"] = tokens / gen_s if gen_s else None
    row["seconds"] = round(seconds, 1)
    print(f"| {row['tok_s'] or 0:.1f} tok/s, {row['seconds']}s")
    return row


def load_rows():
    rows = json.loads(RESULTS_JSON.read_text()) if RESULTS_JSON.exists() else []
    return [r for r in rows if "try1" in r or "backend_error" in r]  # drop rows from the old JSON-format harness


def render(rows):
    by_model = {}
    for r in rows:
        by_model.setdefault(r["model"], []).append(r)
    avg = lambda xs: sum(xs) / len(xs) if xs else 0  # noqa: E731
    lines = [
        "# Builder bake-off results", "",
        "Note: these runs used temperature 0.2, so outputs from different seeds were often near-identical (up to 97% similar).",
        "Task: `bakeoff/task.md` (Flask + SQLite blog). Score = smoke-test steps passed out of 5.",
        "Each run gets one first attempt and, if it fails, one repair attempt with the error message.", "",
        "| Model | Runs | 1st try avg (/5) | 1st try working | After repair avg (/5) | After repair working | Avg tok/s | Avg sec/run | Avg LOC | Notes |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model, rs in by_model.items():
        ok = [r for r in rs if "try1" in r]
        first = [r["try1"]["passed"] for r in ok]
        final = [r["final"] for r in ok]
        loc = [r.get("try2", r["try1"])["loc"] for r in ok]
        tps = [r["tok_s"] for r in ok if r.get("tok_s")]
        notes = sorted({r.get("note") for r in rs if r.get("note")} | ({"backend errors"} if len(ok) < len(rs) else set()))
        lines.append(
            f"| {model} | {len(rs)} | {avg(first):.1f} | {first.count(5)}/{len(ok)} | {avg(final):.1f} | {final.count(5)}/{len(ok)} | "
            f"{avg(tps):.1f} | {avg([r['seconds'] for r in ok]):.0f} | {avg(loc):.0f} | {'; '.join(notes)} |"
        )
    lines += ["", "## What went wrong", ""]
    for r in rows:
        if "backend_error" in r:
            lines.append(f"- **{r['model']}** seed {r['seed']}: backend error: `{r['backend_error'][:160]}`")
            continue
        for t in ("try1", "try2"):
            res = r.get(t)
            if res and res["passed"] < 5:
                err = (res.get("error") or "").strip().splitlines()
                lines.append(f"- **{r['model']}** seed {r['seed']} {t}: {res['failed_step']}" + (f": `{err[-1][:160]}`" if err else ""))
    RESULTS_MD.write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="ollama", help="comma list of model names, 'ollama', 'moe' or 'all'")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--note", default="", help="free text stored with these rows (e.g. llama.cpp settings)")
    args = ap.parse_args()

    if args.models == "all":
        names = list(MODELS)
    elif args.models == "ollama":
        names = [n for n, c in MODELS.items() if c["backend"] == "ollama"]
    else:
        names = [n.strip() for n in args.models.split(",")]
    unknown = [n for n in names if n not in MODELS]
    if unknown:
        sys.exit(f"Unknown model(s): {unknown}. Known: {list(MODELS)}")

    prompt = (HERE / "task.md").read_text()
    rows = load_rows()
    for name in names:
        cfg = MODELS[name]
        print(f"== {cfg.get('label', name)}")
        for seed in SEEDS[: args.runs]:
            row = run_one(name, cfg, seed, prompt)
            if args.note:
                row["note"] = args.note
            rows = [r for r in rows if not (r["model"] == row["model"] and r["seed"] == seed)] + [row]
            RESULTS_JSON.write_text(json.dumps(rows, indent=2))
            render(rows)
    print(f"\nResults: {RESULTS_MD}")


if __name__ == "__main__":
    main()
