"""Minimal stdlib clients for Ollama and llama.cpp's llama-server.

Both take a full message list so the runner can do a follow-up "repair" turn.
"""
import json
import time
import urllib.request

TEMPERATURE = 0.7  # Qwen's recommended non-thinking sampling; 0.2 made runs near-identical
TOP_P = 0.8
TOP_K = 20
NUM_CTX = 8192  # 16k spilled 7% of a 7B model to CPU on 8 GB VRAM
MAX_OUTPUT = 6144


def _post(url, body, timeout=1800):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def ollama_chat(model, messages, seed, think=None, num_ctx=NUM_CTX, host="http://127.0.0.1:11434"):
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": TEMPERATURE, "top_p": TOP_P, "top_k": TOP_K, "seed": seed,
                    "num_ctx": num_ctx, "num_predict": MAX_OUTPUT},
    }
    if think is not None:  # only send for models that support thinking, or Ollama errors
        body["think"] = think
    start = time.time()
    data = _post(f"{host}/api/chat", body)
    seconds = time.time() - start
    tokens = data.get("eval_count", 0)
    eval_s = data.get("eval_duration", 0) / 1e9
    return {
        "text": data["message"]["content"],
        "tokens": tokens,
        "prompt_tokens": data.get("prompt_eval_count", 0),
        "tok_s": tokens / eval_s if eval_s else None,
        "seconds": seconds,
        "truncated": data.get("done_reason") == "length",
    }


def llamacpp_chat(messages, seed, url="http://127.0.0.1:8081"):
    body = {"messages": messages, "temperature": TEMPERATURE, "top_p": TOP_P, "top_k": TOP_K,
            "seed": seed, "max_tokens": MAX_OUTPUT}
    start = time.time()
    data = _post(f"{url}/v1/chat/completions", body)
    seconds = time.time() - start
    timings = data.get("timings", {})
    choice = data["choices"][0]
    return {
        "text": choice["message"]["content"],
        "tokens": timings.get("predicted_n") or data.get("usage", {}).get("completion_tokens", 0),
        "prompt_tokens": data.get("usage", {}).get("prompt_tokens") or timings.get("prompt_n", 0),
        "tok_s": timings.get("predicted_per_second"),
        "seconds": seconds,
        "truncated": choice.get("finish_reason") == "length",
    }
