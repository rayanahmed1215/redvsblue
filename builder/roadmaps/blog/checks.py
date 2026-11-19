"""Checks for the blog roadmap, ported from bakeoff/stage_smoke.py (same 15 checks).

Loaded by builder/checker.py, which calls define(c, app). Checks run in order; each one only runs at
or after its stage, so earlier features keep being re-tested.
"""
import io
import os
import re

REDIRECTS = (301, 302, 303, 307, 308)
T = "Bakeoff Title 7731"
T2 = "Edited Title 7731"
BODY = "Bakeoff body text 7731 zebra7731"
COMMENT = "Bakeoff comment 7731"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24  # enough to look like an image


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
        assert "&lt;strong&gt;bold words 7731" not in page, \
            "the Markdown HTML is shown as escaped text (&lt;strong&gt;...) on the post page: Jinja auto-escapes " \
            "the filter's output, so return markupsafe.Markup(...) from the filter or use |safe in the template"
        assert "<strong>bold words 7731</strong>" in page, "**bold words 7731** in the body isn't rendered as <strong>bold words 7731</strong>"

    @c.check("requirements.txt", 5)
    def _():
        assert os.path.exists("requirements.txt"), "requirements.txt is missing"
        assert re.search(r"(?im)^\s*mdlite\b", open("requirements.txt").read()), "requirements.txt doesn't list mdlite"

    # ---- feature 6: avatars -------------------------------------------------------------
    @c.check("avatar upload", 6, needs=("post_id",))
    def _():
        r = anon.get("/settings/avatar")
        assert r.status_code in REDIRECTS and "/login" in r.headers.get("Location", ""), \
            f"GET /settings/avatar while logged out should redirect to /login, got {r.status_code}"
        r = alice.post("/settings/avatar", data={"avatar": (io.BytesIO(PNG), "me.png")},
                       content_type="multipart/form-data", follow_redirects=True)
        assert r.status_code < 400, f"POST /settings/avatar with a PNG returned {r.status_code}"
        page = text(anon.get(f"/posts/{c.state['post_id']}"))
        m = re.search(r"""<img[^>]+src=["'](/static/uploads/[^"']+)["']""", page)
        assert m, "the post page doesn't show the author's avatar as <img src=\"/static/uploads/...\">"
        r = anon.get(m.group(1))
        assert r.status_code == 200 and r.data == PNG, f"the avatar URL {m.group(1)} doesn't serve the uploaded file"

    @c.check("avatar rejects non-images", 6)
    def _():
        r = alice.post("/settings/avatar", data={"avatar": (io.BytesIO(b"hello"), "notes.txt")},
                       content_type="multipart/form-data")
        assert r.status_code == 400, f"uploading a .txt file should return 400, got {r.status_code}"

    # ---- feature 7: pagination ------------------------------------------------------------
    @c.check("pagination", 7, needs=("post_id",))
    def _():
        for i in range(1, 10):  # 10 posts in total: two full pages of 5
            data = {"title": f"Page post {i} 7731", "body": "filler", "tags": ""}
            r = alice.post("/posts/new", data=data, follow_redirects=True)
            assert r.status_code < 400, f"creating extra post {i} returned {r.status_code}"
        first = text(anon.get("/"))
        if "Page post 9 7731" not in first and T in first:
            raise AssertionError(
                "page 1 shows the oldest posts instead of the newest: these posts were all created in the same "
                "second, and created_at only stores whole seconds, so sorting by created_at alone ties. "
                "Sort by created_at DESC, id DESC (or just id DESC)")
        assert "Page post 9 7731" in first, "the newest post isn't on the first page"
        assert T not in first, "page 1 should show only the 5 newest posts, but it also shows the oldest one"
        assert "page=2" in first, (
            "page 1 doesn't link to ?page=2, although 10 posts exist (two pages of 5), so the app thinks there is "
            "only one page. If you use pager.paginate(), pass it the full list of posts: it does the slicing "
            "itself, so don't also apply LIMIT/OFFSET in SQL")
        second = text(anon.get("/?page=2"))
        assert T in second, "page 2 doesn't show the oldest post"
        assert "page=1" in second or 'href="/"' in second, "page 2 doesn't link back to page 1"

    # ---- feature 8: profiles --------------------------------------------------------------
    @c.check("profiles", 8, needs=("post_id",))
    def _():
        r = anon.get("/settings/profile")
        assert r.status_code in REDIRECTS and "/login" in r.headers.get("Location", ""), \
            f"GET /settings/profile while logged out should redirect to /login, got {r.status_code}"
        r = alice.post("/settings/profile", data={"bio": "Hi, I'm **bio bold 7731**"}, follow_redirects=True)
        assert r.status_code < 400, f"POST /settings/profile returned {r.status_code}"
        r = anon.get("/users/alice")
        assert r.status_code == 200, f"GET /users/alice returned {r.status_code}"
        assert "&lt;strong&gt;bio bold 7731" not in text(r), \
            "the bio's Markdown HTML is shown as escaped text (&lt;strong&gt;...) on /users/alice: Jinja auto-escapes " \
            "the filter's output, so return markupsafe.Markup(...) from the filter or use |safe in the template"
        assert "<strong>bio bold 7731</strong>" in text(r), "the bio isn't rendered as Markdown on /users/alice"
        assert f"/posts/{c.state['post_id']}" in text(r), "/users/alice doesn't link to alice's post"
        assert anon.get("/users/nobody7731").status_code == 404, "GET /users/<unknown> should return 404"
        assert "/users/alice" in text(anon.get(f"/posts/{c.state['post_id']}")), "the post page doesn't link to the author's profile"

    # ---- feature 9: admin -----------------------------------------------------------------
    @c.check("admin panel", 9)
    def _():
        for who, client in (("bob (not admin)", bob), ("a logged-out visitor", anon)):
            assert client.get("/admin").status_code == 403, f"GET /admin by {who} should return 403"
        r = alice.get("/admin")
        assert r.status_code == 200, (
            f"GET /admin as alice returned {r.status_code}, but alice registered first, so she is the admin. "
            f"(bob registered after her, so a check like 'the number of users is 1' is wrong: store or look up "
            f"who registered first, e.g. the user with the lowest id)")
        assert "bob" in text(r), "GET /admin as the first user (admin) doesn't list the users (bob is missing)"
        r = bob.post("/posts/new", data={"title": "Bob post 7731", "body": "by bob", "tags": ""}, follow_redirects=True)
        assert r.status_code < 400, f"bob creating a post returned {r.status_code}"
        ids = [int(i) for i in re.findall(r"/posts/(\d+)", text(alice.get("/admin")))]
        assert ids, "GET /admin doesn't link to the posts"
        bob_post = max(ids)
        assert bob.post(f"/admin/posts/{bob_post}/delete").status_code == 403, \
            "POST /admin/posts/<id>/delete by a non-admin should return 403"
        r = alice.post(f"/admin/posts/{bob_post}/delete", follow_redirects=True)
        assert r.status_code < 400, f"admin POST /admin/posts/<id>/delete returned {r.status_code}"
        assert "Bob post 7731" not in text(anon.get("/")), "the admin deleted bob's post but it still appears on /"

    # ---- feature 10: messages --------------------------------------------------------------
    @c.check("messages", 10)
    def _():
        r = anon.get("/messages")
        assert r.status_code in REDIRECTS and "/login" in r.headers.get("Location", ""), \
            f"GET /messages while logged out should redirect to /login, got {r.status_code}"
        r = alice.post("/messages", data={"to": "bob", "body": "Secret message 7731"}, follow_redirects=True)
        assert r.status_code < 400, f"POST /messages returned {r.status_code}"
        inbox = text(bob.get("/messages"))
        assert "Secret message 7731" in inbox or "/messages/" in inbox, "bob's inbox doesn't show alice's message"
        ids = re.findall(r"/messages/(\d+)", inbox)
        assert ids, "bob's inbox doesn't link to /messages/<id>"
        mid = max(int(i) for i in ids)
        r = bob.get(f"/messages/{mid}")
        assert r.status_code == 200 and "Secret message 7731" in text(r), "bob can't read the message alice sent him"
        carol = app.test_client()
        carol.post("/register", data={"username": "carol", "password": "pw-carol-1"}, follow_redirects=True)
        assert carol.get(f"/messages/{mid}").status_code == 403, "a third user could read a message between alice and bob"
        r = alice.post("/messages", data={"to": "nobody7731", "body": "x"})
        assert r.status_code == 400, f"sending to a user that doesn't exist should return 400, got {r.status_code}"

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
