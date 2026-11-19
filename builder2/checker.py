"""Runs a roadmap's checks against a generated app. Runs INSIDE a subprocess using builder/.venv.

Usage: python checker.py <app_dir> <checks.py> <stage>
Prints one JSON line: {"stage", "passed", "total", "failed", "skipped", "failed_step", "error"}.

checks.py defines `define(c, app)`, which registers checks with `@c.check(name, min_stage, needs=(...))`.
Every check up to <stage> runs, so earlier features are re-tested (regressions count). A check whose
`needs` keys are missing from `c.state` (because an earlier check failed) is skipped, not crashed.

builder2 addition: before the roadmap checks, a "files agree" check looks for names one file uses that
another file never defines (templates, Jinja filters, route functions) and reports them all at once.
"""
import importlib.util
import json
import os
import re
import runpy
import sys
import traceback


def app_traceback(app_dir):
    """The current exception, showing only stack frames from the app's own files (app.py and templates)."""
    etype, evalue, tb = sys.exc_info()
    frames = [f for f in traceback.extract_tb(tb) if os.path.abspath(f.filename).startswith(app_dir)]
    lines = ["Traceback (only frames from your app's files):\n"]
    lines += traceback.format_list(frames) or ["  (no frames in your files; error raised inside a library)\n"]
    lines += traceback.format_exception_only(etype, evalue)
    return "".join(lines).replace(app_dir + os.sep, "")[-1500:]


def load_app(app_dir):
    """Run app.py as if started with `python app.py`, but with app.run() disabled."""
    import flask

    os.chdir(app_dir)
    sys.path.insert(0, app_dir)
    flask.Flask.run = lambda *a, **k: None
    return runpy.run_path(os.path.join(app_dir, "app.py"), run_name="__main__")["app"]


SKIP_DIRS = {".git", ".builder", ".venv", "__pycache__"}
TEMPLATE_REF = re.compile(r"""{%-?\s*(?:extends|include|import|from)\s+["']([^"']+)["']""")
RENDER_REF = re.compile(r"""render_template\(\s*["']([^"']+)["']""")
URL_FOR_REF = re.compile(r"""url_for\(\s*["']([\w.]+)["']""")


def connection_problems(app, app_dir, limit=15):
    """Things one file uses that no file defines. Returns a list of plain-language problems."""
    import jinja2

    env, problems, sources = app.jinja_env, [], {}
    templates = set(env.list_templates())
    for name in sorted(templates):
        try:
            sources[f"templates/{name}"] = env.loader.get_source(env, name)[0]
            env.get_template(name)  # compiling catches unknown filters/tests and syntax errors
        except jinja2.TemplateSyntaxError as e:
            hint = " Define it in app.py with @app.template_filter, or don't use it." if "filter" in str(e.message) else ""
            problems.append(f"templates/{name} line {e.lineno}: {str(e.message).rstrip('.')}.{hint}")
        except Exception as e:  # noqa: BLE001
            problems.append(f"templates/{name} can't be read: {e}")
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, errors="ignore") as fh:
                    sources[os.path.relpath(path, app_dir)] = fh.read()
    routes = sorted(app.view_functions)
    for path, src in sorted(sources.items()):
        refs = RENDER_REF.findall(src) if path.endswith(".py") else TEMPLATE_REF.findall(src)
        for t in dict.fromkeys(refs):
            if t not in templates:
                problems.append(f"{path} uses the template '{t}', but templates/{t} doesn't exist.")
        for endpoint in dict.fromkeys(URL_FOR_REF.findall(src)):
            if not endpoint.startswith(".") and endpoint not in app.view_functions:
                problems.append(f"{path} calls url_for('{endpoint}'), but no route function is named "
                                f"'{endpoint}'. The route functions are: {', '.join(routes)}.")
    if len(problems) > limit:
        problems = problems[:limit] + [f"(and {len(problems) - limit} more)"]
    return problems


class Checker:
    def __init__(self, stage, app_dir):
        self.stage, self.app_dir = stage, app_dir
        self.state = {}  # values shared between checks, e.g. the id of a created post
        self.results = []  # (name, ok, error, skipped)

    def check(self, name, min_stage, needs=()):
        def wrap(fn):
            if self.stage < min_stage:
                return
            if any(k not in self.state for k in needs):
                self.results.append((name, False, None, True))
                return
            try:
                fn()
                self.results.append((name, True, None, False))
            except AssertionError as e:
                self.results.append((name, False, f"Check '{name}' failed: {e}", False))
            except BaseException:  # noqa: BLE001
                self.results.append((name, False, f"Check '{name}' crashed:\n{app_traceback(self.app_dir)}", False))
        return wrap

    def report(self):
        failed = [(n, e) for n, ok, e, _ in self.results if not ok]
        skipped = [n for n, _, _, sk in self.results if sk]
        real = [e for n, e in failed if n not in skipped]
        error = "\n\n".join(real[:3])[-2500:] if real else None
        if error and skipped:
            error += f"\n\n({len(skipped)} later checks were skipped because an earlier check failed.)"
        return {"stage": self.stage, "passed": len(self.results) - len(failed), "total": len(self.results),
                "failed": [n for n, _ in failed], "skipped": skipped,
                "failed_step": failed[0][0] if failed else None, "error": error}


def main(app_dir, checks_path, stage):
    try:
        app = load_app(app_dir)
        app.testing = True  # raise real exceptions instead of bare 500s
    except BaseException:  # noqa: BLE001
        print(json.dumps({"stage": stage, "passed": 0, "total": 1, "failed": ["app starts"], "skipped": [],
                          "failed_step": "app starts", "error": app_traceback(app_dir)}))
        return
    problems = connection_problems(app, app_dir)
    if problems:
        print(json.dumps({"stage": stage, "passed": 0, "total": 1, "failed": ["files agree"], "skipped": [],
                          "failed_step": "files agree",
                          "error": "Your files don't agree with each other:\n- " + "\n- ".join(problems)}))
        return
    spec = importlib.util.spec_from_file_location("roadmap_checks", checks_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    c = Checker(stage, app_dir)
    mod.define(c, app)
    print(json.dumps(c.report()))


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), int(sys.argv[3]))
