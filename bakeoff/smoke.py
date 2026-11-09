"""Runs INSIDE a subprocess, in a generated app's folder. Prints one JSON line.

Usage: python smoke.py <app_dir>
"""
import json
import os
import re
import sys
import traceback

STEPS = ["home page loads", "create post", "view post", "add comment", "comment shows"]


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


def main(app_dir):
    os.chdir(app_dir)
    sys.path.insert(0, app_dir)
    passed, error = 0, None
    try:
        # Run app.py as if started with `python app.py` (so setup code under
        # `if __name__ == "__main__":` runs), but make app.run() a no-op so no server starts.
        import runpy

        import flask

        flask.Flask.run = lambda *a, **k: None
        app = runpy.run_path(os.path.join(app_dir, "app.py"), run_name="__main__")["app"]

        app.testing = True  # raise the real exception instead of returning a bare 500
        client = app.test_client()
        title, body = "Bakeoff Title 7731", "Bakeoff body text 7731"

        r = client.get("/")
        assert r.status_code == 200, f"GET / -> {r.status_code}"
        passed = 1

        r = client.post("/posts/new", data={"title": title, "body": body}, follow_redirects=True)
        assert r.status_code < 400, f"POST /posts/new -> {r.status_code}"
        home = client.get("/").get_data(as_text=True)
        assert title in home, "new post title not on home page"
        ids = re.findall(r"/posts/(\d+)", home)
        assert ids, "no /posts/<id> link on home page"
        post_id = max(int(i) for i in ids)
        passed = 2

        r = client.get(f"/posts/{post_id}")
        page = r.get_data(as_text=True)
        assert r.status_code == 200 and body in page, f"GET /posts/{post_id} -> {r.status_code}, body shown: {body in page}"
        passed = 3

        comment = "Bakeoff comment 7731"
        r = client.post(f"/posts/{post_id}/comments", data={"author": "tester", "body": comment}, follow_redirects=True)
        assert r.status_code < 400, f"POST comment -> {r.status_code}"
        passed = 4

        page = client.get(f"/posts/{post_id}").get_data(as_text=True)
        assert comment in page, "comment not shown on post page"
        passed = 5
    except BaseException:  # noqa: BLE001 - we want any failure, including SystemExit
        error = app_traceback(app_dir)  # last frames = the app's own code
    print(json.dumps({"passed": passed, "failed_step": None if passed == 5 else STEPS[passed], "error": error}))


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]))
