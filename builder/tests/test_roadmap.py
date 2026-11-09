"""The blog roadmap's checks are fair: a correct app passes all of them, broken apps fail the right one.

Run: python3 -m unittest discover -s builder/tests -t .
"""
import tempfile
import unittest
from pathlib import Path

from builder import deps
from builder.build import run_checks
from builder.project import Project
from builder.roadmap import load

REFERENCE = (Path(__file__).parent / "reference_app.py").read_text()
EARLY = {"mdlite": "1.0.0", "uploadkit": "1.0.0", "pager": "1.0.0"}
LATE = {"mdlite": "2.0.0", "uploadkit": "1.0.1", "pager": "1.0.1"}


def grade(src, level, versions=EARLY):
    p = Project.create("site", "blog", base=Path(tempfile.mkdtemp()))
    (p.dir / "app.py").write_text(src)
    (p.dir / "requirements.txt").write_text("\n".join(f"{k}=={v}" for k, v in versions.items()) + "\n")
    deps.install(p.meta / "libs", versions)
    return p, run_checks(p, level)


class RoadmapTest(unittest.TestCase):
    def test_roadmap_loads_with_ten_features_and_a_valid_timeline(self):
        rm = load("blog")
        self.assertEqual(len(rm.stages), 10)
        self.assertEqual([n for t in rm.timeline for n in t.features], list(range(1, 11)))

    def test_reference_passes_everything_with_early_and_late_libraries(self):
        for versions in (EARLY, LATE, {**EARLY, "mdlite": "1.1.0"}):
            with self.subTest(versions=versions):
                _, res = grade(REFERENCE, 10, versions)
                self.assertEqual(res["failed"], [], res["error"])
                self.assertEqual(res["total"], 21)

    def test_checks_dont_leave_uploads_behind(self):
        p, res = grade(REFERENCE, 6)
        self.assertEqual(res["failed"], [], res["error"])
        self.assertFalse((p.dir / "static" / "uploads").exists(), "uploaded test files were left in the project")

    def test_broken_features_fail_the_right_check(self):
        cases = {
            "avatar upload": REFERENCE.replace("<img src='/static/uploads/{author['avatar']}' alt=''>", ""),
            "avatar rejects non-images": REFERENCE.replace('return f"Upload failed: {e}", 400', 'return redirect("/")'),
            "pagination": REFERENCE.replace("per_page=5", "per_page=50"),
            "profiles": REFERENCE.replace("bio=md(u[\"bio\"] or \"\")", "bio=u[\"bio\"]"),
            "admin panel": REFERENCE.replace("    if not is_admin():\n        abort(403)\n    c = db()\n", "    c = db()\n"),
            "messages": REFERENCE.replace("    if current_user() not in (m[\"sender\"], m[\"recipient\"]):\n        abort(403)\n", ""),
        }
        for check, src in cases.items():
            with self.subTest(check=check):
                self.assertNotEqual(src, REFERENCE, "the replacement didn't apply")
                _, res = grade(src, 10)
                self.assertIn(check, res["failed"], res["error"])

    def test_pager_bug_is_latent_not_failing(self):
        """pager 1.0.0 drops a partial last page, but the checks use 10 posts, so the Builder isn't blocked."""
        _, res = grade(REFERENCE, 7, {**EARLY, "pager": "1.0.0"})
        self.assertEqual(res["failed"], [], res["error"])


if __name__ == "__main__":
    unittest.main()
