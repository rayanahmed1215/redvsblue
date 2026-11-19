"""End-to-end tests of builder2 (plan, then one file per call) with a fake model (no LLM needed).

Run: python3 -m unittest discover -s builder2/tests -t .
"""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from builder import deps
from builder.config import VENV_PY, ModelConfig
from builder.files import parse_files
from builder.items import WorkItem
from builder.project import Project
from builder.roadmap import load as load_roadmap
from builder.tests.fixtures import FULL_APP, STAGE1_APP
from builder2.build import CHECKER, run, run_checks
from builder2.files import parse_one, write_file
from builder2.plan import MAX_PLAN_FILES, check_plan, file_prompt, parse_plan, plan_prompt

BROKEN_APP = "from flask import Flask\napp = Flask(__name__)\n"  # home page 404s
ROADMAP = load_roadmap("blog")
REFERENCE = (Path(__file__).parents[2] / "builder" / "tests" / "reference_app.py").read_text()  # all 10 features
FEATURE = WorkItem("feature", "feature-1", "t", "x", 1, feature=1)


def reply(app_src, requirements=True, mdlite="1.0.0"):
    """The files a scripted model wants to end up with, in `### File:` format."""
    text = f"### File: app.py\n```python\n{app_src}\n```\n"
    if requirements is True:
        requirements = f"flask\nmdlite=={mdlite}\n"
    if requirements:
        text += f"\n### File: requirements.txt\n```\n{requirements}```\n"
    return text


def plan_for(paths):
    return ("## Files\n" + "".join(f"- {p} (change): update it\n" for p in paths)
            + "\n## Connections\n- nothing new\n\n## Libraries\n- as before\n")


class FakeModel:
    """Scripted replies. `script(item_key, attempt, prompt)` returns the files the model wants, as `reply()` text.

    A plan call answers with a plan listing those files; each file call answers with that one file.
    item_key is the feature number for feature requests, or "dep"/"fix" for other items.
    """

    def __init__(self, script):
        self.script, self.plans, self.file_calls, self.files = script, [], [], {}

    def __call__(self, cfg, messages, seed):
        prompt = messages[-1]["content"]
        asked = re.search(r"Write `(.+?)` now", prompt)
        if asked is None:
            key = self.key_of(prompt)
            attempt = 1 + sum(1 for k, _ in self.plans if k == key)
            self.plans.append((key, prompt))
            self.files = parse_files(self.script(key, attempt, prompt))
            text = plan_for(self.files)
        else:
            self.file_calls.append((asked[1], prompt))
            text = self.file_reply(asked[1])
        return {"text": text, "tokens": 100, "prompt_tokens": 100, "tok_s": 50.0, "seconds": 0.1, "truncated": False}

    def file_reply(self, path):
        return f"### File: {path}\n```\n{self.files[path]}```\n" if path in self.files else "I have nothing to write."

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
        rels = self.p.releases()
        self.assertEqual([r["version"] for r in rels], ["v1", "v2", "v3", "v4", "v5", "v6"])
        self.assertEqual((rels[4]["deps"], rels[5]["kind"], rels[5]["deps"]),
                         ({"mdlite": "1.0.0"}, "dep_update", {"mdlite": "1.1.0"}))
        self.assertEqual(self.commits()[0], "dep_update: Upgrade mdlite to 1.1.0")
        self.assertIn('__version__ = "1.1.0"', (self.p.meta / "libs" / "mdlite.py").read_text())

    def test_one_plan_call_then_one_call_per_file(self):
        model = FakeModel(good_script)
        self.assertTrue(self.run_ticks(model, ticks=2))
        self.assertEqual([k for k, _ in model.plans], [1, 2])
        # requirements.txt is written first, so the code that follows sees the library pins
        self.assertEqual([p for p, _ in model.file_calls], ["app.py", "requirements.txt", "app.py"])
        plan_call, file_call = model.plans[1][1], model.file_calls[2][1]
        self.assertIn("Do not write any code yet", plan_call)
        self.assertIn("## Connections", plan_call)
        self.assertIn("Here is the app's current code", plan_call)
        self.assertIn("Here is the plan for this work", file_call)
        self.assertIn("- app.py (change): update it", file_call)
        self.assertIn("mdlite==1.0.0", file_call, "the file call should see requirements.txt written just before it")
        entry = self.p.attempts()[-1]
        self.assertEqual(entry["plan_files"], ["requirements.txt", "app.py"])
        self.assertEqual([c["step"] for c in entry["calls"]], ["plan", "requirements.txt", "app.py"])
        self.assertEqual(entry["tokens"], 300)
        try_dir = self.p.meta / "attempts" / "feature-2" / "try1"
        self.assertIn("## Files", (try_dir / "plan.md").read_text())
        self.assertIn("<!-- reply for app.py -->", (try_dir / "reply.md").read_text())

    def test_files_outside_the_plan_are_never_written(self):
        class Sneaky(FakeModel):
            def file_reply(self, path):
                return super().file_reply(path) + "\n### File: extra.py\n```python\nx = 1\n```\n"
        self.assertTrue(self.run_ticks(Sneaky(good_script), ticks=1))
        self.assertFalse((self.p.dir / "extra.py").exists())
        self.assertEqual(self.p.attempts()[0]["files_written"], ["app.py"])

    def test_cut_off_file_fails_the_try_and_the_retry_sees_why(self):
        class CutOff(FakeModel):
            def __call__(self, cfg, messages, seed):
                gen = super().__call__(cfg, messages, seed)
                if len(self.file_calls) == 1 and len(self.plans) == 1:  # the first file of the first try
                    gen.update(text="### File: app.py\n```python\nfrom flask import Fl", truncated=True)
                return gen
        model = CutOff(good_script)
        self.assertTrue(self.run_ticks(model, ticks=1))
        first = self.p.attempts()[0]
        self.assertEqual((first["failed"], first["files_written"], first["truncated"]), (["file not written"], [], True))
        retry = model.plans[1][1]
        self.assertIn("was cut off", retry)
        self.assertIn("This was your plan for that attempt", retry)
        self.assertIn("Plan the fix", retry)
        self.assertEqual(self.p.releases()[0]["tries"], 2)

    def test_plan_without_files_fails_the_try(self):
        class NoPlan(FakeModel):
            def __call__(self, cfg, messages, seed):
                gen = super().__call__(cfg, messages, seed)
                if len(self.plans) == 1 and not self.file_calls:
                    gen["text"] = "I will add the feature carefully."
                return gen
        model = NoPlan(good_script)
        self.assertTrue(self.run_ticks(model, ticks=1))
        self.assertEqual(self.p.attempts()[0]["failed"], ["plan"])
        self.assertIn("didn't list any files", model.plans[1][1])

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
        self.assertIn("'requests' isn't available", model.plans[1][1])

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
        self.assertIn("`render()` has been renamed to `to_html()`", model.plans[0][1])
        self.assertIn("has no attribute 'render'", self.p.attempts()[-2]["error"])
        self.assertIn("has no attribute 'render'", model.file_calls[-1][1], "file calls of a retry should see the error")
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

    def test_upgrade_plan_that_forgets_requirements_still_gets_asked_for_it(self):
        self.assertTrue(self.run_ticks(FakeModel(good_script), ticks=5))
        st = self.p.state()
        st["published"]["mdlite"].append("1.1.0")
        self.p.save_state(st)
        self.p.enqueue(deps.dep_update_item("mdlite", "1.1.0", "1.0.0", tick=5))

        class Forgetful(FakeModel):
            def __call__(self, cfg, messages, seed):
                gen = super().__call__(cfg, messages, seed)
                if gen["text"].startswith("## Files"):
                    gen["text"] = plan_for(["app.py"])
                return gen
        model = Forgetful(good_script)
        self.assertTrue(self.run_ticks(model, ticks=0))
        self.assertEqual([p for p, _ in model.file_calls][-2:], ["requirements.txt", "app.py"])
        self.assertEqual(self.p.state()["deps"], {"mdlite": "1.1.0"})

    def test_prompt_includes_library_docs(self):
        model = FakeModel(good_script)
        self.assertTrue(self.run_ticks(model, ticks=1))
        for prompt in (model.plans[0][1], model.file_calls[0][1]):
            self.assertIn("Available libraries", prompt)
            for lib in ("# mdlite 1.0.0", "# uploadkit 1.0.0", "# pager 1.0.0"):
                self.assertIn(lib, prompt)

    def test_ticks_limit_and_resume(self):
        self.assertTrue(self.run_ticks(FakeModel(good_script), ticks=2))
        self.assertEqual(self.p.state()["tick"], 2)
        model = FakeModel(good_script)
        self.assertTrue(self.run_ticks(model, ticks=4))
        self.assertEqual([k for k, _ in model.plans], [3, 4, 5, "dep"])  # tick 6 ships mdlite 1.1.0

    def test_whole_roadmap_timeline(self):
        model = FakeModel(full_script)
        self.assertTrue(self.run_ticks(model))
        st = self.p.state()
        self.assertEqual((st["tick"], st["features_done"], st["queue"]), (14, 10, []))
        # features, plus an upgrade whenever a library the site uses ships a new version
        self.assertEqual([k for k, _ in model.plans], [1, 2, 3, 4, 5, "dep", 6, 7, 8, "dep", "dep", 9, "dep", 10, "dep"])
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
        repair_prompt = model.plans[1][1]
        self.assertIn("didn't work", repair_prompt)
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
        self.assertEqual([k for k, _ in model.plans], [2])
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
        self.assertTrue(model.plans[0][1].startswith("Bug ticket:\n\nSearch is slow"))
        self.assertIn("comments", self.p.attempts()[-2]["failed"])
        self.assertEqual(self.p.releases()[-1]["kind"], "fix")

    def test_ticket_is_queued_and_released(self):
        self.assertTrue(self.run_ticks(FakeModel(good_script), ticks=2))
        self.p.add_ticket("Comments allow HTML", "Escape comment bodies.")
        self.p.add_ticket("Second ticket", "Something else.")
        model = FakeModel(good_script)
        self.assertTrue(self.run_ticks(model, ticks=0))
        self.assertEqual([k for k, _ in model.plans], ["fix", "fix"])
        self.assertEqual([r["kind"] for r in self.p.releases()][-2:], ["fix", "fix"])
        self.assertEqual(self.p.state()["tick"], 2, "processing tickets must not advance the clock")

    def test_regression_is_caught(self):
        self.assertTrue(self.run_ticks(FakeModel(good_script), ticks=3))
        broken = FULL_APP.replace('@app.post("/posts/<int:pid>/comments")', '@app.post("/posts/<int:pid>/comment")')
        (self.p.dir / "app.py").write_text(broken)
        self.assertIn("comments", run_checks(self.p, 3)["failed"])


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_parse_plan_variants(self):
        text = ("Here is my plan.\n\n## Files\n- app.py (change): add the search route\n"
                "* `templates/search.html` (new): results list\n- **./templates/base.html** (change): search box\n"
                "1. requirements.txt (change): pin mdlite\n- app.py (change): listed twice\n\n"
                "## Connections\n- route `/search` -> `search()` in app.py renders templates/other.html\n")
        self.assertEqual(parse_plan(text), ["app.py", "templates/search.html", "templates/base.html", "requirements.txt"])
        self.assertEqual(parse_plan("### files to change\n- app.py: stuff\n"), ["app.py"])
        self.assertEqual(parse_plan("No sections here.\n- app.py (change)\n"), ["app.py"])  # falls back to the whole reply
        self.assertEqual(parse_plan("I'll just do it."), [])

    def test_check_plan_orders_files_by_what_depends_on_what(self):
        paths, err = check_plan(["templates/a.html", "app.py", "static/s.css", "requirements.txt", "db.py"], self.dir, FEATURE)
        self.assertIsNone(err)
        self.assertEqual(paths, ["requirements.txt", "app.py", "db.py", "templates/a.html", "static/s.css"])

    def test_check_plan_rejects_bad_plans(self):
        self.assertIn("didn't list any files", check_plan([], self.dir, FEATURE)[1])
        for bad in ("../evil.py", "/etc/x.py", ".git/hooks/x.py", ".builder/state.json"):
            self.assertIn(bad, check_plan(["app.py", bad], self.dir, FEATURE)[1])
        many = [f"templates/t{i}.html" for i in range(MAX_PLAN_FILES + 1)]
        self.assertIn("at most", check_plan(many, self.dir, FEATURE)[1])

    def test_upgrade_always_includes_requirements(self):
        item = deps.dep_update_item("mdlite", "1.1.0", "1.0.0", tick=5)
        self.assertEqual(check_plan(["app.py"], self.dir, item), (["requirements.txt", "app.py"], None))
        self.assertEqual(check_plan([], self.dir, item), (["requirements.txt"], None))

    def test_prompts(self):
        first = plan_prompt("Feature request:\n\nBuild it.", "")
        self.assertNotIn("current code", first)
        self.assertNotIn("Plan the fix", first)
        self.assertIn("## Connections", first)
        retry = plan_prompt("Feature request:\n\nAdd X.", "### File: app.py", "LIBDOCS", "OLD PLAN", "No filter named 'x'")
        for part in ("LIBDOCS", "Here is the app's current code", "No filter named 'x'", "OLD PLAN", "Plan the fix"):
            self.assertIn(part, retry)
        new = file_prompt("Feature request:\n\nAdd X.", "### File: app.py", "", "THE PLAN", "templates/t.html", exists=False)
        self.assertIn("THE PLAN", new)
        self.assertIn("Write `templates/t.html` now. It is a new file.", new)
        self.assertTrue(new.endswith("### File: templates/t.html\n```html\n...\n```"))
        self.assertIn("It replaces the current `app.py`", file_prompt("r", "c", "", "p", "app.py", exists=True))


class FilesTest(unittest.TestCase):
    def test_parse_one(self):
        labelled = "Sure.\n\n### File: templates/t.html\n```html\n<p>hi</p>\n```\n\n### File: other.py\n```python\nx = 1\n```\n"
        self.assertEqual(parse_one(labelled, "templates/t.html"), "<p>hi</p>\n")
        self.assertEqual(parse_one("Here it is:\n```html\n<p>hi</p>\n```\nDone.", "templates/t.html"), "<p>hi</p>\n")
        self.assertEqual(parse_one("### File: requirements.txt\n```\n```\n", "requirements.txt"), "")
        self.assertIsNone(parse_one("```html\n<p>a</p>\n```\n```html\n<p>b</p>\n```\n", "t.html"), "two unlabelled blocks")
        self.assertIsNone(parse_one("### File: app.py\n```python\nimport flask\nx = ", "app.py"), "cut off")
        self.assertIsNone(parse_one("no code at all", "app.py"))

    def test_write_file(self):
        d = Path(tempfile.mkdtemp())
        self.assertTrue(write_file(d, "templates/t.html", "x"))
        self.assertEqual((d / "templates" / "t.html").read_text(), "x")
        for bad in ("../evil.py", ".git/config", ".builder/state.json"):
            self.assertFalse(write_file(d, bad, "x"))


class FilesAgreeTest(unittest.TestCase):
    """The connection check in builder2/checker.py, run the way the Builder runs it."""

    APP = ("from flask import Flask, render_template\napp = Flask(__name__)\n"
           "@app.template_filter('shout')\ndef shout(s):\n    return s.upper()\n"
           "@app.get('/')\ndef home():\n    return render_template('index.html', name='x')\n")
    BASE = "<a href=\"{{ url_for('home') }}\">home</a>{% block body %}{% endblock %}"
    INDEX = "{% extends 'base.html' %}{% block body %}{{ name|shout }}{% endblock %}"

    def check(self, files):
        d = Path(tempfile.mkdtemp())
        for rel, content in files.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(content)
        out = subprocess.run([str(VENV_PY), str(CHECKER), str(d), str(ROADMAP.checks), "1"], capture_output=True, text=True)
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_connected_app_passes(self):
        res = self.check({"app.py": self.APP, "templates/base.html": self.BASE, "templates/index.html": self.INDEX})
        self.assertNotIn("files agree", res["failed"])
        self.assertNotIn("home page loads", res["failed"])

    def test_every_mismatch_is_reported_at_once(self):
        res = self.check({
            "app.py": self.APP + "@app.get('/s')\ndef s():\n    return render_template('search.html')\n",
            "templates/base.html": self.BASE.replace("'home'", "'search'"),
            "templates/index.html": self.INDEX.replace("shout", "get_post_tags"),
            "templates/tag.html": "{% extends 'layout.html' %}",
        })
        self.assertEqual((res["failed"], res["total"]), (["files agree"], 1))
        for part in ("templates/index.html line 1: No filter named 'get_post_tags'",
                     "app.py uses the template 'search.html', but templates/search.html doesn't exist",
                     "templates/tag.html uses the template 'layout.html'",
                     "templates/base.html calls url_for('search'), but no route function is named 'search'",
                     "The route functions are: home, s, static"):
            self.assertIn(part, res["error"])


if __name__ == "__main__":
    unittest.main()
