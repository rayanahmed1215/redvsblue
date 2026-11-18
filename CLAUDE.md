# RvB: Red vs Blue Learning Lab

## What we're building
A self-running red team vs blue team system. It's a way to learn web security by watching it happen. There are three agents:
- **Builder**: a local LLM that grows a real Flask + SQLite blog over time, one work item at a time. It only thinks about features, not security.
- **Red (attacker)**: attacks each tagged release of the site. *Not built yet.*
- **Blue (defender)**: triages Red's breach reports and sends fix tickets back to the Builder. Fixes that keep working become secure-coding rules. *Not built yet.*

The user is new to cybersecurity. Explain the *why* behind security concepts and design choices, in plain language. Everything stays local and simulated: attacks only ever target our own generated sites on 127.0.0.1.

## Repo layout
| Path | What it is |
|---|---|
| `index.html`, `js/`, `css/`, `test/` | The original browser simulation, where the vulnerabilities are toy rules (see README.md). Run with `npm start`, test with `npm test`. |
| `bakeoff/` | The harness that picked the Builder model. Results are in `bakeoff/results*.md`. |
| `builder/` | **The original Builder program** (one model call writes every changed file). Kept unchanged so the two versions can be compared. |
| `builder2/` | **Builder version 2: plan first, then one file per call.** This is the current focus. It holds only what differs (`plan.py`, `files.py`, `build.py`, `checker.py`, `__main__.py`, `tests/`) and imports the rest from `builder/`. |
| `builder/roadmaps/blog/` | 10 feature stages (`stages/stageN.md`), their checks (`checks.py`) and the 14-tick `timeline.json`. |
| `ecosystem/` | Homemade libraries (`mdlite`, `uploadkit`, `pager`) with scripted release histories and **planted bugs**. `advisories.json` is the answer key. It is never shown to the Builder; it's for scoring Red and Blue later. |
| `sites/<name>/` | Generated sites (git-ignored). Each one is its own git repo, with releases tagged `v1`, `v2`, and so on. Builder state lives in `sites/<name>/.builder/` (`state.json`, `releases.json`, `attempts/`). |
| `docs/` | Project history: the mock sim, both bake-offs, Builder v1 and v2, every decision with its stats. Update it when a milestone lands. |
| `moe.sh` | Starts the MoE model on its own and opens its chat page (handy for poking at it by hand). |

## How the Builder works
- **The model** is Qwen3-Coder-30B-A3B (MoE, Q4_K_M) on llama.cpp, with `--n-cpu-moe 36` and a 12k context, on port 8081. It won the bake-offs; qwen3:8b was dropped. Settings are in `builder/config.py`. The hardware is an RTX 4070 8GB laptop GPU with 31.5GB RAM, under WSL2, so VRAM is tight. Don't run two models at once.
- **A clock in ticks.** Each tick in `timeline.json` can request features and publish library versions.
- **A work-item queue** holds three kinds of item:
  - `feature`: from the roadmap.
  - `dep_update`: a library the site uses shipped a new version, so upgrade to it.
  - `fix`: a ticket. These come from the CLI for now and from Blue later.
- **One loop for every item:** prompt (current code + library docs) → apply files → run all checks so far → repair up to 5 times → commit and tag a release, or roll back.

```bash
python3 -m builder new demo                # create sites/demo
python3 -m builder run demo --ticks 4      # advance the clock 4 ticks (starts/stops llama-server itself)
python3 -m builder run demo --ticks 0      # only process the queue (e.g. tickets)
python3 -m builder ticket demo --title "..." --body "..."
python3 -m builder status demo             # clock, queue, releases
python3 -m builder serve demo              # http://127.0.0.1:5000
```

### Builder version 2 (`builder2/`)
Same commands, clock, queue and releases, run as `python3 -m builder2 ...`. Only the loop for one item differs:
1. **Plan call.** The model writes no code. It lists the files it will create or change (`## Files`), the names that files share (`## Connections`: routes, templates, Jinja filters, form fields, database columns) and the libraries (`## Libraries`).
2. **Plan check.** No model involved: paths must be safe, at most 12 files, and a `dep_update` always includes `requirements.txt`.
3. **One call per file**, in the order `requirements.txt`, `.py` files, then the rest. Each call sees the plan and the files already written in this try. Files that aren't in the plan can't be touched.
4. **"Files agree" check**, then the normal checks. It reports every mismatch at once: unknown Jinja filters, templates that don't exist, `url_for` names with no route.
5. A retry starts with a new plan that sees the error and the previous plan.

Each try saves `plan.md` next to `reply.md` in `.builder/attempts/<item>/tryN/`. `builder2` runs on `sites/demo2`, a copy of `demo` taken at v3. Leave `sites/demo` for the original Builder.

Tests:
```bash
python3 -m unittest discover -s builder2/tests -t .
python3 -m unittest discover -s builder/tests -t .
python3 -m unittest discover -s ecosystem/tests
npm test                                   # the JS simulation
```

## Steps for every task
1. **Understand.** Re-read this file and check `git status` and `python3 -m builder status <site>`. Look things up in the code or the last session's transcript instead of asking the user to repeat themselves.
2. **Discuss.** For anything bigger than a small fix, explain the idea and the trade-offs in plain language, then ask about any real decisions before writing code.
3. **Build in phases.** Make one small, working piece at a time, and add or update tests with each piece.
4. **Test.** Run the relevant test suites (see above) and make sure they pass before moving on. If something fails, say so and show the output.
5. **Run it for real.** For Builder changes, run it against a site and check `status` and the saved attempts in `.builder/attempts/`.
6. **Report.** Say what changed, what was verified, what's left, and the exact command to continue.
7. **Update this file.** Keep "Where we are" and "What's next" current.
8. **Commit and push only when asked.** Use a 1–3 line message with no attribution.

## Workflow with the user
- **Long runs:** start them, then report progress when the user asks for "status". The user often says **"pause"**. When they do, stop cleanly: kill `llama-server`, leave no half-finished attempt behind, and say exactly where things stopped and the command to resume. Nothing should ever be redone after a resume.
- **Before big changes,** discuss the structure first and ask for decisions on real forks. Then build it in phases, with tests passing at each phase.
- **Git:**
  - Work happens on feature branches (currently `builder-setup`). `main` is the default branch. The remote is `github.com/rayanahmed1215/redvsblue`.
  - Commit and push only when asked.
  - Commit messages are 1–3 lines. **Never add Co-Authored-By or any Claude attribution.**
- **Keep explanations plain:** short sentences, and define jargon the first time it comes up.

## Where we are (2026-11-15)
- The original Builder (`builder/`) is committed and unchanged. Its `demo` run is still paused at tick 4, clean at v3, with feature 4 queued after 3 failed whole-file tries.
- **Builder version 2 (`builder2/`) is built and tested (26 tests) but not committed.** It plans first, then writes one file per call (see "Builder version 2" above).
- **`sites/demo2` is paused at tick 4, clean at v3, with feature 4 queued.** One `builder2` try has run on it so far:
  - Try 1 planned 6 files and wrote all 6 in 7 calls (470s). No reply was cut off; the largest was `app.py` at 2,710 tokens, and the largest context was 8,157 of 12,288.
  - It failed the "files agree" check: `templates/index.html` used a filter `get_post_tags`, while the plan named it `tag_links` and `app.py` defined neither. The same mistake as the whole-file tries, but now caught with a one-line error instead of 13 crashed checks.
  - Try 2 was interrupted by the pause and rolled back. The plan and replies for try 1 are in `sites/demo2/.builder/attempts/feature-4/try1/` (`try2` and `try3` there are old whole-file tries copied from `demo`).
- Resume with `python3 -m builder2 run demo2 --ticks 0`. It starts feature 4 again from a fresh plan.

## What's next
1. **Finish the feature 4 comparison with `builder2`** on `demo2` (`python3 -m builder2 run demo2 --ticks 0`). Watch whether the retry plan fixes the filter mismatch, and whether templates keep using names the plan didn't give.
2. **Edit-based replies**, if whole files get too big. The model sends find/replace edits for existing files, and whole files only for new ones. `app.py` is already a 2,710-token reply on its own.
3. **Split the app into a few files** (route files per area), so each prompt only includes the files a feature touches.
4. **Keep releases and reuse them.** Red and Blue attack saved releases many times over; the Builder only runs again for fix tickets.
5. Resume the winning Builder's site and run the full 14-tick timeline. Check how the Builder handles the dependency updates, especially the planted bugs: mdlite 1.1.0 XSS, uploadkit 1.0.0 path traversal, and the mdlite 2.0.0 breaking change.
6. Possibly let the Builder *decide* whether to take a dependency update. Right now it always upgrades.
7. Build **Red**: attack each tagged release, score it against `ecosystem/advisories.json` and against vulnerabilities in the Builder's own code.
8. Build **Blue**: read breach reports, file `fix` tickets through the same queue, and verify each fix with Red's retest. Then turn proven fixes into secure-coding rules that get added to the Builder's prompt.
