# Quest Voice API

Cloudflare Worker backend for a Meta Quest 2 voice-avatar app.

## What it provides

- API key auth
- Shared-key and per-user key support
- Cloud reply endpoint
- Optional cloud STT endpoint
- Optional cloud TTS endpoint
- OpenAI-compatible `/v1/chat/completions`
- App-friendly `/session/respond`
- Optional routing to your own `llama-server` / OpenAI-compatible upstream

## Why this shape

The Quest app can default to:

- `Device STT`
- `Cloud Reply`
- `Device TTS`

while still exposing:

- `Cloud STT`
- `Cloud TTS`

for fallback or centralized operation.

## Endpoints

- `GET /health`
- `GET /config`
- `POST /reply`
- `POST /stt`
- `POST /tts`
- `POST /session/respond`
- `POST /v1/chat/completions`

## Request auth

Use either:

- `Authorization: Bearer YOUR_KEY`
- `x-api-key: YOUR_KEY`

## Deploy

1. `cd cloudflare-api`
2. `npm install`
3. `npx wrangler kv namespace create API_KEYS`
4. Put the returned namespace id into [`wrangler.jsonc`](wrangler.jsonc)
5. `npx wrangler login`
6. `npx wrangler deploy`

## Use the exact same Neo Qwen 9B model

If you want the online API to use the same local Neo model instead of Workers AI, set these vars in [`wrangler.jsonc`](wrangler.jsonc):

- `UPSTREAM_MODE`: `openai_proxy`
- `UPSTREAM_OPENAI_BASE_URL`: your public proxy URL
- `UPSTREAM_OPENAI_API_KEY`: key accepted by that proxy
- `UPSTREAM_OPENAI_MODEL`: `nyx`

The intended upstream is your local `proxy.py`, which already forwards OpenAI-compatible requests to your local `llama-server`.

That preserves the exact Qwen 3.5 9B behavior used by Neo, as long as the machine hosting `llama-server` stays online.

## Create keys

Store keys in KV like:

Key:

`key:YOUR_SECRET_KEY`

Value:

```json
{
  "id": "team-shared",
  "label": "Hackathon Team",
  "mode": "shared",
  "enabled": true,
  "features": {
    "cloud_stt": true,
    "cloud_reply": true,
    "cloud_tts": true
  }
}
```

Or a per-user key:

```json
{
  "id": "user-alex",
  "label": "Alex",
  "mode": "personal",
  "enabled": true,
  "features": {
    "cloud_stt": true,
    "cloud_reply": true,
    "cloud_tts": false
  }
}
```

## Important platform note

For highest reliability on Quest 2, keep mic capture and default speech playback inside the existing Quest app. Use this backend mainly for cloud reply and optional cloud STT/TTS.
