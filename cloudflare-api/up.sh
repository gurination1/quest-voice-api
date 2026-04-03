#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$ROOT/.." && pwd)"
ENV_FILE="$ROOT/.env"
WRANGLER_JSON="$ROOT/wrangler.jsonc"
PROJECT_KEYS_FILE="$PROJECT_ROOT/keys.txt"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  echo "Copy .env.example to .env and fill it once."
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" || "${!name}" == "replace_me" ]]; then
    echo "Missing required env var: $name"
    exit 1
  fi
}

require_var CLOUDFLARE_API_TOKEN
require_var WORKER_URL
require_var APP_API_KEY
require_var PROXY_API_KEY
require_var TUNNEL_PUBLIC_URL

if [[ -n "${CF_ACCOUNT_ID:-}" && -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
  export CLOUDFLARE_ACCOUNT_ID="$CF_ACCOUNT_ID"
fi

mkdir -p /home/nyx/.cloudex-runtime

echo "1. Checking llama-server..."
if ! curl --http1.1 -fsS "$LLAMA_HEALTH_URL" >/home/nyx/.cloudex-runtime/llama_health.json; then
  echo "llama-server is not reachable at $LLAMA_HEALTH_URL"
  echo "Start it first, for example:"
  echo "python3 -c \"from assistant.genesis_llm import start_model; start_model('9B')\""
  exit 1
fi
cat /home/nyx/.cloudex-runtime/llama_health.json
echo
echo

echo "2. Ensuring proxy key exists..."
touch "$PROJECT_KEYS_FILE"
if ! grep -qxF "$PROXY_API_KEY" "$PROJECT_KEYS_FILE"; then
  echo "$PROXY_API_KEY" >> "$PROJECT_KEYS_FILE"
fi

echo "3. Ensuring proxy is running on ${PROXY_HOST}:${PROXY_PORT}..."
if ! curl --http1.1 -fsS "http://${PROXY_HOST}:${PROXY_PORT}/health" >/home/nyx/.cloudex-runtime/proxy_health.json; then
  nohup "$PROJECT_ROOT/start_local_api.sh" --host "${PROXY_HOST}" --port "${PROXY_PORT}" >/home/nyx/.cloudex-runtime/proxy.log 2>&1 &
  sleep 3
fi
curl --http1.1 -fsS "http://${PROXY_HOST}:${PROXY_PORT}/health" >/home/nyx/.cloudex-runtime/proxy_health.json
cat /home/nyx/.cloudex-runtime/proxy_health.json
echo
echo

echo "4. Checking public proxy URL..."
if ! curl --http1.1 -fsS "${TUNNEL_PUBLIC_URL}/health" >/home/nyx/.cloudex-runtime/tunnel_health.json; then
  echo "Public tunnel URL is not reachable: $TUNNEL_PUBLIC_URL"
  echo "If using a named tunnel, start it separately with cloudflared."
  exit 1
fi
cat /home/nyx/.cloudex-runtime/tunnel_health.json
echo
echo

echo "5. Updating Worker config..."
python3 - "$WRANGLER_JSON" "$TUNNEL_PUBLIC_URL" "$PROXY_API_KEY" "$UPSTREAM_OPENAI_MODEL" "$DEFAULT_STT" "$DEFAULT_REPLY" "$DEFAULT_TTS" <<'PY'
import json, sys
path, tunnel_url, proxy_key, model, default_stt, default_reply, default_tts = sys.argv[1:8]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
vars_ = data.setdefault("vars", {})
vars_["UPSTREAM_MODE"] = "openai_proxy"
vars_["UPSTREAM_OPENAI_BASE_URL"] = tunnel_url
vars_["UPSTREAM_OPENAI_API_KEY"] = proxy_key
vars_["UPSTREAM_OPENAI_MODEL"] = model
vars_["FALLBACK_CONFIG_JSON"] = json.dumps({
    "recommended_defaults": {
        "stt": default_stt,
        "reply": default_reply,
        "tts": default_tts,
    }
}, separators=(",", ":"))
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY

cd "$ROOT"

echo "6. Deploying Worker..."
npx wrangler deploy

echo "7. Writing remote app key..."
printf '%s' "{\"id\":\"team-shared\",\"label\":\"Hackathon Team\",\"mode\":\"shared\",\"enabled\":true,\"features\":{\"cloud_stt\":true,\"cloud_reply\":true,\"cloud_tts\":true}}" > /tmp/team-demo-key.json
npx wrangler kv key put --remote --binding API_KEYS --path /tmp/team-demo-key.json "key:${APP_API_KEY}"

echo "8. Running smoke tests..."
curl --http1.1 -fsS "${WORKER_URL}/health" >/home/nyx/.cloudex-runtime/worker_health.json
cat /home/nyx/.cloudex-runtime/worker_health.json
echo
echo

curl --http1.1 -fsS "${WORKER_URL}/config" -H "Authorization: Bearer ${APP_API_KEY}" >/home/nyx/.cloudex-runtime/worker_config.json
cat /home/nyx/.cloudex-runtime/worker_config.json
echo
echo

curl --http1.1 -fsS "${WORKER_URL}/reply" \
  -H "Authorization: Bearer ${APP_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"transcript":"Hi Neo, introduce yourself in one sentence.","history":[],"mode":"fast"}' >/home/nyx/.cloudex-runtime/worker_reply.json
cat /home/nyx/.cloudex-runtime/worker_reply.json
echo
echo

echo "Done."
echo "Base URL: ${WORKER_URL}"
echo "API key: ${APP_API_KEY}"
