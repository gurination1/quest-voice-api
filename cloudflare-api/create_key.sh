#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/nyx/subtitle-vr-demo/cloudflare-api"
if [[ $# -lt 2 ]]; then
  echo "Usage: ./create_key.sh <key-value> <label> [shared|personal]"
  exit 1
fi

KEY_VALUE="$1"
LABEL="$2"
MODE="${3:-personal}"

cd "$ROOT"
printf '%s' "{\"id\":\"${LABEL}\",\"label\":\"${LABEL}\",\"mode\":\"${MODE}\",\"enabled\":true,\"features\":{\"cloud_stt\":true,\"cloud_reply\":true,\"cloud_tts\":true}}" > /tmp/quest_api_key.json
npx wrangler kv key put --remote --binding API_KEYS --path /tmp/quest_api_key.json "key:${KEY_VALUE}"
echo "Created remote key: ${KEY_VALUE}"
