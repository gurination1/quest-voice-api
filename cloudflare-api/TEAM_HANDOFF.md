# Team Handoff

## What teammates receive

- Base URL: your deployed Worker URL
- API key: shared or per-user key

## Default client behavior

- device STT
- cloud reply
- device TTS

## Main endpoint

`POST /reply`

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
