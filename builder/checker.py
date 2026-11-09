"""Runs a roadmap's checks against a generated app. Runs INSIDE a subprocess using builder/.venv.

Usage: python checker.py <app_dir> <checks.py> <stage>
Prints one JSON line: {"stage", "passed", "total", "failed", "skipped", "failed_step", "error"}.

checks.py defines `define(c, app)`, which registers checks with `@c.check(name, min_stage, needs=(...))`.
Every check up to <stage> runs, so earlier features are re-tested (regressions count). A check whose
`needs` keys are missing from `c.state` (because an earlier check failed) is skipped, not crashed.
"""
import importlib.util
import json
import os
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
    spec = importlib.util.spec_from_file_location("roadmap_checks", checks_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    c = Checker(stage, app_dir)
    mod.define(c, app)
    print(json.dumps(c.report()))


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), int(sys.argv[3]))
