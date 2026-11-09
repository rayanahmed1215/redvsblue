"""Builder command line.

  python3 -m builder new myblog                 # create sites/myblog (roadmap: blog)
  python3 -m builder build myblog               # build the remaining stages (starts llama-server if needed)
  python3 -m builder build myblog --until 2     # stop after stage 2; run again later to continue
  python3 -m builder build myblog --ollama qwen3.5:9b   # use an Ollama model instead of the MoE
  python3 -m builder status myblog              # stages done, commits, attempts
  python3 -m builder serve myblog               # browse it at http://127.0.0.1:5000
"""
import argparse
import subprocess
import sys

from . import roadmap
from .build import build
from .config import MAX_REPAIRS, PKG, VENV_PY, ModelConfig
from .llm import model_server
from .project import Project


def cmd_new(args):
    p = Project.create(args.name, args.roadmap)
    rm = p.roadmap()
    print(f"Created {p.dir} (roadmap '{rm.name}', {len(rm.stages)} stages):")
    for s in rm.stages:
        print(f"  {s.number}. {s.title}")
    print(f"\nNext: python3 -m builder build {args.name}")


def load(name) -> Project:
    p = Project(name)
    if not p.exists():
        sys.exit(f"No project '{name}'. Create it with: python3 -m builder new {name}")
    return p


def cmd_build(args):
    p = load(args.name)
    cfg = ModelConfig.ollama(args.ollama) if args.ollama else ModelConfig()
    print(f"Project {p.dir}  model {cfg.model} ({cfg.backend})  up to {args.max_repairs} repairs per stage")
    with model_server(cfg):
        ok = build(p, cfg, until=args.until, max_repairs=args.max_repairs)
    cmd_status(args)
    sys.exit(0 if ok else 1)


def cmd_status(args):
    p = load(args.name)
    rm, st = p.roadmap(), p.state()
    print(f"\n{p.name}: {st['stage_done']}/{len(rm.stages)} stages done (roadmap '{rm.name}')")
    for s in rm.stages:
        tries = [a for a in p.attempts() if a["stage"] == s.number]
        mark = "done" if s.number <= st["stage_done"] else ("FAILED" if tries else "todo")
        extra = f"  ({len(tries)} {'try' if len(tries) == 1 else 'tries'})" if tries else ""
        print(f"  {s.number}. [{mark:>6}] {s.title}{extra}")
    print("\nCommits:\n" + "\n".join("  " + l for l in p.history().strip().splitlines()))


def cmd_serve(args):
    p = load(args.name)
    if p.state()["stage_done"] == 0:
        sys.exit("Nothing built yet.")
    subprocess.run([str(VENV_PY), str(PKG / "serve_app.py"), str(p.dir), str(args.port)])


def main():
    ap = argparse.ArgumentParser(prog="python3 -m builder", description="Build a website stage by stage with a local LLM.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new", help="create a project")
    s.add_argument("name")
    s.add_argument("--roadmap", default="blog", choices=roadmap.available())
    s.set_defaults(fn=cmd_new)
    s = sub.add_parser("build", help="build the next stages")
    s.add_argument("name")
    s.add_argument("--until", type=int, help="stop after this stage")
    s.add_argument("--max-repairs", type=int, default=MAX_REPAIRS)
    s.add_argument("--ollama", metavar="TAG", help="use this Ollama model instead of the llama.cpp MoE")
    s.set_defaults(fn=cmd_build)
    s = sub.add_parser("status", help="show progress and commits")
    s.add_argument("name")
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("serve", help="run the site on 127.0.0.1")
    s.add_argument("name")
    s.add_argument("--port", type=int, default=5000)
    s.set_defaults(fn=cmd_serve)
    args = ap.parse_args()
    try:
        args.fn(args)
    except (ValueError, RuntimeError) as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
