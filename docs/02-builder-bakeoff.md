# 2. Choosing the Builder model (bake-offs)

**Dates:** Nov 8–9. **Code:** `bakeoff/`. **Raw results:** [`results.md`](../bakeoff/results.md), [`results_stages.md`](../bakeoff/results_stages.md).

A **bake-off** is a contest: give several models the same task and measure which does best.

## Decision: a local model, not the Claude API
The first plan used the Claude API. You stopped it ("why Claude API?"), so the Builder runs **on your own laptop**. That way it's free to run as often as we like, and everything stays local, on 127.0.0.1.

Your hardware sets the limits: an RTX 4070 laptop GPU with **8 GB of VRAM** (the GPU's own memory), 31.5 GB of RAM, under WSL2.
- A model is fast only if it fits in VRAM, which means about 7–8 billion **parameters** (the numbers a model learned in training) or fewer.
- Models are stored compressed to about 4 bits per number (**Q4**) so that they fit.

## Decision: drop JSON, add a repair step
At first the model had to reply in JSON. Code inside JSON needs every quote and newline escaped, and small models get that wrong. The new format is a heading per file (`### File: app.py`) followed by a normal code block.

You also chose to let the model **repair**: if the app fails, it gets the error message and one more try.

## Bake-off 1: one small blog app
**Task** ([`task.md`](../bakeoff/task.md)): a Flask + SQLite blog with posts and comments. It's scored by a 5-step smoke test. 3 runs per model, temperature 0.2.

| Model | 1st try avg (/5) | 1st try working | After repair working | tok/s | sec/run | Lines of code |
|---|---|---|---|---|---|---|
| qwen2.5-coder:7b | 1.7 | 1/3 | 1/3 | 45.3 | 42 | 141 |
| qwen3:8b | 1.0 | 0/3 | **3/3** | 36.6 | 56 | 167 |
| qwen3.5:9b | 2.3 | 1/3 | **3/3** | 29.9 | 93 | 168 |
| Qwen3-Coder-30B-A3B (MoE) | 0.0 | 0/3 | **3/3** | 14.3 | 212 | 314 |

What went wrong:
- qwen2.5-coder:7b and the MoE both used `before_first_request`, which was removed in Flask 3. qwen2.5-coder never fixed it, even after the repair.
- qwen3:8b had `KeyError` bugs in "create post", and qwen3.5:9b used a database connection after closing it. Both fixed these on repair.
- Temperature 0.2 made seeds nearly identical (up to 97% similar), so 3 runs were really about 1.

**MoE** means "mixture of experts." The model has 30B parameters, but only about 3B are used for each word it writes. Most of it stays in normal RAM (`--n-cpu-moe`), so it fits on your laptop, but it runs slower.

At this point qwen3:8b looked best: just as reliable and 4× faster. You asked for a harder test between the two finalists.

## Bake-off 2: a 5-stage blog
5 stages, each one adding a feature (basic blog → accounts → edit/delete → tags and search → Markdown). Each stage is graded on **every feature so far** (15 checks in total) and gets up to 3 repairs. A run stops at the first stage it can't pass. The settings are temperature 0.7, top_p 0.8, top_k 20, a 12k context, and a hint in the prompt about Flask 3.

| Model | Runs | Avg stages passed | Tries per stage | Min/run | tok/s | Max context used |
|---|---|---|---|---|---|---|
| qwen3:8b | 1 | **0/5** | 4.0 | 3.1 | 25.2 | 2,903 / 12,288 |
| MoE (`n-cpu-moe 36`) | 2 | **5/5** | 1.2 | 20.5 | 17.6 | 9,395 / 12,288 |

- The MoE stage by stage: seed 11 took 1, 2, 2, 1 and 1 tries. Seed 22 passed every stage on the first try.
- qwen3:8b never passed stage 1, here or in 3 earlier attempts. ("It clearly isn't up to the task.")
- The context is 12k, not 16k, because at 16k qwen3:8b spilled out of VRAM and dropped to 1.8 tok/s. The MoE needed 36 expert layers in RAM instead of 34 to make room.

**Decision:** the MoE is the Builder and qwen3:8b is dropped. Being slower is fine, because a Builder that can't get past stage 1 is useless.
