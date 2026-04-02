#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/nyx/subtitle-vr-demo/cloudflare-api"
CONFIG="$ROOT/deploy_config.json"
WRANGLER_JSON="$ROOT/wrangler.jsonc"

if [[ ! -f "$CONFIG" ]]; then
  echo "Missing config file: $CONFIG"
  exit 1
fi

if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  echo "CLOUDFLARE_API_TOKEN is not set."
  echo "Export it once in this shell, then rerun this script."
  exit 1
fi

read_json() {
  python3 - "$CONFIG" "$1" <<'PY'
import json, sys
path, key = sys.argv[1:3]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
parts = key.split(".")
cur = data
for part in parts:
    cur = cur[part]
if isinstance(cur, str):
    print(cur)
else:
    import json as _json
    print(_json.dumps(cur))
PY
}

WORKER_URL="$(read_json worker_url)"
APP_API_KEY="$(read_json app_api_key)"
PROXY_API_KEY="$(read_json proxy_api_key)"
TUNNEL_URL="$(read_json tunnel_url)"
UPSTREAM_MODE="$(read_json upstream_mode)"
UPSTREAM_OPENAI_MODEL="$(read_json upstream_openai_model)"
DEFAULT_STT="$(read_json defaults.stt)"
DEFAULT_REPLY="$(read_json defaults.reply)"
DEFAULT_TTS="$(read_json defaults.tts)"

echo "Checking local llama-server..."
curl --http1.1 -fsS http://127.0.0.1:8080/health >/tmp/quest_llama_health.json
cat /tmp/quest_llama_health.json
echo
echo

echo "Checking local proxy..."
curl --http1.1 -fsS http://127.0.0.1:5050/v1/chat/completions \
  -H "Authorization: Bearer $PROXY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"nyx","messages":[{"role":"user","content":"Say hello in one sentence."}],"max_tokens":80,"temperature":0.5,"stream":false}' >/tmp/quest_proxy_check.json
cat /tmp/quest_proxy_check.json
echo
echo

echo "Checking public tunnel..."
curl --http1.1 -fsS "$TUNNEL_URL/v1/chat/completions" \
  -H "Authorization: Bearer $PROXY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"nyx","messages":[{"role":"user","content":"Say hello in one sentence."}],"max_tokens":80,"temperature":0.5,"stream":false}' >/tmp/quest_tunnel_check.json
cat /tmp/quest_tunnel_check.json
echo
echo

echo "Updating wrangler.jsonc..."
python3 - "$WRANGLER_JSON" "$UPSTREAM_MODE" "$TUNNEL_URL" "$PROXY_API_KEY" "$UPSTREAM_OPENAI_MODEL" "$DEFAULT_STT" "$DEFAULT_REPLY" "$DEFAULT_TTS" <<'PY'
import json, sys
path, upstream_mode, tunnel_url, proxy_key, model, default_stt, default_reply, default_tts = sys.argv[1:8+1]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
vars_ = data.setdefault("vars", {})
vars_["UPSTREAM_MODE"] = upstream_mode
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
echo "Deploying worker..."
npx wrangler deploy

echo "Writing remote app key..."
printf '%s' "{\"id\":\"team-shared\",\"label\":\"Hackathon Team\",\"mode\":\"shared\",\"enabled\":true,\"features\":{\"cloud_stt\":true,\"cloud_reply\":true,\"cloud_tts\":true}}" > /tmp/team-demo-key.json
npx wrangler kv key put --remote --binding API_KEYS --path /tmp/team-demo-key.json "key:$APP_API_KEY"

echo
echo "Checking live /health..."
curl --http1.1 -fsS "$WORKER_URL/health"
echo
echo

echo "Checking live /config..."
curl --http1.1 -fsS "$WORKER_URL/config" -H "Authorization: Bearer $APP_API_KEY"
echo
echo

echo "Checking live /reply..."
curl --http1.1 -fsS "$WORKER_URL/reply" \
  -H "Authorization: Bearer $APP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"transcript":"Hi Neo, introduce yourself in one sentence.","history":[],"mode":"fast"}'
echo
echo

echo "Done."
echo "Worker URL: $WORKER_URL"
echo "App key: $APP_API_KEY"
