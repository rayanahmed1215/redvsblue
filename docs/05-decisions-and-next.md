# 5. Decisions and what's next

## Every decision so far

| Date | Decision | Why | What we didn't do |
|---|---|---|---|
| Nov 8 | Build a real website before Red and Blue | The simulation was toy rules, and Blue "solved" it | Extend the simulation with more attacks |
| Nov 8 | Use a local model, not the Claude API | Free to run often, and everything stays on your machine | Use a cloud API |
| Nov 9 | Replies as `### File:` headings + code blocks, not JSON | Escaping code inside JSON broke small models | Keep JSON |
| Nov 9 | Let the model repair using the error message | Every model but one went from failing to working after a repair | Grade the first try only |
| Nov 9 | Run a harder 5-stage bake-off between two finalists | 1 small app was too easy to tell them apart | Pick qwen3:8b because it was 4× faster |
| Nov 9 | Use a 12k context, not 16k | At 16k, qwen3:8b spilled out of VRAM (1.8 tok/s) | 16k |
| Nov 9 | MoE is the Builder, qwen3:8b is dropped | 5/5 stages vs 0/5 | Keep both |
| Nov 9 | Work-item queue, tick clock, tagged releases | Red/Blue need fixed versions to attack, and fixes need a way back to the Builder | A fixed list of stages |
| Nov 9 | Homemade libraries with planted bugs, answer key hidden | Real sites break through dependencies, and the key lets us score Red and Blue | Use real PyPI packages |
| Nov 10 | Pause and rethink after feature 4 failed 3 times | Rewriting whole files doesn't scale | Keep retrying |
| Nov 15 | Builder v2: plan first, then one file per call, plus a "files agree" check | Files disagreed on shared names | Edit-based replies (still on the list) |
| Nov 15 | v2 in its own folder, on a copy of the site | So v1 and v2 can be compared on the same feature | Change `builder/` in place |

## What's next
1. **Finish feature 4 with v2:** `python3 -m builder2 run demo2 --ticks 0`
2. **Edit-based replies:** the model sends find/replace edits for existing files and whole files only for new ones. `app.py` alone is already a 2,710-token reply.
3. **Split the app into a few files** (route files per area), so each prompt only includes what a feature touches.
4. **Keep releases and reuse them:** Red and Blue attack saved releases many times over.
5. **Run the full 14-tick timeline** and see how the Builder handles the planted bugs (mdlite 1.1.0 XSS, uploadkit 1.0.0 path traversal, the mdlite 2.0.0 breaking change).
6. Maybe let the Builder **decide** whether to take a dependency update.
7. **Build Red:** attack each release, and score it against `advisories.json` and against bugs in the Builder's own code.
8. **Build Blue:** read breach reports, file `fix` tickets, check each fix with Red's retest, and turn proven fixes into secure-coding rules for the Builder's prompt.
