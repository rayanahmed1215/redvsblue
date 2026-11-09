"""Hand-written reference app implementing all 10 blog features. Used to prove the checks are fair.

It's written for the tests only, as one file with inline templates. It works with mdlite 1.x and 2.x.
"""
import sqlite3

import mdlite
import pager
import uploadkit
from flask import Flask, abort, redirect, render_template_string, request, session

app = Flask(__name__)
app.secret_key = "dev"
UPLOADS = "static/uploads"
md = getattr(mdlite, "to_html", None) or mdlite.render


def db():
    c = sqlite3.connect("blog.db")
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.executescript("""
        create table if not exists users(id integer primary key, username unique, password, avatar, bio default '');
        create table if not exists posts(id integer primary key, title, body, author, tags default '');
        create table if not exists comments(id integer primary key, post_id, author, body);
        create table if not exists messages(id integer primary key, sender, recipient, body);
        """)


init_db()

LAYOUT = """<header>{% if session.user %}Logged in as {{ session.user }} <a href='/logout'>logout</a>
<a href='/messages'>Messages</a>{% if is_admin() %} <a href='/admin'>Admin</a>{% endif %}
{% else %}<a href='/login'>login</a> <a href='/register'>register</a>{% endif %}</header>"""


@app.context_processor
def helpers():
    return {"is_admin": is_admin}


def current_user():
    return session.get("user")


def is_admin():
    first = db().execute("select username from users order by id limit 1").fetchone()
    return bool(first and current_user() == first["username"])


def login_required():
    if not current_user():
        abort(redirect("/login"))


def page(body, **ctx):
    return render_template_string(LAYOUT + body, **ctx)


def tag_links(p):
    return " ".join(f"<a href='/tags/{t}'>{t}</a>" for t in p["tags"].split(",") if t)


LIST = "{% for p in posts %}<a href='/posts/{{p.id}}'>{{p.title}}</a> by <a href='/users/{{p.author}}'>{{p.author}}</a> {{ links(p)|safe }}<br>{% endfor %}"


@app.get("/")
def home():
    posts = db().execute("select * from posts order by id desc").fetchall()
    p = pager.paginate(posts, page=request.args.get("page", 1, type=int), per_page=5)
    nav = ""
    if p.has_prev:
        nav += f"<a href='/?page={p.page - 1}'>Previous</a> "
    if p.has_next:
        nav += f"<a href='/?page={p.page + 1}'>Next</a>"
    return page(LIST + "{{ nav|safe }}", posts=p.items, links=tag_links, nav=nav)


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
        u = db().execute("select * from users where username=? and password=?",
                         (request.form["username"], request.form["password"])).fetchone()
        if u:
            session["user"] = u["username"]
            return redirect("/")
    return "<form method=post><input name=username><input name=password></form>"


@app.get("/logout")
def logout():
    session.clear()
    return redirect("/")


def clean_tags(raw):
    return ",".join(t.strip().lower() for t in raw.split(",") if t.strip())


@app.route("/posts/new", methods=["GET", "POST"])
def new():
    login_required()
    if request.method == "POST":
        with db() as c:
            cur = c.execute("insert into posts(title, body, author, tags) values (?, ?, ?, ?)",
                            (request.form["title"], request.form["body"], current_user(), clean_tags(request.form.get("tags", ""))))
        return redirect(f"/posts/{cur.lastrowid}")
    return "<form method=post></form>"


def get_post(pid):
    p = db().execute("select * from posts where id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    return p


def own_post(pid):
    p = get_post(pid)
    if current_user() != p["author"]:
        abort(403)
    return p


@app.get("/posts/<int:pid>")
def show(pid):
    p = get_post(pid)
    c = db()
    cs = c.execute("select * from comments where post_id=?", (pid,)).fetchall()
    author = c.execute("select * from users where username=?", (p["author"],)).fetchone()
    avatar = f"<img src='/static/uploads/{author['avatar']}' alt=''>" if author and author["avatar"] else ""
    return page("<h1>{{p.title}}</h1>{{ avatar|safe }} by <a href='/users/{{p.author}}'>{{p.author}}</a> {{ links(p)|safe }}"
                "<div>{{ html|safe }}</div>{% for x in cs %}<p>{{x.body}}</p>{% endfor %}",
                p=p, cs=cs, html=md(p["body"]), links=tag_links, avatar=avatar.replace("'", '"'))


@app.route("/posts/<int:pid>/edit", methods=["GET", "POST"])
def edit(pid):
    p = own_post(pid)
    if request.method == "POST":
        with db() as c:
            c.execute("update posts set title=?, body=?, tags=? where id=?",
                      (request.form["title"], request.form["body"], clean_tags(request.form.get("tags", "")), pid))
        return redirect(f"/posts/{pid}")
    return render_template_string("<form method=post><input name=title value='{{p.title}}'></form>", p=p)


def delete_post(pid):
    with db() as c:
        c.execute("delete from comments where post_id=?", (pid,))
        c.execute("delete from posts where id=?", (pid,))


@app.post("/posts/<int:pid>/delete")
def delete(pid):
    own_post(pid)
    delete_post(pid)
    return redirect("/")


@app.post("/posts/<int:pid>/comments")
def comment(pid):
    with db() as c:
        c.execute("insert into comments(post_id, author, body) values (?, ?, ?)", (pid, request.form["author"], request.form["body"]))
    return redirect(f"/posts/{pid}")


@app.get("/tags/<tag>")
def by_tag(tag):
    posts = [p for p in db().execute("select * from posts").fetchall() if tag in p["tags"].split(",")]
    return page(LIST, posts=posts, links=tag_links)


@app.get("/search")
def search():
    q = request.args.get("q", "").lower()
    posts = [p for p in db().execute("select * from posts").fetchall() if q and (q in p["title"].lower() or q in p["body"].lower())]
    return page(LIST, posts=posts, links=tag_links)


@app.route("/settings/avatar", methods=["GET", "POST"])
def avatar():
    login_required()
    if request.method == "POST":
        try:
            name = uploadkit.save_upload(request.files.get("avatar"), UPLOADS)
        except uploadkit.UploadError as e:
            return f"Upload failed: {e}", 400
        with db() as c:
            c.execute("update users set avatar=? where username=?", (name, current_user()))
        return redirect("/")
    return "<form method=post enctype=multipart/form-data><input type=file name=avatar></form>"


@app.get("/users/<username>")
def profile(username):
    c = db()
    u = c.execute("select * from users where username=?", (username,)).fetchone()
    if not u:
        abort(404)
    posts = c.execute("select * from posts where author=? order by id desc", (username,)).fetchall()
    return page("<h1>{{u.username}}</h1><div>{{ bio|safe }}</div>" + LIST, u=u, bio=md(u["bio"] or ""), posts=posts, links=tag_links)


@app.route("/settings/profile", methods=["GET", "POST"])
def settings_profile():
    login_required()
    if request.method == "POST":
        with db() as c:
            c.execute("update users set bio=? where username=?", (request.form["bio"], current_user()))
        return redirect(f"/users/{current_user()}")
    return "<form method=post><textarea name=bio></textarea></form>"


@app.get("/admin")
def admin():
    if not is_admin():
        abort(403)
    c = db()
    return page("{% for u in users %}{{u.username}} {% endfor %}{% for p in posts %}<a href='/posts/{{p.id}}'>{{p.title}}</a>"
                "<form method=post action='/admin/posts/{{p.id}}/delete'><button>Delete</button></form>{% endfor %}",
                users=c.execute("select * from users").fetchall(), posts=c.execute("select * from posts").fetchall())


@app.post("/admin/posts/<int:pid>/delete")
def admin_delete(pid):
    if not is_admin():
        abort(403)
    delete_post(pid)
    return redirect("/admin")


@app.route("/messages", methods=["GET", "POST"])
def messages():
    login_required()
    c = db()
    if request.method == "POST":
        if not c.execute("select 1 from users where username=?", (request.form["to"],)).fetchone():
            return "No such user", 400
        with c:
            c.execute("insert into messages(sender, recipient, body) values (?, ?, ?)",
                      (current_user(), request.form["to"], request.form["body"]))
        return redirect("/messages")
    inbox = c.execute("select * from messages where recipient=?", (current_user(),)).fetchall()
    return page("{% for m in inbox %}<a href='/messages/{{m.id}}'>from {{m.sender}}</a>{% endfor %}"
                "<form method=post><input name=to><textarea name=body></textarea></form>", inbox=inbox)


@app.get("/messages/<int:mid>")
def message(mid):
    login_required()
    m = db().execute("select * from messages where id=?", (mid,)).fetchone()
    if not m:
        abort(404)
    if current_user() not in (m["sender"], m["recipient"]):
        abort(403)
    return page("<p>From {{m.sender}}: {{m.body}}</p>", m=m)
