#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8000}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-Qwen/Qwen3-8B}"
export NO_PROXY=127.0.0.1,localhost
export no_proxy="$NO_PROXY"

curl --noproxy '*' --max-time 10 -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null

python3 - "$PORT" "$SERVED_MODEL_NAME" <<'PY'
import json, sys, urllib.request

port, model = sys.argv[1], sys.argv[2]
payload = {
    "model": model,
    "temperature": 0.0,
    "max_tokens": 128,
    "messages": [
        {"role": "user", "content": "Call get_weather for Beijing."},
    ],
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ],
}
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/v1/chat/completions",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    body = json.loads(resp.read().decode())
choice = body["choices"][0]["message"]
print(json.dumps({
    "id": body.get("id"),
    "model": body.get("model"),
    "usage": body.get("usage"),
    "finish_reason": body["choices"][0].get("finish_reason"),
    "has_tool_calls": bool(choice.get("tool_calls")),
    "has_reasoning": bool(choice.get("reasoning_content")),
    "content_preview": (choice.get("content") or "")[:200],
}, ensure_ascii=False, indent=2))
if body.get("model") != model:
    raise SystemExit(f"model_identity mismatch: {body.get('model')!r}")
if not body.get("usage"):
    raise SystemExit("usage_missing")
PY
