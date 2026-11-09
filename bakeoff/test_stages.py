"""Checks the multi-stage grader: a correct stage-5 app passes everything; known bugs fail the right check.

Run: bakeoff/.venv/bin/python -m unittest bakeoff/test_stages.py
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_check import GOOD_APP  # noqa: E402  (stage-1 reference app)

REFERENCE = r'''
import sqlite3, markdown
from flask import Flask, request, redirect, session, abort, render_template_string
app = Flask(__name__)
app.secret_key = "dev"

def db():
    c = sqlite3.connect("blog.db"); c.row_factory = sqlite3.Row; return c

with db() as c:
    c.executescript("""
    create table if not exists users(id integer primary key, username unique, password);
    create table if not exists posts(id integer primary key, title, body, author, tags default '');
    create table if not exists comments(id integer primary key, post_id, author, body);
    """)

LAYOUT = "<header>{% if session.user %}Logged in as {{ session.user }} <a href='/logout'>logout</a>{% else %}<a href='/login'>login</a>{% endif %}</header>"

def tag_links(p):
    return " ".join(f"<a href='/tags/{t}'>{t}</a>" for t in p["tags"].split(",") if t)

def post_list(posts):
    return render_template_string(LAYOUT + "{% for p in posts %}<a href='/posts/{{p.id}}'>{{p.title}}</a> by {{p.author}} {{ links(p)|safe }}{% endfor %}", posts=posts, links=tag_links)

@app.get("/")
def home():
    return post_list(db().execute("select * from posts order by id desc").fetchall())

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        with db() as c:
            c.execute("insert into users(username, password) values (?, ?)", (request.form["username"], request.form["password"]))
        session["user"] = request.form["username"]
        return redirect("/")
    return "<form method=post><input name=username><input name=password></form>"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db().execute("select * from users where username=? and password=?", (request.form["username"], request.form["password"])).fetchone()
        if u:
            session["user"] = u["username"]
            return redirect("/")
    return "<form method=post><input name=username><input name=password></form>"

@app.get("/logout")
def logout():
    session.clear(); return redirect("/")

def clean_tags(raw):
    return ",".join(t.strip().lower() for t in raw.split(",") if t.strip())

@app.route("/posts/new", methods=["GET", "POST"])
def new():
    if not session.get("user"):
        return redirect("/login")
    if request.method == "POST":
        with db() as c:
            cur = c.execute("insert into posts(title, body, author, tags) values (?, ?, ?, ?)",
                            (request.form["title"], request.form["body"], session["user"], clean_tags(request.form.get("tags", ""))))
        return redirect(f"/posts/{cur.lastrowid}")
    return "<form method=post></form>"

def get_post(pid):
    p = db().execute("select * from posts where id=?", (pid,)).fetchone()
    if not p: abort(404)
    return p

def own_post(pid):
    p = get_post(pid)
    if session.get("user") != p["author"]: abort(403)
    return p

@app.get("/posts/<int:pid>")
def show(pid):
    p = get_post(pid)
    cs = db().execute("select * from comments where post_id=?", (pid,)).fetchall()
    return render_template_string(LAYOUT + "<h1>{{p.title}}</h1>by {{p.author}} {{ links(p)|safe }}<div>{{ html|safe }}</div>{% for x in cs %}<p>{{x.body}}</p>{% endfor %}",
                                  p=p, cs=cs, html=markdown.markdown(p["body"]), links=tag_links)

@app.route("/posts/<int:pid>/edit", methods=["GET", "POST"])
def edit(pid):
    p = own_post(pid)
    if request.method == "POST":
        with db() as c:
            c.execute("update posts set title=?, body=?, tags=? where id=?", (request.form["title"], request.form["body"], clean_tags(request.form.get("tags", "")), pid))
        return redirect(f"/posts/{pid}")
    return render_template_string("<form method=post><input name=title value='{{p.title}}'></form>", p=p)

@app.post("/posts/<int:pid>/delete")
def delete(pid):
    own_post(pid)
    with db() as c:
        c.execute("delete from comments where post_id=?", (pid,)); c.execute("delete from posts where id=?", (pid,))
    return redirect("/")

@app.post("/posts/<int:pid>/comments")
def comment(pid):
    with db() as c:
        c.execute("insert into comments(post_id, author, body) values (?, ?, ?)", (pid, request.form["author"], request.form["body"]))
    return redirect(f"/posts/{pid}")

@app.get("/tags/<tag>")
def by_tag(tag):
    return post_list([p for p in db().execute("select * from posts").fetchall() if tag in p["tags"].split(",")])

@app.get("/search")
def search():
    q = request.args.get("q", "").lower()
    return post_list([p for p in db().execute("select * from posts").fetchall() if q and (q in p["title"].lower() or q in p["body"].lower())])
'''


def grade(src, stage, requirements="flask\nmarkdown\n"):
    d = Path(tempfile.mkdtemp())
    (d / "app.py").write_text(src)
    if requirements is not None:
        (d / "requirements.txt").write_text(requirements)
    out = subprocess.run([str(HERE / ".venv/bin/python"), str(HERE / "stage_smoke.py"), str(d), str(stage)],
                         capture_output=True, text=True, timeout=60).stdout
    return json.loads(out.strip().splitlines()[-1])


class StageGraderTest(unittest.TestCase):
    def test_reference_passes_every_stage_check(self):
        res = grade(REFERENCE, 5)
        self.assertEqual(res["failed"], [], res["error"])
        self.assertEqual(res["total"], 15)

    def test_stage1_app_passes_stage1(self):
        res = grade(GOOD_APP, 1)
        self.assertEqual(res["failed"], [], res["error"])

    def test_missing_ownership_check_is_caught(self):
        res = grade(REFERENCE.replace('if session.get("user") != p["author"]: abort(403)', "pass"), 3)
        self.assertIn("others can't edit or delete", res["failed"])

    def test_case_sensitive_search_is_caught(self):
        res = grade(REFERENCE.replace('q = request.args.get("q", "").lower()', 'q = request.args.get("q", "")'), 4)
        self.assertEqual(res["failed"], ["search"])

    def test_unrendered_markdown_is_caught(self):
        res = grade(REFERENCE.replace('html=markdown.markdown(p["body"])', 'html=p["body"]'), 5)
        self.assertEqual(res["failed"], ["markdown"])

    def test_missing_requirements_is_caught(self):
        res = grade(REFERENCE, 5, requirements=None)
        self.assertEqual(res["failed"], ["requirements.txt"])

    def test_regression_in_old_feature_is_caught(self):
        res = grade(REFERENCE.replace("@app.post(\"/posts/<int:pid>/comments\")", "@app.post(\"/posts/<int:pid>/comment\")"), 5)
        self.assertIn("comments", res["failed"])

    def test_failed_create_post_skips_dependent_checks(self):
        res = grade(REFERENCE.replace('"insert into posts(title', '"insert into no_such_table(title'), 5)
        self.assertIn("create post", res["failed"])
        self.assertTrue(res["skipped"], "checks that need the post should be skipped")
        self.assertNotIn("create post", res["skipped"])
        self.assertNotIn("KeyError: 'id'", res["error"])
        self.assertIn("later checks were skipped", res["error"])

    def test_error_shows_app_line_not_library_internals(self):
        res = grade(REFERENCE.replace('return redirect(f"/posts/{cur.lastrowid}")', 'return redirect(url_for_missing_id())'), 5)
        self.assertIn('File "app.py"', res["error"])
        self.assertIn("url_for_missing_id", res["error"])
        self.assertNotIn("site-packages", res["error"])

    def test_crash_on_startup(self):
        res = grade("import nope_not_a_module\n", 3)
        self.assertEqual(res["failed"], ["app starts"])


if __name__ == "__main__":
    unittest.main()
