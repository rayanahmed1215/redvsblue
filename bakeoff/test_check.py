"""Checks the grader itself: a correct app must score 5/5, broken ones less.

Run: bakeoff/.venv/bin/python -m unittest bakeoff/test_check.py
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import grade, parse_files, write_files  # noqa: E402

GOOD_APP = '''
import sqlite3
from flask import Flask, request, redirect, render_template_string
app = Flask(__name__)
def db():
    c = sqlite3.connect("blog.db"); c.row_factory = sqlite3.Row; return c
with db() as c:
    c.execute("create table if not exists posts(id integer primary key, title, body)")
    c.execute("create table if not exists comments(id integer primary key, post_id, author, body)")
@app.get("/")
def home():
    posts = db().execute("select * from posts order by id desc").fetchall()
    return render_template_string("{% for p in posts %}<a href='/posts/{{p.id}}'>{{p.title}}</a>{% endfor %}", posts=posts)
@app.route("/posts/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        with db() as c:
            cur = c.execute("insert into posts(title, body) values (?, ?)", (request.form["title"], request.form["body"]))
        return redirect(f"/posts/{cur.lastrowid}")
    return "<form method=post><input name=title><textarea name=body></textarea></form>"
@app.get("/posts/<int:pid>")
def show(pid):
    c = db()
    p = c.execute("select * from posts where id=?", (pid,)).fetchone()
    cs = c.execute("select * from comments where post_id=?", (pid,)).fetchall()
    return render_template_string("<h1>{{p.title}}</h1><p>{{p.body}}</p>{% for x in cs %}<p>{{x.body}}</p>{% endfor %}", p=p, cs=cs)
@app.post("/posts/<int:pid>/comments")
def comment(pid):
    with db() as c:
        c.execute("insert into comments(post_id, author, body) values (?, ?, ?)", (pid, request.form["author"], request.form["body"]))
    return redirect(f"/posts/{pid}")
'''

NO_COMMENTS_APP = GOOD_APP.split("@app.post")[0]


def md(*files):
    return "\n\n".join(f"### File: {path}\n```python\n{src}\n```" for path, src in files)


def files_json(app_src):
    return md(("app.py", app_src))


class GraderTest(unittest.TestCase):
    def run_app(self, text, base=None):
        out = Path(tempfile.mkdtemp()) / "app"
        stats = write_files(text, out, base_dir=base)
        return stats, (grade(out) if stats["parsed"] else None), out

    def test_good_app_scores_five(self):
        stats, res, _ = self.run_app(files_json(GOOD_APP))
        self.assertEqual(res["passed"], 5, res)
        self.assertEqual(stats["files"], ["app.py"])

    def test_missing_comment_route_scores_four_or_less(self):
        _, res, _ = self.run_app(files_json(NO_COMMENTS_APP))
        self.assertLess(res["passed"], 5)
        self.assertEqual(res["failed_step"], "add comment")

    def test_syntax_error_scores_zero(self):
        _, res, _ = self.run_app(files_json("def broken(:\n"))
        self.assertEqual(res["passed"], 0)
        self.assertIsNotNone(res["error"])

    def test_no_files_found(self):
        stats, _, _ = self.run_app("Sure! Here is a description of a blog, but no code.")
        self.assertFalse(stats["parsed"])

    def test_path_escape_is_blocked(self):
        stats, _, _ = self.run_app(md(("../evil.py", "x"), ("/etc/x.py", "x"), ("app.py", GOOD_APP)))
        self.assertEqual(stats["files"], ["app.py"])
        self.assertEqual(len(stats["skipped"]), 2)

    def test_parser_formats(self):
        text = "Intro\n\n**app.py**\n```python\nprint(1)\n```\n\n### File: ./templates/base.html\n```html\n<p>hi</p>\n```\n"
        self.assertEqual(parse_files(text), {"app.py": "print(1)\n", "templates/base.html": "<p>hi</p>\n"})
        self.assertEqual(parse_files("```python\nx = 1\n```"), {"app.py": "x = 1\n"})

    def test_repair_overlays_previous_attempt(self):
        _, res1, first = self.run_app(md(("app.py", NO_COMMENTS_APP), ("templates/keep.html", "<p>keep</p>")))
        self.assertLess(res1["passed"], 5)
        stats, res2, second = self.run_app(md(("app.py", GOOD_APP)), base=first)
        self.assertEqual(res2["passed"], 5, res2)
        self.assertTrue((second / "templates" / "keep.html").exists(), "unchanged files must carry over")


if __name__ == "__main__":
    unittest.main()
