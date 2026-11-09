"""Homemade library versions (ecosystem/) for a site: what's published, what the site pins, and installing it.

Each site's libraries live in sites/<name>/.builder/libs/ and are put on PYTHONPATH when its checks run.
requirements.txt may only name Flask (provided by builder/.venv) and homemade libraries that have been
published as of the current tick. Anything else is rejected and reported to the model; model-chosen
packages are never installed.
"""
import re
import shutil

from .config import ROOT
from .items import WorkItem

ECOSYSTEM = ROOT / "ecosystem"
PROVIDED = {"flask", "werkzeug", "jinja2", "markupsafe", "itsdangerous", "click", "blinker"}  # from builder/.venv
REQ_LINE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*(?:(==|>=|~=)\s*([0-9][0-9.]*))?\s*(?:#.*)?$")


def vkey(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


def libraries() -> list[str]:
    return sorted(p.name for p in ECOSYSTEM.iterdir() if (p / "CHANGELOG.md").exists())


def all_versions(lib: str) -> list[str]:
    return sorted((p.name for p in (ECOSYSTEM / lib).iterdir() if p.is_dir() and p.name[0].isdigit()), key=vkey)


def changelog(lib: str, version: str) -> str:
    """The changelog section for one version (what was public when it was released)."""
    text = (ECOSYSTEM / lib / "CHANGELOG.md").read_text()
    m = re.search(rf"^## {re.escape(version)}\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else "(no changelog entry)"


def readme(lib: str, version: str) -> str:
    return (ECOSYSTEM / lib / version / "README.md").read_text().strip()


def resolve(requirements: str | None, published: dict) -> tuple[dict, list[str]]:
    """Turn requirements.txt into {lib: version}. Returns (deps, errors)."""
    deps, errors = {}, []
    for raw in (requirements or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = REQ_LINE.match(line)
        if not m:
            errors.append(f"requirements.txt: can't understand the line {line!r}. Use `name` or `name==version`.")
            continue
        name, op, ver = m.group(1).lower().replace("_", "-"), m.group(2), m.group(3)
        if name in PROVIDED:
            continue
        if name not in libraries():
            errors.append(f"requirements.txt: the package {name!r} isn't available. You can only use Flask, the "
                          f"Python standard library and these libraries: {available_text(published)}.")
            continue
        versions = published.get(name, [])
        if not versions:
            errors.append(f"requirements.txt: {name} hasn't been released yet.")
        elif op == "==":
            if ver not in versions:
                errors.append(f"requirements.txt: {name}=={ver} doesn't exist. Released versions: {', '.join(versions)}.")
            else:
                deps[name] = ver
        else:
            ok = [v for v in versions if not ver or vkey(v) >= vkey(ver)]
            if not ok:
                errors.append(f"requirements.txt: no released {name} version matches {line!r}. Released: {', '.join(versions)}.")
            else:
                deps[name] = max(ok, key=vkey)
    return deps, errors


def available_text(published: dict) -> str:
    return ", ".join(f"{lib} ({', '.join(vs)})" for lib, vs in sorted(published.items()) if vs) or "none yet"


def install(libs_dir, deps: dict):
    """Make libs_dir contain exactly the given library versions."""
    if libs_dir.exists():
        shutil.rmtree(libs_dir)
    libs_dir.mkdir(parents=True)
    for lib, version in deps.items():
        shutil.copy(ECOSYSTEM / lib / version / f"{lib}.py", libs_dir / f"{lib}.py")


def docs_for_prompt(published: dict, pinned: dict) -> str:
    """Docs for each published library: the pinned version if the site uses it, otherwise the newest."""
    if not any(published.values()):
        return ""
    parts = ["Available libraries (besides Flask and the standard library). To use one, add it to "
             "requirements.txt as `name==version`:"]
    for lib, versions in sorted(published.items()):
        if versions:
            v = pinned.get(lib) or max(versions, key=vkey)
            parts.append(readme(lib, v))
    return "\n\n".join(parts)


def dep_update_item(lib: str, version: str, current: str, tick: int) -> WorkItem:
    text = (f"{lib} {version} has been released (the app currently uses {lib} {current}).\n\n"
            f"Changelog for {version}:\n{changelog(lib, version)}\n\n"
            f"Upgrade the app to {lib}=={version}: change requirements.txt and update any code the new version "
            f"requires, keeping every feature working.\n\nDocumentation for {lib} {version}:\n\n{readme(lib, version)}")
    return WorkItem("dep_update", f"dep-{lib}-{version}", f"Upgrade {lib} to {version}", text, tick,
                    extra={"lib": lib, "version": version, "from": current})
