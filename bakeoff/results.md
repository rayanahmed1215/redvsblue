# Builder bake-off results

Note: these runs used temperature 0.2, so outputs from different seeds were often near-identical (up to 97% similar).
Task: `bakeoff/task.md` (Flask + SQLite blog). Score = smoke-test steps passed out of 5.
Each run gets one first attempt and, if it fails, one repair attempt with the error message.

| Model | Runs | 1st try avg (/5) | 1st try working | After repair avg (/5) | After repair working | Avg tok/s | Avg sec/run | Avg LOC | Notes |
|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:7b | 3 | 1.7 | 1/3 | 1.7 | 1/3 | 45.3 | 42 | 141 |  |
| qwen3:8b | 3 | 1.0 | 0/3 | 5.0 | 3/3 | 36.6 | 56 | 167 |  |
| qwen3.5:9b | 3 | 2.3 | 1/3 | 5.0 | 3/3 | 29.9 | 93 | 168 |  |
| qwen3-coder-30b-a3b (MoE) | 3 | 0.0 | 0/3 | 5.0 | 3/3 | 14.3 | 212 | 314 | llama.cpp n-cpu-moe=34 |

## What went wrong

- **qwen2.5-coder:7b** seed 22 try1: home page loads: `AttributeError: 'Flask' object has no attribute 'before_first_request'. Did you mean: '_got_first_request'?`
- **qwen2.5-coder:7b** seed 22 try2: home page loads: `AttributeError: 'Flask' object has no attribute 'before_first_request'. Did you mean: '_got_first_request'?`
- **qwen2.5-coder:7b** seed 33 try1: home page loads: `AttributeError: 'Flask' object has no attribute 'before_first_request'. Did you mean: '_got_first_request'?`
- **qwen2.5-coder:7b** seed 33 try2: home page loads: `AttributeError: 'Flask' object has no attribute 'before_first_request'. Did you mean: '_got_first_request'?`
- **qwen3:8b** seed 11 try1: create post: `KeyError: '3'`
- **qwen3:8b** seed 22 try1: create post: `KeyError: '3DATABASE'`
- **qwen3:8b** seed 33 try1: create post: `KeyError: '3DATABASE'`
- **qwen3.5:9b** seed 11 try1: create post: `sqlite3.ProgrammingError: Cannot operate on a closed database.`
- **qwen3.5:9b** seed 22 try1: create post: `sqlite3.ProgrammingError: Cannot operate on a closed database.`
- **qwen3-coder-30b-a3b (MoE)** seed 11 try1: home page loads: `AttributeError: 'Flask' object has no attribute 'before_first_request'. Did you mean: '_got_first_request'?`
- **qwen3-coder-30b-a3b (MoE)** seed 22 try1: home page loads: `AttributeError: 'Flask' object has no attribute 'before_first_request'. Did you mean: '_got_first_request'?`
- **qwen3-coder-30b-a3b (MoE)** seed 33 try1: home page loads: `AttributeError: 'Flask' object has no attribute 'before_first_request'. Did you mean: '_got_first_request'?`
