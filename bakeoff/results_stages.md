# Multi-stage Builder bake-off

5 stages (`bakeoff/stages/`), each graded on every feature so far. Up to 3 repairs per stage;
a run stops at the first stage it can't pass.

| Model | Runs | Avg stages passed | Finished all | Tries per stage (avg) | Avg minutes/run | Stages per hour | Avg tok/s | Max context used | Notes |
|---|---|---|---|---|---|---|---|---|---|
| qwen3:8b | 1 | 0.0/5 | 0/1 | 0.0 | 1.9 | 0.0 | 26.4 | 2436 / 12288 |  |

## Stage by stage

- **qwen3:8b** seed 11: S1 ❌ 4 tries
  - stuck on stage 1: failed checks ['app starts']
