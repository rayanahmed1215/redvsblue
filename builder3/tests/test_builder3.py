"""Tests for builder3: edit blocks, and the build loop using them (with a scripted fake model)."""
import re
import tempfile
import unittest
from pathlib import Path

from builder.config import ModelConfig
from builder.files import parse_files
from builder.project import Project
from builder.tests.fixtures import FULL_APP, STAGE1_APP
from builder2.tests.test_builder2 import FakeModel, good_script, plan_for, reply
from builder3.build import run
from builder3.edits import apply_edits, parse_edits

SRC = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"


def block(find, replace):
    return f"<<<<<<< FIND\n{find}=======\n{replace}>>>>>>> REPLACE\n"


class EditsTest(unittest.TestCase):
    def test_parse_several_blocks_in_order(self):
        text = "Here are the edits:\n\n" + block("x\n", "y\n") + "\n" + block("p\nq\n", "")
        edits, err = parse_edits(text)
        self.assertIsNone(err)
        self.assertEqual(edits, [("x\n", "y\n"), ("p\nq\n", "")])

    def test_parse_inside_a_code_fence(self):
        edits, err = parse_edits("```python\n" + block("x\n", "y\n") + "```\n")
        self.assertEqual((edits, err), ([("x\n", "y\n")], None))

    def test_cut_off_block_is_reported(self):
        edits, err = parse_edits(block("x\n", "y\n") + "<<<<<<< FIND\nz\n=======\nhalf")
        self.assertEqual(len(edits), 1)
        self.assertIn("1 of your 2 edit blocks never reached", err)

    def test_exact_edit(self):
        out, errs = apply_edits(SRC, [("    return 2\n", "    return 3\n")])
        self.assertEqual((errs, out), ([], SRC.replace("return 2", "return 3")))

    def test_edits_apply_in_order_and_can_delete(self):
        out, errs = apply_edits(SRC, [("return 1", "return 10"), ("return 10\n", "return 11\n"),
                                      ("\n\ndef b():\n    return 2\n", "")])
        self.assertEqual((errs, out), ([], "def a():\n    return 11\n"))

    def test_trailing_spaces_are_forgiven(self):
        src = "def a():   \n    return 1\n"
        out, errs = apply_edits(src, [("def a():\n    return 1\n", "def a():\n    return 5\n")])
        self.assertEqual((errs, out), ([], "def a():\n    return 5\n"))

    def test_indentation_is_not_forgiven(self):
        _, errs = apply_edits(SRC, [("return 2\n  ", "x")])
        self.assertEqual(len(errs), 1)
        _, errs = apply_edits(SRC, [("def b():\nreturn 2\n", "x")])
        self.assertIn("isn't in the file", errs[0])

    def test_missing_find_shows_the_closest_lines(self):
        _, errs = apply_edits(SRC, [("def b():\n    return 22\n", "x\n")], "app.py")
        self.assertEqual(len(errs), 1)
        self.assertIn("Edit 1 for `app.py`: the FIND text isn't in the file", errs[0])
        self.assertIn("   5| def b():", errs[0])
        self.assertIn("   6|     return 2", errs[0])

    def test_unlike_text_says_nothing_matches(self):
        _, errs = apply_edits(SRC, [("@app.route('/zzz')\n", "x")])
        self.assertIn("Nothing in the file looks like it", errs[0])

    def test_ambiguous_find_is_rejected(self):
        _, errs = apply_edits(SRC, [("    return", "    yield")])
        self.assertIn("appears 2 times", errs[0])

    def test_empty_find_is_rejected(self):
        _, errs = apply_edits(SRC, [("\n", "x")])
        self.assertIn("empty FIND", errs[0])

    def test_search_is_accepted_as_find(self):
        edits, err = parse_edits("<<<<<<< SEARCH\nx\n=======\ny\n>>>>>>> REPLACE\n")
        self.assertEqual((edits, err), ([("x\n", "y\n")], None))

    def test_edits_that_change_nothing_leave_the_file_as_it_is(self):
        out, errs = apply_edits(SRC, [("    return 1\n", "    return 1\n"), ("    return 2\n", "    return 2\n")])
        self.assertEqual((errs, out), ([], SRC))

    def test_one_unchanged_edit_among_real_ones_is_skipped(self):
        out, errs = apply_edits(SRC, [("    return 1\n", "    return 1\n"), ("    return 2\n", "    return 3\n")])
        self.assertEqual((errs, out), ([], SRC.replace("return 2", "return 3")))

    def test_every_error_is_reported(self):
        _, errs = apply_edits(SRC, [("nope1\n", "x"), ("    return 1\n", "    return 9\n"), ("nope2\n", "y")])
        self.assertEqual([e.split(":")[0] for e in errs], ["Edit 1 for `the file`", "Edit 3 for `the file`"])


class EditModel(FakeModel):
    """FakeModel that understands builder3's edit prompt: for an existing file it replies with one edit
    replacing the whole current file (taken from the prompt) with the scripted content."""

    def __init__(self, script, edit_reply=None):
        super().__init__(script)
        self.edit_calls = []
        self.edit_reply = edit_reply or (lambda path, current, wanted, n: block(current, wanted))

    def __call__(self, cfg, messages, seed):
        prompt = messages[-1]["content"]
        asked = re.search(r"Change `(.+?)` now", prompt)
        if asked is None:
            return super().__call__(cfg, messages, seed)
        path = asked[1]
        current = parse_files(prompt.split("Here is the plan for this work", 1)[0])[path]
        self.edit_calls.append((path, prompt))
        text = self.edit_reply(path, current, self.files[path], len(self.edit_calls))
        truncated = text.endswith("<<CUT>>")
        return {"text": text.removesuffix("<<CUT>>"), "tokens": 50, "prompt_tokens": 100, "tok_s": 50.0,
                "seconds": 0.1, "truncated": truncated}


class RunTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.p = Project.create("site", "blog", base=self.base)
        self.cfg = ModelConfig()
        self.out = []

    def run_ticks(self, model, ticks=None, **kw):
        return run(self.p, self.cfg, ticks=ticks, log=self.out.append, chat=model, **kw)

    def test_new_files_are_written_whole_and_existing_files_are_edited(self):
        model = EditModel(good_script)
        self.assertTrue(self.run_ticks(model, ticks=2))
        # tick 1: app.py is new (whole file); tick 2: requirements.txt is new, app.py exists (edits)
        self.assertEqual([p for p, _ in model.file_calls], ["app.py", "requirements.txt"])
        self.assertEqual([p for p, _ in model.edit_calls], ["app.py"])
        edit_prompt = model.edit_calls[0][1]
        self.assertIn("<<<<<<< FIND", edit_prompt)
        self.assertIn("- app.py (change): update it", edit_prompt)
        self.assertEqual((self.p.dir / "app.py").read_text().rstrip(), FULL_APP.rstrip())
        entry = self.p.attempts()[-1]
        self.assertEqual(entry["written_as"], {"requirements.txt": "new", "app.py": "1 edits"})
        self.assertIn("app.py (1 edits)", self.out[-2])
        self.assertEqual([r["version"] for r in self.p.releases()], ["v1", "v2"])

    def test_bad_find_fails_the_try_leaves_the_file_and_the_retry_sees_why(self):
        def edits(path, current, wanted, n):
            if n == 1:
                return block("def this_is_not_in_the_file():\n", "x\n")
            return block(current, wanted)
        model = EditModel(good_script, edits)
        self.assertTrue(self.run_ticks(model, ticks=1))
        before = (self.p.dir / "app.py").read_text()
        self.assertTrue(self.run_ticks(model, ticks=1))
        first, second = self.p.attempts()[-2:]
        self.assertEqual(first["failed"], ["edits"])
        self.assertIn("`app.py` was not changed", first["error"])
        self.assertIn("the FIND text isn't in the file", first["error"])
        self.assertEqual(second["failed"], [])
        self.assertIn("isn't in the file", model.plans[-1][1], "the retry plan should see the edit error")
        self.assertNotEqual(before, (self.p.dir / "app.py").read_text())
        self.assertEqual(self.p.releases()[-1]["tries"], 2)

    def test_whole_file_reply_for_an_existing_file_is_accepted(self):
        model = EditModel(good_script, lambda path, current, wanted, n: f"### File: {path}\n```python\n{wanted}```\n")
        self.assertTrue(self.run_ticks(model, ticks=2))
        self.assertEqual(self.p.attempts()[-1]["written_as"]["app.py"], "whole")
        self.assertEqual((self.p.dir / "app.py").read_text().rstrip(), FULL_APP.rstrip())

    def test_cut_off_edits_fail_the_try(self):
        def edits(path, current, wanted, n):
            return block("x\n", "y\n") + "<<<<<<< FIND\nhalf<<CUT>>" if n == 1 else block(current, wanted)
        model = EditModel(good_script, edits)
        self.assertTrue(self.run_ticks(model, ticks=2))
        failed = [a for a in self.p.attempts() if a["failed"]]
        self.assertEqual(len(failed), 1)
        self.assertIn("was cut off", failed[0]["error"])
        self.assertIn("never reached", failed[0]["error"])

    def test_reply_with_no_edits_and_no_file_fails(self):
        model = EditModel(good_script, lambda path, current, wanted, n: "Sure!" if n == 1 else block(current, wanted))
        self.assertTrue(self.run_ticks(model, ticks=2))
        self.assertIn("had no `<<<<<<< FIND`", [a for a in self.p.attempts() if a["failed"]][0]["error"])

    def test_a_try_where_nothing_changes_fails(self):
        def edits(path, current, wanted, n):
            return block(current, current) if n == 1 else block(current, wanted)

        def script(key, attempt, prompt):  # the ticket only touches app.py
            return reply(STAGE1_APP + "\n# fixed\n", requirements=False) if key == "fix" else good_script(key, attempt, prompt)
        model = EditModel(script, edits)
        self.assertTrue(self.run_ticks(model, ticks=1))
        self.p.add_ticket("Fix it", "Something.")
        self.assertTrue(self.run_ticks(model, ticks=0))
        first, second = [a for a in self.p.attempts() if a["item"].startswith("fix")]
        self.assertEqual((first["failed"], first["written_as"]), (["edits"], {"app.py": "unchanged"}))
        self.assertIn("Your edits changed nothing", first["error"])
        self.assertEqual(second["failed"], [])

    def test_try_folders_keep_counting_across_runs(self):
        model = EditModel(good_script, lambda path, current, wanted, n: block("nope\n", "x\n"))
        self.assertTrue(self.run_ticks(model, ticks=1))
        self.assertFalse(self.run_ticks(model, ticks=1, max_repairs=1))  # tries 1-2 fail
        self.assertFalse(self.run_ticks(model, ticks=0, max_repairs=0))  # a new run: its try 1 goes in try3
        d = self.p.meta / "attempts" / "feature-2"
        self.assertEqual(sorted(p.name for p in d.iterdir()), ["try1", "try2", "try3"])
        self.assertEqual([a["folder"] for a in self.p.attempts()[-3:]], ["try1", "try2", "try3"])
        self.assertTrue((d / "try3" / "plan.md").exists())
        self.assertEqual((self.p.dir / "app.py").read_text().rstrip(), STAGE1_APP.rstrip(), "failed runs roll back to v1")


if __name__ == "__main__":
    unittest.main()
