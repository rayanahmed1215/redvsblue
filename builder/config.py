"""Settings for the Builder. Defaults come from the bake-offs (see bakeoff/results_stages.md)."""
from dataclasses import dataclass
from pathlib import Path

PKG = Path(__file__).resolve().parent
ROOT = PKG.parent
SITES_DIR = ROOT / "sites"
ROADMAPS_DIR = PKG / "roadmaps"
VENV_PY = PKG / ".venv" / "bin" / "python"  # runs the generated apps (Flask + markdown installed)
SERVER_LOG = PKG / ".llama-server.log"

# The MoE won the multi-stage bake-off: 5/5 stages in both runs.
LLAMA_SERVER = Path.home() / "tools" / "llama.cpp" / "build" / "bin" / "llama-server"
MOE_GGUF = Path.home() / "models" / "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
N_CPU_MOE = 36  # expert layers kept in RAM; 34 left too little VRAM at a 12k context

MAX_REPAIRS = 5

# Don't mention app.app_context() here: it's the Flask-SQLAlchemy idiom and pulls models toward that library.
SYSTEM_PROMPT = (
    "You are a web developer. You write complete, working code and reply in the exact format requested. "
    "This is Flask 3.x, where before_first_request no longer exists: create the database tables with a "
    "plain function that app.py calls once at import time, using Python's built-in sqlite3 module."
)


@dataclass
class ModelConfig:
    backend: str = "llamacpp"  # "llamacpp" (managed llama-server) or "ollama"
    model: str = "qwen3-coder-30b-a3b"  # label for llama.cpp; the model tag for Ollama
    url: str = "http://127.0.0.1:8081"
    num_ctx: int = 12288
    temperature: float = 0.7  # Qwen's recommended non-thinking sampling
    top_p: float = 0.8
    top_k: int = 20
    max_output: int = 6144
    think: bool | None = None  # Ollama only: False for qwen3-family models

    @classmethod
    def ollama(cls, tag: str) -> "ModelConfig":
        return cls(backend="ollama", model=tag, url="http://127.0.0.1:11434",
                   think=False if tag.startswith("qwen3") else None)
