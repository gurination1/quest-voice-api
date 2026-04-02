# Team Handoff

## What teammates receive

- Base URL: your deployed Worker URL
- API key: shared or per-user key
- endpoint docs from `API_REFERENCE.md`

## Default client behavior

- device STT
- cloud reply
- device TTS

## Main endpoint

`POST /reply`

Recommended defaults:

- `stt = device`
- `reply = cloud`
- `tts = device`

Example request:

```json
{
  "transcript": "Hi Neo, introduce yourself in one sentence.",
  "history": [],
  "mode": "fast"
}
```

Example headers:

```text
Authorization: Bearer YOUR_APP_KEY
Content-Type: application/json
```

## Other endpoints

- `GET /health`
- `GET /config`
- `POST /session/respond`
- `POST /v1/chat/completions`

## What the host operator must keep running

- local `llama-server`
- local `proxy.py`
- Cloudflare Tunnel
- public Worker deployment

## Security

- share only app keys
- never share Cloudflare API tokens
- never commit `.env`

## If the host operator is offline

Cloud replies stop working.
Device STT and device TTS can still work locally inside the Quest app, depending on the app implementation.
