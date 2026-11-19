"""The prompt for changing an existing file with edits. New files still use builder2's whole-file prompt."""
from builder2.plan import _base

EDIT_FORMAT = """Reply with edits to `{path}`, not the whole file. Each edit is one block like this:

<<<<<<< FIND
lines copied exactly from the current `{path}`
=======
the new lines that replace them
>>>>>>> REPLACE

Rules:
- FIND must be copied character for character from the current `{path}` shown above, and must match only one
  place in it. Use 2 to 8 whole lines: enough to be unique, no more.
- To add new code, FIND a few existing lines next to where it goes, and repeat those lines in the replacement
  together with the new code.
- To delete code, leave the replacement empty.
- Edits are applied in order, top to bottom. Don't put code fences around the blocks.
- Make every change the plan needs in `{path}`, and nothing else."""


def edit_prompt(request: str, code: str | None, libraries: str, plan: str, path: str,
                error: str | None = None) -> str:
    msg = _base(request, code, libraries, error)
    return (f"{msg}\nHere is the plan for this work:\n\n{plan.strip()}\n\n"
            f"Change `{path}` now. Follow the plan exactly: use the same names it gives for routes, functions, "
            f"templates, variables, form fields and database columns.\n\n" + EDIT_FORMAT.format(path=path))
