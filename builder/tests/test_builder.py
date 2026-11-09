"""End-to-end tests of the Builder with a fake model (no LLM needed).

Run: python3 -m unittest discover -s builder/tests -t .
"""
import re
import tempfile
import unittest
from pathlib import Path

from builder.build import build_prompt, run, run_checks
from builder import deps
from builder.config import ModelConfig
from builder.files import apply_files, parse_files
from builder.items import WorkItem
from builder.project import Project
from builder.roadmap import load as load_roadmap
from builder.tests.fixtures import FULL_APP, STAGE1_APP

BROKEN_APP = "from flask import Flask\napp = Flask(__name__)\n"  # home page 404s
ROADMAP = load_roadmap("blog")
REFERENCE = (Path(__file__).parent / "reference_app.py").read_text()  # all 10 features


def reply(app_src, requirements=True, mdlite="1.0.0"):
    text = f"### File: app.py\n```python\n{app_src}\n```\n"
    if requirements is True:
        requirements = f"flask\nmdlite=={mdlite}\n"
    if requirements:
        text += f"\n### File: requirements.txt\n```\n{requirements}```\n"
    return text


class FakeModel:
    """Scripted replies. `script(item_key, attempt, prompt)` returns the reply text.

    item_key is the feature number for feature requests, or "dep"/"fix" for other items.
    """

    def __init__(self, script):
        self.script, self.calls = script, []

    def __call__(self, cfg, messages, seed):
        prompt = messages[-1]["content"]
        key = self.key_of(prompt)
        attempt = 1 + sum(1 for k, _ in self.calls if k == key)
        self.calls.append((key, prompt))
        return {"text": self.script(key, attempt, prompt), "tokens": 100, "prompt_tokens": 100,
                "tok_s": 50.0, "seconds": 0.1, "truncated": False}

    @staticmethod
    def key_of(prompt):
        if prompt.startswith("Feature request:"):
            first_line = prompt.split("\n\n", 1)[1].splitlines()[0]
            return next(s.number for s in ROADMAP.stages if s.text.startswith(first_line))
        return "dep" if prompt.startswith("Dependency update:") else "fix"


def full_script(key, attempt, prompt):
    """Correct replies for all 10 features: the reference app, pinning the library versions the prompt shows
    (the pinned/newest docs), with an upgrade request's version taking priority."""
    pins = dict(re.findall(r"^# (mdlite|uploadkit|pager) ([0-9.]+)$", prompt, re.MULTILINE))
    m = re.search(r"Upgrade the app to (\w+)==([0-9.]+)", prompt)
    if m:
        pins[m.group(1)] = m.group(2)
    if key == 1:
        return reply(STAGE1_APP, requirements=False)
    return reply(REFERENCE, requirements="".join(f"{k}=={v}\n" for k, v in pins.items()))


def good_script(key, attempt, prompt):
    """Correct replies: the stage-1 app, then the full app; upgrades pin whatever version was requested."""
    if key == 1:
        return reply(STAGE1_APP, requirements=False)
    if key == "dep":
        return reply(FULL_APP, mdlite=re.search(r"Upgrade the app to mdlite==([0-9.]+)", prompt).group(1))
    return reply(FULL_APP)


class RunTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.p = Project.create("site", "blog", base=self.base)
        self.cfg = ModelConfig()
        self.out = []

    def run_ticks(self, model, ticks=None, **kw):
        return run(self.p, self.cfg, ticks=ticks, log=self.out.append, chat=model, **kw)

    def commits(self):
        return self.p.git("log", "--format=%s").strip().splitlines()

    def test_full_timeline_with_library_upgrade(self):
        def script(key, attempt, prompt):
            return reply(FULL_APP, mdlite="1.1.0") if key == "dep" else good_script(key, attempt, prompt)
        self.assertTrue(self.run_ticks(FakeModel(script), ticks=6))
        st = self.p.state()
        self.assertEqual((st["tick"], st["features_done"], st["queue"]), (6, 5, []))
        self.assertEqual(st["deps"], {"mdlite": "1.1.0"})
        self.assertEqual(st["published"]["mdlite"], ["1.0.0", "1.1.0"])
        rels = self.p.releases()
        self.assertEqual([r["version"] for r in rels], ["v1", "v2", "v3", "v4", "v5", "v6"])
        self.assertEqual((rels[4]["deps"], rels[5]["kind"], rels[5]["deps"]),
                         ({"mdlite": "1.0.0"}, "dep_update", {"mdlite": "1.1.0"}))
        self.assertEqual(self.commits()[0], "dep_update: Upgrade mdlite to 1.1.0")
        self.assertIn('__version__ = "1.1.0"', (self.p.meta / "libs" / "mdlite.py").read_text())

    def test_unpublished_or_unknown_packages_are_rejected(self):
        def script(key, attempt, prompt):
            if attempt == 1:
                return reply(STAGE1_APP, requirements="flask\nrequests\nmdlite==9.9.9\n")
            return reply(STAGE1_APP, requirements="flask\n")  # the repair fixes requirements.txt
        model = FakeModel(script)
        self.assertTrue(self.run_ticks(model, ticks=1))
        err = self.p.attempts()[0]["error"]
        self.assertIn("'requests' isn't available", err)
        self.assertIn("mdlite==9.9.9 doesn't exist", err)
        self.assertIn("some checks failed", model.calls[1][1])

    def test_breaking_upgrade_needs_a_repair(self):
        self.assertTrue(self.run_ticks(FakeModel(good_script), ticks=5))
        st = self.p.state()
        st["published"]["mdlite"] += ["1.1.0", "1.2.0", "2.0.0"]
        self.p.save_state(st)
        self.p.enqueue(deps.dep_update_item("mdlite", "2.0.0", "1.0.0", tick=5))

        def script(key, attempt, prompt):
            if attempt == 1:  # pins 2.0.0 but still calls render()
                return reply(FULL_APP, mdlite="2.0.0")
            return reply(FULL_APP.replace("mdlite.render(", "mdlite.to_html("), mdlite="2.0.0")
        model = FakeModel(script)
        self.assertTrue(self.run_ticks(model, ticks=0))
        self.assertIn("`render()` has been renamed to `to_html()`", model.calls[0][1])
        self.assertIn("has no attribute 'render'", self.p.attempts()[-2]["error"])
        self.assertEqual(self.p.state()["deps"], {"mdlite": "2.0.0"})

    def test_upgrade_must_actually_change_the_pin(self):
        self.assertTrue(self.run_ticks(FakeModel(good_script), ticks=5))
        st = self.p.state()
        st["published"]["mdlite"].append("1.1.0")
        self.p.save_state(st)
        self.p.enqueue(deps.dep_update_item("mdlite", "1.1.0", "1.0.0", tick=5))
        stays_on_old = FakeModel(lambda key, attempt, prompt: reply(FULL_APP, mdlite="1.0.0"))
        self.assertFalse(self.run_ticks(stays_on_old, ticks=0, max_repairs=0))
        self.assertIn("must pin mdlite==1.1.0", self.p.attempts()[-1]["error"])
        self.assertIn('__version__ = "1.0.0"', (self.p.meta / "libs" / "mdlite.py").read_text(),
                      "libraries weren't restored after the failed upgrade")

    def test_prompt_includes_library_docs(self):
        model = FakeModel(good_script)
        self.assertTrue(self.run_ticks(model, ticks=1))
        self.assertIn("Available libraries", model.calls[0][1])
        for lib in ("# mdlite 1.0.0", "# uploadkit 1.0.0", "# pager 1.0.0"):
            self.assertIn(lib, model.calls[0][1])

    def test_ticks_limit_and_resume(self):
        self.assertTrue(self.run_ticks(FakeModel(good_script), ticks=2))
        self.assertEqual(self.p.state()["tick"], 2)
        model = FakeModel(good_script)
        self.assertTrue(self.run_ticks(model, ticks=4))
        self.assertEqual([k for k, _ in model.calls], [3, 4, 5, "dep"])  # tick 6 ships mdlite 1.1.0

    def test_whole_roadmap_timeline(self):
        model = FakeModel(full_script)
        self.assertTrue(self.run_ticks(model))
        st = self.p.state()
        self.assertEqual((st["tick"], st["features_done"], st["queue"]), (14, 10, []))
        # features, plus an upgrade whenever a library the site uses ships a new version
        self.assertEqual([k for k, _ in model.calls], [1, 2, 3, 4, 5, "dep", 6, 7, 8, "dep", "dep", 9, "dep", 10, "dep"])
        self.assertEqual(st["deps"], {"mdlite": "2.0.0", "uploadkit": "1.0.1", "pager": "1.0.1"})
        rels = self.p.releases()
        self.assertEqual(len(rels), 15)
        by_title = {r["title"]: r for r in rels}
        self.assertEqual(by_title["Upgrade mdlite to 1.1.0"]["deps"]["mdlite"], "1.1.0")  # the XSS window opens
        self.assertEqual(by_title["Upgrade mdlite to 1.2.0"]["tick"], 12)  # ...and closes
        self.assertFalse((self.p.dir / "static" / "uploads").exists(), "check uploads leaked into the site")
        self.assertIn("\nEnd of the roadmap timeline.", self.out)

    def test_repair_after_failure(self):
        def script(key, attempt, prompt):
            return reply(BROKEN_APP, requirements=False) if (key, attempt) == (1, 1) else good_script(key, attempt, prompt)
        model = FakeModel(script)
        self.assertTrue(self.run_ticks(model, ticks=1))
        repair_prompt = model.calls[1][1]
        self.assertIn("some checks failed", repair_prompt)
        self.assertIn("home page loads", repair_prompt)
        self.assertIn("Here is the app's current code", repair_prompt)
        self.assertEqual([a["attempt"] for a in self.p.attempts()], [1, 2])
        self.assertEqual(self.p.releases()[0]["tries"], 2)

    def test_failed_item_rolls_back_and_stays_queued(self):
        self.assertTrue(self.run_ticks(FakeModel(good_script), ticks=1))
        before = (self.p.dir / "app.py").read_text()

        def script(key, attempt, prompt):
            return f"### File: app.py\n```python\n{BROKEN_APP}\n```\n### File: extra.py\n```python\nx = 1\n```\n"
        self.assertFalse(self.run_ticks(FakeModel(script), ticks=1, max_repairs=2))
        st = self.p.state()
        self.assertEqual(st["features_done"], 1)
        self.assertEqual([d["id"] for d in st["queue"]], ["feature-2"])
        self.assertEqual((self.p.dir / "app.py").read_text(), before, "failed attempt wasn't rolled back")
        self.assertFalse((self.p.dir / "extra.py").exists(), "new file from failed attempt wasn't removed")
        self.assertTrue((self.p.meta / "attempts" / "feature-2" / "try3" / "reply.md").exists())
        self.assertEqual(len(self.p.releases()), 1)
        # Next run retries the queued item first, without advancing the clock.
        model = FakeModel(good_script)
        self.assertTrue(self.run_ticks(model, ticks=0))
        self.assertEqual([k for k, _ in model.calls], [2])
        self.assertEqual(self.p.state()["tick"], 2)

    def test_fix_item_runs_regression_checks(self):
        self.assertTrue(self.run_ticks(FakeModel(good_script), ticks=3))
        self.p.enqueue(WorkItem("fix", "fix-1", "Search is slow", "Make it faster.", tick=3))

        def script(key, attempt, prompt):
            if attempt == 1:  # first try breaks comments, a feature-1 check
                return reply(FULL_APP.replace('"/posts/<int:pid>/comments"', '"/posts/<int:pid>/comment"'))
            return reply(FULL_APP)
        model = FakeModel(script)
        self.assertTrue(self.run_ticks(model, ticks=0))
        self.assertTrue(model.calls[0][1].startswith("Bug ticket:\n\nSearch is slow"))
        self.assertIn("comments", self.p.attempts()[-2]["failed"])
        self.assertEqual(self.p.releases()[-1]["kind"], "fix")

    def test_regression_is_caught(self):
        self.assertTrue(self.run_ticks(FakeModel(good_script), ticks=3))
        broken = FULL_APP.replace('@app.post("/posts/<int:pid>/comments")', '@app.post("/posts/<int:pid>/comment")')
        (self.p.dir / "app.py").write_text(broken)
        self.assertIn("comments", run_checks(self.p, 3)["failed"])


class FilesTest(unittest.TestCase):
    def test_parse_formats(self):
        text = "Intro\n\n**app.py**\n```python\nprint(1)\n```\n\n### File: ./templates/base.html\n```html\n<p>hi</p>\n```\n"
        self.assertEqual(parse_files(text), {"app.py": "print(1)\n", "templates/base.html": "<p>hi</p>\n"})

    def test_unsafe_paths_are_skipped(self):
        d = Path(tempfile.mkdtemp())
        paths = ("../evil.py", "/etc/x.py", ".git/hooks/x.py", ".builder/state.json", ".venv/x.py", "ok.py")
        res = apply_files("".join(f"### File: {p}\n```\nx\n```\n" for p in paths), d)
        self.assertEqual(res["written"], ["ok.py"])
        self.assertEqual(len(res["skipped"]), 5)

    def test_first_prompt_has_no_code_section(self):
        self.assertNotIn("current code", build_prompt("Feature request:\n\nBuild it.", None, None))
        self.assertIn("Files you don't include", build_prompt("Feature request:\n\nAdd X.", "### File: app.py", None))


if __name__ == "__main__":
    unittest.main()
