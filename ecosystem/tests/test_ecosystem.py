"""Proves the answer key (advisories.json) is accurate: each bug exists in exactly the listed versions.

Run: python3 -m unittest discover -s ecosystem/tests
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ECO = Path(__file__).resolve().parent.parent
ADVISORIES = json.loads((ECO / "advisories.json").read_text())


def vkey(v):
    return tuple(int(x) for x in v.split("."))


def versions(lib):
    return sorted((p.name for p in (ECO / lib).iterdir() if p.is_dir() and p.name[0].isdigit()), key=vkey)


def load(lib, version):
    spec = importlib.util.spec_from_file_location(f"{lib}_{version.replace('.', '_')}", ECO / lib / version / f"{lib}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeUpload:
    def __init__(self, filename):
        self.filename = filename

    def save(self, path):
        Path(path).write_bytes(b"\x89PNG fake")


def mdlite_xss(mod):
    fn = getattr(mod, "render", None) or mod.to_html
    return "<script>" in fn("hi <script>alert(1)</script>")


def uploadkit_traversal(mod):
    root = Path(tempfile.mkdtemp())
    mod.save_upload(FakeUpload("../../escaped.png"), str(root / "static" / "uploads"))
    return (root / "escaped.png").exists()


def pager_bug(mod):
    return mod.paginate(range(7), 1, 5).pages == 1


PROBES = {"MDLITE-1": mdlite_xss, "UPLOADKIT-1": uploadkit_traversal, "PAGER-1": pager_bug}


class AnswerKeyTest(unittest.TestCase):
    def test_every_advisory_has_a_probe(self):
        self.assertEqual({a["id"] for a in ADVISORIES}, set(PROBES))

    def test_bugs_exist_exactly_in_affected_versions(self):
        for adv in ADVISORIES:
            for v in versions(adv["lib"]):
                affected = vkey(adv["introduced"]) <= vkey(v) < vkey(adv["fixed"])
                with self.subTest(advisory=adv["id"], version=v):
                    self.assertEqual(PROBES[adv["id"]](load(adv["lib"], v)), affected)


class PackagingTest(unittest.TestCase):
    def test_each_version_has_module_readme_and_changelog_entry(self):
        for lib in ("mdlite", "uploadkit", "pager"):
            changelog = (ECO / lib / "CHANGELOG.md").read_text()
            for v in versions(lib):
                with self.subTest(lib=lib, version=v):
                    self.assertTrue((ECO / lib / v / f"{lib}.py").exists())
                    self.assertIn(f"# {lib} {v}", (ECO / lib / v / "README.md").read_text())
                    self.assertIn(f"## {v}", changelog)
                    self.assertEqual(load(lib, v).__version__, v)

    def test_mdlite_api_change(self):
        self.assertTrue(hasattr(load("mdlite", "1.2.0"), "render"))
        new = load("mdlite", "2.0.0")
        self.assertFalse(hasattr(new, "render"))
        self.assertIn("<strong>x</strong>", new.to_html("**x**"))

    def test_silent_fix_is_silent(self):
        entry = (ECO / "uploadkit" / "CHANGELOG.md").read_text().split("## 1.0.0")[0]
        for word in ("security", "traversal", "vulnerab"):
            self.assertNotIn(word, entry.lower())


if __name__ == "__main__":
    unittest.main()
