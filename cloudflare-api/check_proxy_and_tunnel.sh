#!/usr/bin/env bash
set -euo pipefail

PROXY_KEY="${1:-team-demo-key}"
TUNNEL_URL="${2:-}"

echo "Checking llama-server health..."
curl --http1.1 http://127.0.0.1:8080/health
echo
echo

echo "Checking local proxy..."
curl --http1.1 http://127.0.0.1:5050/v1/chat/completions \
  -H "Authorization: Bearer $PROXY_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"nyx","messages":[{"role":"user","content":"Say hello in one sentence."}],"max_tokens":80,"temperature":0.5,"stream":false}'
echo
echo

if [[ -n "$TUNNEL_URL" ]]; then
  echo "Checking public tunnel..."
  curl --http1.1 "$TUNNEL_URL/v1/chat/completions" \
    -H "Authorization: Bearer $PROXY_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"nyx","messages":[{"role":"user","content":"Say hello in one sentence."}],"max_tokens":80,"temperature":0.5,"stream":false}'
  echo
  echo
fi

echo "Done."
