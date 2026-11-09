"""End-to-end tests of the Builder with a fake model (no LLM needed).

Run: python3 -m unittest discover -s builder/tests -t .
"""
import tempfile
import unittest
from pathlib import Path

from builder.build import build_prompt, run, run_checks
from builder.config import ModelConfig
from builder.files import apply_files, parse_files
from builder.items import WorkItem
from builder.project import Project
from builder.tests.fixtures import FULL_APP, STAGE1_APP

BROKEN_APP = "from flask import Flask\napp = Flask(__name__)\n"  # home page 404s
FEATURE_STARTS = ["Build a small blog", "Add user accounts", "Let authors edit", "Add tags and search", "Let authors format"]


def reply(app_src, requirements=True):
    text = f"### File: app.py\n```python\n{app_src}\n```\n"
    if requirements:
        text += "\n### File: requirements.txt\n```\nflask\nmarkdown\n```\n"
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
            return next(i for i, f in enumerate(FEATURE_STARTS, 1) if f in prompt[:200])
        return "dep" if prompt.startswith("Dependency update:") else "fix"


def good_script(key, attempt, prompt):
    return reply(STAGE1_APP, requirements=False) if key == 1 else reply(FULL_APP)


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

    def test_full_timeline_releases_every_feature(self):
        self.assertTrue(self.run_ticks(FakeModel(good_script)))
        st = self.p.state()
        self.assertEqual((st["tick"], st["features_done"], st["queue"]), (5, 5, []))
        self.assertEqual(len(self.commits()), 6)  # start + 5 releases
        self.assertEqual(self.commits()[0], "feature: Let authors format posts with Markdown")
        self.assertEqual([r["version"] for r in self.p.releases()], ["v1", "v2", "v3", "v4", "v5"])
        self.assertEqual(self.p.git("tag").split(), ["v1", "v2", "v3", "v4", "v5"])
        self.assertIn("\nEnd of the roadmap timeline.", self.out)

    def test_ticks_limit_and_resume(self):
        self.assertTrue(self.run_ticks(FakeModel(good_script), ticks=2))
        self.assertEqual(self.p.state()["tick"], 2)
        model = FakeModel(good_script)
        self.assertTrue(self.run_ticks(model))
        self.assertEqual([k for k, _ in model.calls], [3, 4, 5])

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
