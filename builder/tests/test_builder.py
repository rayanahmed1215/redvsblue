"""End-to-end tests of the build loop with a fake model (no LLM needed).

Run: python3 -m unittest discover -s builder/tests -t .
"""
import tempfile
import unittest
from pathlib import Path

from builder.build import build, build_prompt, run_checks
from builder.config import ModelConfig
from builder.files import apply_files, parse_files
from builder.project import Project
from builder.tests.fixtures import FULL_APP, STAGE1_APP

BROKEN_APP = "from flask import Flask\napp = Flask(__name__)\n"  # home page 404s


def reply(app_src, requirements=True):
    text = f"### File: app.py\n```python\n{app_src}\n```\n"
    if requirements:
        text += "\n### File: requirements.txt\n```\nflask\nmarkdown\n```\n"
    return text


class FakeModel:
    """Scripted replies. `script(stage, attempt, prompt)` returns the reply text."""

    def __init__(self, script):
        self.script, self.calls = script, []

    def __call__(self, cfg, messages, seed):
        prompt = messages[-1]["content"]
        stage = self.stage_of(prompt)
        attempt = 1 + sum(1 for s, _ in self.calls if s == stage)
        self.calls.append((stage, prompt))
        return {"text": self.script(stage, attempt, prompt), "tokens": 100, "prompt_tokens": 100,
                "tok_s": 50.0, "seconds": 0.1, "truncated": False}

    @staticmethod
    def stage_of(prompt):
        firsts = ["Build a small blog", "Add user accounts", "Let authors edit", "Add tags and search", "Let authors format"]
        return next(i for i, f in enumerate(firsts, 1) if prompt.startswith(f))


def good_script(stage, attempt, prompt):
    return reply(STAGE1_APP, requirements=False) if stage == 1 else reply(FULL_APP)


class BuildLoopTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.p = Project.create("site", "blog", base=self.base)
        self.cfg = ModelConfig()
        self.out = []

    def run_build(self, model, **kw):
        return build(self.p, self.cfg, log=self.out.append, chat=model, **kw)

    def commits(self):
        return self.p.git("log", "--format=%s").strip().splitlines()

    def test_full_build_commits_every_stage(self):
        self.assertTrue(self.run_build(FakeModel(good_script)))
        self.assertEqual(self.p.state()["stage_done"], 5)
        self.assertEqual(len(self.commits()), 6)  # start + 5 stages
        self.assertTrue(self.commits()[0].startswith("Stage 5:"))
        self.assertEqual(len(self.p.attempts()), 5)

    def test_repair_after_failure(self):
        def script(stage, attempt, prompt):
            if stage == 1 and attempt == 1:
                return reply(BROKEN_APP, requirements=False)
            return good_script(stage, attempt, prompt)
        model = FakeModel(script)
        self.assertTrue(self.run_build(model, until=1))
        repair_prompt = model.calls[1][1]
        self.assertIn("some checks failed", repair_prompt)
        self.assertIn("home page loads", repair_prompt)
        self.assertIn("Here is the app's current code", repair_prompt)
        self.assertEqual([a["attempt"] for a in self.p.attempts()], [1, 2])

    def test_stuck_stage_rolls_back(self):
        self.assertTrue(self.run_build(FakeModel(good_script), until=1))
        before = (self.p.dir / "app.py").read_text()

        def script(stage, attempt, prompt):
            return f"### File: app.py\n```python\n{BROKEN_APP}\n```\n### File: extra.py\n```python\nx = 1\n```\n"
        self.assertFalse(self.run_build(FakeModel(script), until=2, max_repairs=2))
        self.assertEqual(self.p.state()["stage_done"], 1)
        self.assertEqual((self.p.dir / "app.py").read_text(), before, "failed attempt wasn't rolled back")
        self.assertFalse((self.p.dir / "extra.py").exists(), "new file from failed attempt wasn't removed")
        self.assertEqual(len([a for a in self.p.attempts() if a["stage"] == 2]), 3)
        self.assertTrue((self.p.meta / "attempts" / "stage2" / "try3" / "reply.md").exists())

    def test_resume_continues_from_last_stage(self):
        self.assertTrue(self.run_build(FakeModel(good_script), until=2))
        model = FakeModel(good_script)
        self.assertTrue(self.run_build(model))
        self.assertEqual([s for s, _ in model.calls], [3, 4, 5])

    def test_regression_is_caught(self):
        self.assertTrue(self.run_build(FakeModel(good_script), until=3))
        broken = FULL_APP.replace('@app.post("/posts/<int:pid>/comments")', '@app.post("/posts/<int:pid>/comment")')
        (self.p.dir / "app.py").write_text(broken)
        self.assertIn("comments", run_checks(self.p, 3)["failed"])


class FilesTest(unittest.TestCase):
    def test_parse_formats(self):
        text = "Intro\n\n**app.py**\n```python\nprint(1)\n```\n\n### File: ./templates/base.html\n```html\n<p>hi</p>\n```\n"
        self.assertEqual(parse_files(text), {"app.py": "print(1)\n", "templates/base.html": "<p>hi</p>\n"})

    def test_unsafe_paths_are_skipped(self):
        d = Path(tempfile.mkdtemp())
        text = "".join(f"### File: {p}\n```\nx\n```\n" for p in ("../evil.py", "/etc/x.py", ".git/hooks/x.py", ".builder/state.json", "ok.py"))
        res = apply_files(text, d)
        self.assertEqual(res["written"], ["ok.py"])
        self.assertEqual(len(res["skipped"]), 4)

    def test_first_prompt_has_no_code_section(self):
        self.assertNotIn("current code", build_prompt("Build it.", None, None))
        self.assertIn("Files you don't include", build_prompt("Add X.", "### File: app.py", None))


if __name__ == "__main__":
    unittest.main()
