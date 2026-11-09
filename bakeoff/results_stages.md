# Multi-stage Builder bake-off

5 stages (`bakeoff/stages/`), each graded on every feature so far. Up to 3 repairs per stage;
a run stops at the first stage it can't pass.
Sampling: temperature 0.7, top_p 0.8, top_k 20. The system prompt includes a Flask 3 hint (no before_first_request; create tables with sqlite3 at import).

| Model | Runs | Avg stages passed | Finished all | Tries per attempted stage (avg) | Avg minutes/run | Stages per hour | Avg tok/s | Max context used | Notes |
|---|---|---|---|---|---|---|---|---|---|
| qwen3:8b | 1 | 0.0/5 | 0/1 | 4.0 | 3.1 | 0.0 | 25.2 | 2903 / 12288 |  |
| qwen3-coder-30b-a3b (MoE) | 2 | 5.0/5 | 2/2 | 1.2 | 20.5 | 14.6 | 17.6 | 9395 / 12288 | llama.cpp n-cpu-moe=36 |

## Stage by stage

- **qwen3:8b** seed 11: S1 ❌ 4 tries
  - stuck on stage 1: failed checks ['create post', 'view post', 'comments']
- **qwen3-coder-30b-a3b (MoE)** seed 11: S1 ✅ 1 try · S2 ✅ 2 tries · S3 ✅ 2 tries · S4 ✅ 1 try · S5 ✅ 1 try
- **qwen3-coder-30b-a3b (MoE)** seed 22: S1 ✅ 1 try · S2 ✅ 1 try · S3 ✅ 1 try · S4 ✅ 1 try · S5 ✅ 1 try

## Notes

- qwen3:8b was dropped after this run: across 3 more attempts (with earlier harness versions) it also never passed stage 1.
- MoE seed 11's time includes about 6.6 minutes when the laptop went to sleep (Windows Modern Standby, 9:02–9:09).
