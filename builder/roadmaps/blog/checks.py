"""Checks for the blog roadmap, ported from bakeoff/stage_smoke.py (same 15 checks).

Loaded by builder/checker.py, which calls define(c, app). Checks run in order; each one only runs at
or after its stage, so earlier features keep being re-tested.
"""
import os
import re

REDIRECTS = (301, 302, 303, 307, 308)
T = "Bakeoff Title 7731"
T2 = "Edited Title 7731"
BODY = "Bakeoff body text 7731 zebra7731"
COMMENT = "Bakeoff comment 7731"


def define(c, app):
    alice, bob, anon, alice2 = (app.test_client() for _ in range(4))
    body = BODY + ("\n\n**bold words 7731**" if c.stage >= 5 else "")

    def text(r):
        return r.get_data(as_text=True)

    @c.check("home page loads", 1)
    def _():
        r = anon.get("/")
        assert r.status_code == 200, f"GET / returned {r.status_code}"

    @c.check("register", 2)
    def _():
        for client, user in ((alice, "alice"), (bob, "bob")):
            r = client.post("/register", data={"username": user, "password": f"pw-{user}-1"}, follow_redirects=True)
            assert r.status_code < 400, f"POST /register for {user} returned {r.status_code}"

    @c.check("login and logout", 2)
    def _():
        r = alice2.post("/login", data={"username": "alice", "password": "pw-alice-1"}, follow_redirects=True)
        assert r.status_code < 400, f"POST /login returned {r.status_code}"
        assert "alice" in text(alice2.get("/")), "after logging in, the home page doesn't show the username 'alice'"
        alice2.get("/logout", follow_redirects=True)
        r = alice2.get("/posts/new")
        assert r.status_code in REDIRECTS and "/login" in r.headers.get("Location", ""), \
            f"after GET /logout, GET /posts/new should redirect to /login, got {r.status_code}"

    @c.check("logged-out users can't post", 2)
    def _():
        r = anon.get("/posts/new")
        assert r.status_code in REDIRECTS and "/login" in r.headers.get("Location", ""), \
            f"GET /posts/new while logged out should redirect to /login, got {r.status_code}"
        r = anon.post("/posts/new", data={"title": "Anon post 7731", "body": "x", "tags": "x"})
        assert r.status_code in REDIRECTS, f"POST /posts/new while logged out should redirect to /login, got {r.status_code}"
        assert "Anon post 7731" not in text(anon.get("/")), "a logged-out user was able to create a post"

    @c.check("create post", 1)
    def _():
        data = {"title": T, "body": body}
        if c.stage >= 4:
            data["tags"] = " Python, Flask "
        r = alice.post("/posts/new", data=data, follow_redirects=True)
        assert r.status_code < 400, f"POST /posts/new returned {r.status_code}"
        home = text(alice.get("/"))
        assert T in home, "the new post's title doesn't appear on the home page"
        ids = re.findall(r"/posts/(\d+)", home)
        assert ids, "no link of the form /posts/<id> on the home page"
        c.state["post_id"] = max(int(i) for i in ids)

    @c.check("view post", 1, needs=("post_id",))
    def _():
        r = anon.get(f"/posts/{c.state["post_id"]}")
        assert r.status_code == 200, f"GET /posts/<id> returned {r.status_code}"
        assert T in text(r) and "Bakeoff body text 7731" in text(r), "the post page doesn't show the title and body"

    @c.check("author shown", 2, needs=("post_id",))
    def _():
        assert "alice" in text(anon.get(f"/posts/{c.state["post_id"]}")), "the post page doesn't show the author's username"
        assert "alice" in text(anon.get("/")), "the home page doesn't show the author's username"

    @c.check("comments", 1, needs=("post_id",))
    def _():
        r = anon.post(f"/posts/{c.state["post_id"]}/comments", data={"author": "tester", "body": COMMENT}, follow_redirects=True)
        assert r.status_code < 400, f"POST /posts/<id>/comments returned {r.status_code}"
        assert COMMENT in text(anon.get(f"/posts/{c.state["post_id"]}")), "the comment doesn't appear on the post page"

    @c.check("tags", 4, needs=("post_id",))
    def _():
        page = text(anon.get(f"/posts/{c.state["post_id"]}"))
        assert "/tags/python" in page, "the post page doesn't link to /tags/python (tags should be stored lowercase, trimmed)"
        for tag in ("python", "flask"):
            r = anon.get(f"/tags/{tag}")
            assert r.status_code == 200 and T in text(r), f"GET /tags/{tag} doesn't list the post"

    @c.check("search", 4, needs=("post_id",))
    def _():
        r = anon.get("/search?q=ZEBRA7731")
        assert r.status_code == 200 and T in text(r), "searching for a word in the body (different case) doesn't find the post"
        assert T not in text(anon.get("/search?q=nomatch99999")), "searching for a word that isn't in any post still lists the post"

    @c.check("markdown", 5, needs=("post_id",))
    def _():
        page = text(anon.get(f"/posts/{c.state["post_id"]}"))
        assert "<strong>bold words 7731</strong>" in page, "**bold words 7731** in the body isn't rendered as <strong>bold words 7731</strong>"

    @c.check("requirements.txt", 5)
    def _():
        assert os.path.exists("requirements.txt"), "requirements.txt is missing"
        assert re.search(r"(?im)^\s*markdown\b", open("requirements.txt").read()), "requirements.txt doesn't list markdown"

    @c.check("others can't edit or delete", 3, needs=("post_id",))
    def _():
        pid = c.state["post_id"]
        for who, client in (("another user", bob), ("a logged-out visitor", anon)):
            r = client.post(f"/posts/{pid}/edit", data={"title": "Hacked 7731", "body": "x", "tags": "x"})
            assert r.status_code == 403, f"POST /posts/<id>/edit by {who} should return 403, got {r.status_code}"
            r = client.post(f"/posts/{pid}/delete")
            assert r.status_code == 403, f"POST /posts/<id>/delete by {who} should return 403, got {r.status_code}"
        page = text(anon.get(f"/posts/{pid}"))
        assert T in page and "Hacked 7731" not in page, "the post was changed or deleted by someone who isn't its author"

    @c.check("author can edit", 3, needs=("post_id",))
    def _():
        pid = c.state["post_id"]
        r = alice.get(f"/posts/{pid}/edit")
        assert r.status_code == 200 and T in text(r), "GET /posts/<id>/edit isn't pre-filled with the current title"
        data = {"title": T2, "body": body}
        if c.stage >= 4:
            data["tags"] = "python, flask"
        r = alice.post(f"/posts/{pid}/edit", data=data, follow_redirects=True)
        assert r.status_code < 400, f"POST /posts/<id>/edit returned {r.status_code}"
        assert T2 in text(anon.get(f"/posts/{pid}")), "the edited title doesn't appear on the post page"

    @c.check("author can delete", 3, needs=("post_id",))
    def _():
        pid = c.state["post_id"]
        r = alice.post(f"/posts/{pid}/delete", follow_redirects=True)
        assert r.status_code < 400, f"POST /posts/<id>/delete returned {r.status_code}"
        assert T2 not in text(anon.get("/")), "the deleted post still appears on the home page"
        assert anon.get(f"/posts/{pid}").status_code in (404, *REDIRECTS), "the deleted post's page still loads"
