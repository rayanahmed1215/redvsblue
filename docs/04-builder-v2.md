# 4. Builder v2: plan first, then one file at a time

**Date:** Nov 15. **Code:** `builder2/` (26 tests, not committed yet). **Site:** `sites/demo2`, a copy of `demo` taken at v3.

## Your decision
> "the model plans out the changes THEN implements it"
> "dependencies and connected stuff should be considered"

Feature 4 failed because files disagreed: a template called a filter that `app.py` didn't have. So v2 makes the model write down the **shared names** before it writes any code, and then checks that every file sticks to them.

`builder/` was left unchanged, so the two versions can be compared fairly on the same feature.

## How v2 works
1. **Plan call.** No code yet. The model lists:
   - `## Files`: what it will create or change
   - `## Connections`: names that files share (routes, templates, Jinja filters, form fields, database columns)
   - `## Libraries`: what it uses from mdlite, pager and so on
2. **Plan check**, with no model involved: paths must be safe, there can be at most 12 files, and a `dep_update` must include `requirements.txt`.
3. **One call per file**, in the order `requirements.txt`, then `.py`, then the rest. Each call sees the plan and the files already written in this try. Files that aren't in the plan can't be touched.
4. **"Files agree" check.** Before running the site, it reports every mismatch at once: unknown filters, missing templates, `url_for` names with no route.
5. **Retry** with a new plan that sees the error and the previous plan.

Why one file per call? Each reply stays small (one file instead of the whole site), and a reply getting cut off only loses one file.

## First try on feature 4 (`demo2`)

| Call | Reply tokens | Prompt tokens | Seconds |
|---|---|---|---|
| Plan | 333 | 5,243 | 74 |
| `app.py` | **2,710** | 5,447 | 196 |
| `templates/base.html` | 938 | 6,196 | 87 |
| `templates/edit_post.html` | 305 | 6,303 | 27 |
| `templates/new_post.html` | 218 | 6,351 | 20 |
| `templates/post.html` | 472 | 6,396 | 37 |
| `templates/index.html` | 396 | 6,427 | 28 |
| **Total** | **5,372** | peak context **8,157 / 12,288** | **470** |

### v1 vs v2 on feature 4

| | v1 (whole site per call) | v2 (plan + one file per call) |
|---|---|---|
| Biggest reply | 6,144 (cut off) | 2,710 (`app.py`) |
| Peak context | 11,375 / 12,288 | 8,157 / 12,288 |
| Time per try | 204–339 s | 470 s |
| Result | 0/13 checks, crashed | Stopped at "files agree" |
| Error the model sees | A 13-check crash with a traceback | One line: `templates/index.html line 14: No filter named 'get_post_tags'` |

**What it shows:** it made the **same mistake**. The plan called the filter `tag_links` (and noted it was "not yet implemented"), `app.py` defined neither name, and `index.html` invented `get_post_tags`. The plan didn't stop the mistake, but v2 caught it early and described it clearly, with no reply cut off and plenty of context to spare. The cost is that a try is slower.

Try 2 was cut short by a pause and rolled back cleanly. The plan and replies are in `sites/demo2/.builder/attempts/feature-4/try1/`. (`try2` and `try3` there are old v1 tries copied over from `demo`.)

**Open question:** will the retry plan, now that it sees the one-line error, get the names to agree?
