"""Cumulative checks for the multi-stage bake-off. Runs INSIDE a subprocess, in an app folder.

Usage: python stage_smoke.py <app_dir> <stage>
Prints one JSON line: {"stage", "passed", "total", "failed": [...], "failed_step", "error"}.
Every check up to <stage> runs, so features from earlier stages are re-tested (regressions count).
"""
import json
import os
import re
import runpy
import sys
import traceback

REDIRECTS = (301, 302, 303, 307, 308)
T = "Bakeoff Title 7731"
T2 = "Edited Title 7731"
BODY = "Bakeoff body text 7731 zebra7731"
COMMENT = "Bakeoff comment 7731"


def app_traceback(app_dir):
    """The current exception, showing only stack frames from the app's own files (app.py and templates).

    "Last N frames" can hide the app entirely when the error is raised deep inside Flask or Jinja.
    """
    etype, evalue, tb = sys.exc_info()
    frames = [f for f in traceback.extract_tb(tb) if os.path.abspath(f.filename).startswith(app_dir)]
    lines = ["Traceback (only frames from your app's files):\n"]
    lines += traceback.format_list(frames) or ["  (no frames in your files; error raised inside a library)\n"]
    lines += traceback.format_exception_only(etype, evalue)
    return "".join(lines).replace(app_dir + os.sep, "")[-1500:]  # show paths as app.py, templates/x.html


def main(app_dir, stage):
    os.chdir(app_dir)
    sys.path.insert(0, app_dir)
    results = []  # (name, ok, error, skipped)

    try:
        import flask

        flask.Flask.run = lambda *a, **k: None  # run app.py as __main__ without starting a server
        app = runpy.run_path(os.path.join(app_dir, "app.py"), run_name="__main__")["app"]
        app.testing = True  # raise real exceptions instead of bare 500s
    except BaseException:  # noqa: BLE001
        err = app_traceback(app_dir)
        print(json.dumps({"stage": stage, "passed": 0, "total": 1, "failed": ["app starts"],
                          "failed_step": "app starts", "error": err}))
        return

    alice, bob, anon, alice2 = (app.test_client() for _ in range(4))
    state = {}
    body = BODY + ("\n\n**bold words 7731**" if stage >= 5 else "")

    def check(name, min_stage, needs_post=False):
        def wrap(fn):
            if stage < min_stage:
                return
            if needs_post and "id" not in state:
                # Can't run without the post from 'create post'; skip rather than crash with KeyError noise.
                results.append((name, False, None, True))
                return
            try:
                fn()
                results.append((name, True, None, False))
            except AssertionError as e:
                results.append((name, False, f"Check '{name}' failed: {e}", False))
            except BaseException:  # noqa: BLE001
                results.append((name, False, f"Check '{name}' crashed:\n" + app_traceback(app_dir), False))
        return wrap

    def text(r):
        return r.get_data(as_text=True)

    @check("home page loads", 1)
    def _():
        r = anon.get("/")
        assert r.status_code == 200, f"GET / returned {r.status_code}"

    @check("register", 2)
    def _():
        for client, user in ((alice, "alice"), (bob, "bob")):
            r = client.post("/register", data={"username": user, "password": f"pw-{user}-1"}, follow_redirects=True)
            assert r.status_code < 400, f"POST /register for {user} returned {r.status_code}"

    @check("login and logout", 2)
    def _():
        r = alice2.post("/login", data={"username": "alice", "password": "pw-alice-1"}, follow_redirects=True)
        assert r.status_code < 400, f"POST /login returned {r.status_code}"
        assert "alice" in text(alice2.get("/")), "after logging in, the home page doesn't show the username 'alice'"
        alice2.get("/logout", follow_redirects=True)
        r = alice2.get("/posts/new")
        assert r.status_code in REDIRECTS and "/login" in r.headers.get("Location", ""), \
            f"after GET /logout, GET /posts/new should redirect to /login, got {r.status_code}"

    @check("logged-out users can't post", 2)
    def _():
        r = anon.get("/posts/new")
        assert r.status_code in REDIRECTS and "/login" in r.headers.get("Location", ""), \
            f"GET /posts/new while logged out should redirect to /login, got {r.status_code}"
        r = anon.post("/posts/new", data={"title": "Anon post 7731", "body": "x", "tags": "x"})
        assert r.status_code in REDIRECTS, f"POST /posts/new while logged out should redirect to /login, got {r.status_code}"
        assert "Anon post 7731" not in text(anon.get("/")), "a logged-out user was able to create a post"

    @check("create post", 1)
    def _():
        data = {"title": T, "body": body}
        if stage >= 4:
            data["tags"] = " Python, Flask "
        r = alice.post("/posts/new", data=data, follow_redirects=True)
        assert r.status_code < 400, f"POST /posts/new returned {r.status_code}"
        home = text(alice.get("/"))
        assert T in home, "the new post's title doesn't appear on the home page"
        ids = re.findall(r"/posts/(\d+)", home)
        assert ids, "no link of the form /posts/<id> on the home page"
        state["id"] = max(int(i) for i in ids)

    @check("view post", 1, needs_post=True)
    def _():
        r = anon.get(f"/posts/{state['id']}")
        assert r.status_code == 200, f"GET /posts/<id> returned {r.status_code}"
        assert T in text(r) and "Bakeoff body text 7731" in text(r), "the post page doesn't show the title and body"

    @check("author shown", 2, needs_post=True)
    def _():
        assert "alice" in text(anon.get(f"/posts/{state['id']}")), "the post page doesn't show the author's username"
        assert "alice" in text(anon.get("/")), "the home page doesn't show the author's username"

    @check("comments", 1, needs_post=True)
    def _():
        r = anon.post(f"/posts/{state['id']}/comments", data={"author": "tester", "body": COMMENT}, follow_redirects=True)
        assert r.status_code < 400, f"POST /posts/<id>/comments returned {r.status_code}"
        assert COMMENT in text(anon.get(f"/posts/{state['id']}")), "the comment doesn't appear on the post page"

    @check("tags", 4, needs_post=True)
    def _():
        page = text(anon.get(f"/posts/{state['id']}"))
        assert "/tags/python" in page, "the post page doesn't link to /tags/python (tags should be stored lowercase, trimmed)"
        for tag in ("python", "flask"):
            r = anon.get(f"/tags/{tag}")
            assert r.status_code == 200 and T in text(r), f"GET /tags/{tag} doesn't list the post"

    @check("search", 4, needs_post=True)
    def _():
        r = anon.get("/search?q=ZEBRA7731")
        assert r.status_code == 200 and T in text(r), "searching for a word in the body (different case) doesn't find the post"
        assert T not in text(anon.get("/search?q=nomatch99999")), "searching for a word that isn't in any post still lists the post"

    @check("markdown", 5, needs_post=True)
    def _():
        page = text(anon.get(f"/posts/{state['id']}"))
        assert "<strong>bold words 7731</strong>" in page, "**bold words 7731** in the body isn't rendered as <strong>bold words 7731</strong>"

    @check("requirements.txt", 5)
    def _():
        assert os.path.exists("requirements.txt"), "requirements.txt is missing"
        assert re.search(r"(?im)^\s*markdown\b", open("requirements.txt").read()), "requirements.txt doesn't list markdown"

    @check("others can't edit or delete", 3, needs_post=True)
    def _():
        pid = state["id"]
        for who, client in (("another user", bob), ("a logged-out visitor", anon)):
            r = client.post(f"/posts/{pid}/edit", data={"title": "Hacked 7731", "body": "x", "tags": "x"})
            assert r.status_code == 403, f"POST /posts/<id>/edit by {who} should return 403, got {r.status_code}"
            r = client.post(f"/posts/{pid}/delete")
            assert r.status_code == 403, f"POST /posts/<id>/delete by {who} should return 403, got {r.status_code}"
        page = text(anon.get(f"/posts/{pid}"))
        assert T in page and "Hacked 7731" not in page, "the post was changed or deleted by someone who isn't its author"

    @check("author can edit", 3, needs_post=True)
    def _():
        pid = state["id"]
        r = alice.get(f"/posts/{pid}/edit")
        assert r.status_code == 200 and T in text(r), "GET /posts/<id>/edit isn't pre-filled with the current title"
        data = {"title": T2, "body": body}
        if stage >= 4:
            data["tags"] = "python, flask"
        r = alice.post(f"/posts/{pid}/edit", data=data, follow_redirects=True)
        assert r.status_code < 400, f"POST /posts/<id>/edit returned {r.status_code}"
        assert T2 in text(anon.get(f"/posts/{pid}")), "the edited title doesn't appear on the post page"

    @check("author can delete", 3, needs_post=True)
    def _():
        pid = state["id"]
        r = alice.post(f"/posts/{pid}/delete", follow_redirects=True)
        assert r.status_code < 400, f"POST /posts/<id>/delete returned {r.status_code}"
        assert T2 not in text(anon.get("/")), "the deleted post still appears on the home page"
        assert anon.get(f"/posts/{pid}").status_code in (404, *REDIRECTS), "the deleted post's page still loads"

    failed = [(n, e) for n, ok, e, _ in results if not ok]
    skipped = [n for n, _, _, sk in results if sk]
    real = [e for n, e in failed if n not in skipped]
    error = "\n\n".join(real[:3])[-2500:] if real else None
    if error and skipped:
        error += f"\n\n({len(skipped)} later checks were skipped because 'create post' failed.)"
    print(json.dumps({
        "stage": stage, "passed": len(results) - len(failed), "total": len(results),
        "failed": [n for n, _ in failed], "skipped": skipped,
        "failed_step": failed[0][0] if failed else None,
        "error": error,
    }))


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]), int(sys.argv[2]))
