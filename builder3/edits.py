"""Edit-based replies: change an existing file with FIND/REPLACE blocks instead of rewriting all of it.

A reply for an existing file looks like this (any number of blocks, applied in order):

    <<<<<<< FIND
    lines copied exactly from the current file
    =======
    the lines that replace them
    >>>>>>> REPLACE

Why: rewriting a whole file costs as many tokens as the file is long, so a 470-line app.py no longer fit in
the model's context. An edit costs only as much as the change.

The risk is a FIND that doesn't match the file exactly. Each FIND must match exactly once (trailing spaces
are forgiven, nothing looser, so an edit never lands in the wrong place). If any edit for a file fails,
the file is left unchanged and the error shows the closest lines that *are* in the file.
"""
import difflib
import re

EDIT_BLOCK = re.compile(
    r"^<{5,}\s*(?:FIND|SEARCH)\s*\n(?P<find>.*?)^={5,}\s*\n(?P<replace>.*?)^>{5,}\s*REPLACE\s*$",
    re.MULTILINE | re.DOTALL,
)
FIND_START = re.compile(r"^<{5,}\s*(?:FIND|SEARCH)\s*$", re.MULTILINE)  # SEARCH: a common habit from other tools


def parse_edits(text: str) -> tuple[list[tuple[str, str]], str | None]:
    """The (find, replace) pairs in a reply, in order, and an error if a block is broken or cut off."""
    edits = [(m["find"], m["replace"]) for m in EDIT_BLOCK.finditer(text)]
    starts = len(FIND_START.findall(text))
    if starts > len(edits):
        return edits, (f"{starts - len(edits)} of your {starts} edit blocks never reached its `>>>>>>> REPLACE` "
                       f"line (cut off, or the `=======` line is missing).")
    return edits, None


def _lines(s: str) -> list[str]:
    return [l.rstrip() for l in s.split("\n")]


def _find_tolerant(content: str, find: str) -> list[int]:
    """Line numbers (0-based) where `find` matches when trailing spaces are ignored."""
    have, want = _lines(content), _lines(find.rstrip("\n"))
    n = len(want)
    return [i for i in range(len(have) - n + 1) if have[i:i + n] == want]


def _closest(content: str, find: str) -> str:
    """The run of lines in `content` most like `find`, with line numbers, to show the model what's really there."""
    have, want = content.split("\n"), find.rstrip("\n").split("\n")
    n = max(1, len(want))
    best, best_at = 0.0, 0
    target = "\n".join(l.strip() for l in want)
    for i in range(max(1, len(have) - n + 1)):
        score = difflib.SequenceMatcher(None, target, "\n".join(l.strip() for l in have[i:i + n])).ratio()
        if score > best:
            best, best_at = score, i
    if best < 0.4:
        return "Nothing in the file looks like it."
    window = have[best_at:best_at + n]
    shown = "\n".join(f"{best_at + 1 + k:4}| {l}" for k, l in enumerate(window))
    return f"The closest lines in the file are (line numbers added, they are not part of the file):\n{shown}"


def apply_edits(content: str, edits: list[tuple[str, str]], path: str = "the file") -> tuple[str, list[str]]:
    """Apply the edits in order. Returns (new content, errors). If there are any errors, use the original."""
    errors = []
    for n, (find, replace) in enumerate(edits, 1):
        label = f"Edit {n} for `{path}`"
        if not find.strip():
            errors.append(f"{label} has an empty FIND. Copy the lines to change from the current file.")
            continue
        if find.strip() == replace.strip():
            continue  # changes nothing (the build loop fails a try in which no file changed at all)
        count = content.count(find)
        if count == 1:
            content = content.replace(find, replace, 1)
            continue
        if count > 1:
            errors.append(f"{label}: the FIND text appears {count} times in the file. Include more of the "
                          f"surrounding lines so it matches exactly one place.")
            continue
        at = _find_tolerant(content, find)
        if len(at) == 1:  # same lines, only trailing spaces differ
            lines = content.split("\n")
            size = len(_lines(find.rstrip("\n")))
            new = replace[:-1] if replace.endswith("\n") else replace
            lines[at[0]:at[0] + size] = new.split("\n") if new else []
            content = "\n".join(lines)
            continue
        if len(at) > 1:
            errors.append(f"{label}: the FIND text appears {len(at)} times in the file. Include more of the "
                          f"surrounding lines so it matches exactly one place.")
            continue
        first = find.strip("\n").split("\n")[0]
        errors.append(f"{label}: the FIND text isn't in the file. It must be copied exactly from the current "
                      f"file. It starts with:\n    {first}\n{_closest(content, find)}")
    return content, errors
