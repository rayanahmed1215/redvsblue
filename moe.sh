#!/usr/bin/env bash
# Start the Builder's MoE model (Qwen3-Coder-30B) and open its chat page.
# Usage: ./moe.sh        Stop with Ctrl+C.
set -euo pipefail

SERVER="$HOME/tools/llama.cpp/build/bin/llama-server"
MODEL="$HOME/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
PORT=8081
URL="http://127.0.0.1:$PORT"

# Already running? Then there's nothing to start.
if curl -sf "$URL/health" >/dev/null 2>&1; then
  echo "The model is already running: $URL"
  exit 0
fi

for f in "$SERVER" "$MODEL"; do
  [[ -e "$f" ]] || { echo "Missing $f"; exit 1; }
done

# Same settings as builder/config.py: 36 expert layers in RAM, 12k context.
echo "Loading the model (takes a minute or two)..."
"$SERVER" -m "$MODEL" -ngl 99 --n-cpu-moe 36 -c 12288 \
  --host 127.0.0.1 --port "$PORT" >/tmp/moe-server.log 2>&1 &
PID=$!
trap 'echo; echo "Stopping..."; kill $PID 2>/dev/null; wait $PID 2>/dev/null' EXIT

until curl -sf "$URL/health" >/dev/null 2>&1; do
  if ! kill -0 $PID 2>/dev/null; then
    echo "llama-server crashed. Last lines of /tmp/moe-server.log:"
    tail -n 15 /tmp/moe-server.log
    exit 1
  fi
  sleep 2
done

echo "Ready! Open $URL in your browser. Press Ctrl+C here to stop."
# Try to open the Windows browser from WSL; fine if it doesn't work.
explorer.exe "$URL" >/dev/null 2>&1 || true
wait $PID
