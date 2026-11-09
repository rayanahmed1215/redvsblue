"""Serve a generated app for browsing. Runs with builder/.venv.

Always binds to 127.0.0.1 (this machine only) and forces debug off: Flask's debugger lets anyone who
can reach the page run code, and the generated apps are deliberately not security-reviewed.

Usage: python serve_app.py <app_dir> <port>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checker import load_app  # noqa: E402

if __name__ == "__main__":
    import flask

    real_run = flask.Flask.run
    app = load_app(os.path.abspath(sys.argv[1]))  # stubs app.run while loading
    print(f"Serving on http://127.0.0.1:{sys.argv[2]}  (Ctrl+C to stop)")
    real_run(app, host="127.0.0.1", port=int(sys.argv[2]), debug=False, use_reloader=False)
