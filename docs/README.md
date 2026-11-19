# RvB project history

RvB (Red vs Blue) is a learning lab for web security. Three agents share one world:

- a **Builder** that grows a website,
- **Red**, which attacks it,
- **Blue**, which defends it.

You learn by watching attacks and fixes happen. These docs cover what has been built so far, the decisions behind it, and the numbers from every test.

## Timeline

| Date | What happened |
|---|---|
| Nov 8 | First draft: a browser simulation where the hacking is toy rules. Learned that it was "fake all the way down" and that Blue hits a ceiling. |
| Nov 8 | Decided to build a **real** site with a **local** AI model. Bake-off 1: four models, one small blog app each. |
| Nov 9 | Dropped the JSON reply format and added a repair step. Bake-off 2: a 5-stage blog, MoE vs qwen3:8b. The MoE won 5/5 and qwen3:8b was dropped. |
| Nov 9 | Builder v1: tick clock, work-item queue, tagged releases, homemade libraries with planted bugs, fix tickets. |
| Nov 9–10 | `demo` run: features 1–3 released (v1–v3). Feature 4 (tags and search) failed all 3 tries. |
| Nov 15 | Builder v2: plan first, then one file per call, with a "files agree" check. First try on feature 4 caught the bug in one line. |
| Nov 18 | Paused at tick 4 on both sites. These docs written. |
| Nov 18 | v2 long run on `demo2`: v4 → v11 (features 4–8, three dependency updates). Three error messages rewritten to say *why*. Stopped at feature 9: context full. |
| Nov 18 | Builder v3: edit-based replies. `demo3` (a copy of `demo2` at v11) finished the **whole 14-tick timeline**: v15, all 10 features, mdlite 2.0.0 handled. |

## Chapters

1. [The mock simulation](01-mock-simulation.md): the first draft and why it wasn't enough
2. [Choosing the Builder model](02-builder-bakeoff.md): two bake-offs and their numbers
3. [Builder v1](03-builder-v1.md): the queue, releases, planted bugs and the `demo` run
4. [Builder v2](04-builder-v2.md): plan first, then write one file at a time
5. [Decisions and what's next](05-decisions-and-next.md): every decision in one table
6. [Builder v2 long run](06-builder-v2-full-run.md): `demo2` from v4 to v11, and where it hit the wall
7. [Builder v3: edits](07-builder-v3-edits.md): FIND/REPLACE edits, the first full timeline, and what the Builder did with the planted bugs
