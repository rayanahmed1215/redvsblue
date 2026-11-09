"""Talk to the model (llama.cpp's llama-server or Ollama), and manage llama-server's lifecycle."""
import contextlib
import json
import subprocess
import time
import urllib.request

from .config import LLAMA_SERVER, MOE_GGUF, N_CPU_MOE, SERVER_LOG, ModelConfig


def _post(url, body, timeout=3600):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def chat(cfg: ModelConfig, messages, seed) -> dict:
    """Returns {text, tokens, prompt_tokens, tok_s, seconds, truncated}."""
    start = time.time()
    if cfg.backend == "ollama":
        body = {"model": cfg.model, "messages": messages, "stream": False,
                "options": {"temperature": cfg.temperature, "top_p": cfg.top_p, "top_k": cfg.top_k,
                            "seed": seed, "num_ctx": cfg.num_ctx, "num_predict": cfg.max_output}}
        if cfg.think is not None:
            body["think"] = cfg.think
        data = _post(f"{cfg.url}/api/chat", body)
        tokens = data.get("eval_count", 0)
        eval_s = data.get("eval_duration", 0) / 1e9
        return {"text": data["message"]["content"], "tokens": tokens,
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "tok_s": tokens / eval_s if eval_s else None, "seconds": time.time() - start,
                "truncated": data.get("done_reason") == "length"}
    body = {"messages": messages, "temperature": cfg.temperature, "top_p": cfg.top_p, "top_k": cfg.top_k,
            "seed": seed, "max_tokens": cfg.max_output}
    data = _post(f"{cfg.url}/v1/chat/completions", body)
    timings = data.get("timings", {})
    choice = data["choices"][0]
    return {"text": choice["message"]["content"],
            "tokens": timings.get("predicted_n") or data.get("usage", {}).get("completion_tokens", 0),
            "prompt_tokens": data.get("usage", {}).get("prompt_tokens") or timings.get("prompt_n", 0),
            "tok_s": timings.get("predicted_per_second"), "seconds": time.time() - start,
            "truncated": choice.get("finish_reason") == "length"}


def healthy(cfg: ModelConfig) -> bool:
    path = "/api/tags" if cfg.backend == "ollama" else "/health"
    try:
        with urllib.request.urlopen(f"{cfg.url}{path}", timeout=2) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


@contextlib.contextmanager
def model_server(cfg: ModelConfig, log=print):
    """Make sure the model is reachable. Starts llama-server (and stops it afterwards) if it isn't running."""
    if healthy(cfg):
        yield
        return
    if cfg.backend == "ollama":
        raise RuntimeError(f"Ollama isn't reachable at {cfg.url}. Is the ollama service running?")
    for path in (LLAMA_SERVER, MOE_GGUF):
        if not path.exists():
            raise RuntimeError(f"Missing {path}. See bakeoff/ and the README for setup.")
    port = cfg.url.rsplit(":", 1)[1]
    cmd = [str(LLAMA_SERVER), "-m", str(MOE_GGUF), "-ngl", "99", "--n-cpu-moe", str(N_CPU_MOE),
           "-c", str(cfg.num_ctx), "--host", "127.0.0.1", "--port", port]
    log(f"Starting llama-server (n-cpu-moe {N_CPU_MOE}, ctx {cfg.num_ctx}); log: {SERVER_LOG}")
    with open(SERVER_LOG, "w") as out:
        proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 600
        while not healthy(cfg):
            if proc.poll() is not None:
                raise RuntimeError(f"llama-server exited early (code {proc.returncode}); see {SERVER_LOG}")
            if time.time() > deadline:
                raise RuntimeError("llama-server didn't become ready within 10 minutes")
            time.sleep(2)
        log("llama-server is ready.")
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            proc.kill()
        log("llama-server stopped.")
