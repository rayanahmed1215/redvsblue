"""Builder command line.

  python3 -m builder new myblog                 # create sites/myblog (roadmap: blog)
  python3 -m builder run myblog --ticks 3       # advance the clock 3 ticks, doing whatever arrives
  python3 -m builder run myblog                 # run to the end of the roadmap timeline ("build" works too)
  python3 -m builder run myblog --ollama qwen3.5:9b   # use an Ollama model instead of the MoE
  python3 -m builder status myblog              # clock, queue, releases, commits
  python3 -m builder serve myblog               # browse it at http://127.0.0.1:5000
"""
import argparse
import os
import subprocess
import sys

from . import roadmap
from .build import run
from .config import MAX_REPAIRS, PKG, VENV_PY, ModelConfig
from .llm import model_server
from .project import Project


def cmd_new(args):
    p = Project.create(args.name, args.roadmap)
    rm = p.roadmap()
    print(f"Created {p.dir} (roadmap '{rm.name}', {len(rm.stages)} features over {rm.last_tick} ticks):")
    for s in rm.stages:
        print(f"  {s.number}. {s.title}")
    print(f"\nNext: python3 -m builder run {args.name} --ticks 1")


def load(name) -> Project:
    p = Project(name)
    if not p.exists():
        sys.exit(f"No project '{name}'. Create it with: python3 -m builder new {name}")
    return p


def cmd_run(args):
    p = load(args.name)
    cfg = ModelConfig.ollama(args.ollama) if args.ollama else ModelConfig()
    print(f"Project {p.dir}  model {cfg.model} ({cfg.backend})  up to {args.max_repairs} repairs per item")
    with model_server(cfg):
        ok = run(p, cfg, ticks=args.ticks, max_repairs=args.max_repairs)
    cmd_status(args)
    sys.exit(0 if ok else 1)


def cmd_status(args):
    p = load(args.name)
    rm, st = p.roadmap(), p.state()
    print(f"\n{p.name}: tick {st['tick']}/{rm.last_tick}, features {st['features_done']}/{len(rm.stages)}"
          f" (roadmap '{rm.name}')")
    print("Dependencies: " + (", ".join(f"{k}=={v}" for k, v in st["deps"].items()) or "none"))
    if st["published"]:
        print("Published:    " + ", ".join(f"{k} {'/'.join(v)}" for k, v in sorted(st["published"].items())))
    queue = p.queue()
    print(f"\nQueue ({len(queue)}):" + ("" if queue else " empty"))
    for item in queue:
        tries = sum(1 for a in p.attempts() if a["item"] == item.id)
        print(f"  [{item.kind}] {item.title}" + (f"  (failed {tries} tries so far)" if tries else ""))
    rels = p.releases()
    print(f"\nReleases ({len(rels)}):")
    for r in rels:
        deps = " ".join(f"{k}=={v}" for k, v in r["deps"].items())
        print(f"  {r['version']:>4}  tick {r['tick']:>2}  {r['kind']:<10} {r['title']}"
              f"  ({r['tries']} {'try' if r['tries'] == 1 else 'tries'}){'  ' + deps if deps else ''}")


def cmd_serve(args):
    p = load(args.name)
    if not p.releases():
        sys.exit("Nothing released yet.")
    env = {**os.environ, "PYTHONPATH": str(p.meta / "libs")}  # the site's homemade library versions
    subprocess.run([str(VENV_PY), str(PKG / "serve_app.py"), str(p.dir), str(args.port)], env=env)


def main():
    ap = argparse.ArgumentParser(prog="python3 -m builder", description="Grow a website over time with a local LLM.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new", help="create a project")
    s.add_argument("name")
    s.add_argument("--roadmap", default="blog", choices=roadmap.available())
    s.set_defaults(fn=cmd_new)
    for cmd in ("run", "build"):
        s = sub.add_parser(cmd, help="advance the clock and process work items" + (" (alias of run)" if cmd == "build" else ""))
        s.add_argument("name")
        s.add_argument("--ticks", type=int, help="how many ticks to advance (default: to the end of the timeline)")
        s.add_argument("--max-repairs", type=int, default=MAX_REPAIRS)
        s.add_argument("--ollama", metavar="TAG", help="use this Ollama model instead of the llama.cpp MoE")
        s.set_defaults(fn=cmd_run)
    s = sub.add_parser("status", help="show the clock, queue and releases")
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
