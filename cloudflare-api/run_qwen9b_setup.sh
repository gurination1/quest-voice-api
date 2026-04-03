#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="$ROOT/wrangler.jsonc"
WORKER_URL="https://quest-voice-api.questvoice2026.workers.dev"
APP_KEY="team-demo-key"

if [[ ! -f "$CFG" ]]; then
  echo "Missing config: $CFG"
  exit 1
fi

if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  echo "CLOUDFLARE_API_TOKEN is not set in this shell."
  echo "Run: export CLOUDFLARE_API_TOKEN='YOUR_TOKEN'"
  exit 1
fi

read -r -p "Enter public proxy URL (example: https://name.trycloudflare.com): " TUNNEL_URL
if [[ -z "$TUNNEL_URL" ]]; then
  echo "Tunnel URL is required."
  exit 1
fi

read -r -p "Use proxy key [team-demo-key]: " PROXY_KEY
PROXY_KEY="${PROXY_KEY:-$APP_KEY}"

python3 - "$CFG" "$TUNNEL_URL" "$PROXY_KEY" <<'PY'
import json, sys
path, tunnel_url, proxy_key = sys.argv[1:4]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
vars_ = data.setdefault("vars", {})
vars_["UPSTREAM_MODE"] = "openai_proxy"
vars_["UPSTREAM_OPENAI_BASE_URL"] = tunnel_url
vars_["UPSTREAM_OPENAI_API_KEY"] = proxy_key
vars_["UPSTREAM_OPENAI_MODEL"] = "nyx"
vars_["FALLBACK_CONFIG_JSON"] = "{\"recommended_defaults\":{\"stt\":\"device\",\"reply\":\"cloud\",\"tts\":\"device\"}}"
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print("Updated wrangler.jsonc")
PY

cd "$ROOT"
echo "Deploying Worker..."
npx wrangler deploy

echo "Writing remote shared app key..."
printf '%s' '{"id":"team-shared","label":"Hackathon Team","mode":"shared","enabled":true,"features":{"cloud_stt":true,"cloud_reply":true,"cloud_tts":true}}' > /tmp/team-demo-key.json
npx wrangler kv key put --remote --binding API_KEYS --path /tmp/team-demo-key.json "key:$APP_KEY"

echo
echo "Testing /health"
curl --http1.1 "$WORKER_URL/health"
echo
echo
echo "Testing /reply"
curl --http1.1 "$WORKER_URL/reply" \
  -H "Authorization: Bearer $APP_KEY" \
  -H "Content-Type: application/json" \
  -d '{"transcript":"Hi Neo, introduce yourself in one sentence.","history":[],"mode":"fast"}'
echo
echo
echo "Testing /v1/chat/completions"
curl --http1.1 "$WORKER_URL/v1/chat/completions" \
  -H "Authorization: Bearer $APP_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Say hello from the Neo Qwen 9B model in one sentence."}],"max_tokens":80,"temperature":0.5}'
echo
echo
echo "Done."
echo "Worker URL: $WORKER_URL"
echo "App key: $APP_KEY"
