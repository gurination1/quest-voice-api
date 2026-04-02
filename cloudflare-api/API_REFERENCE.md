# API Reference

## Auth

Use either:

```text
Authorization: Bearer YOUR_APP_KEY
```

or:

```text
x-api-key: YOUR_APP_KEY
```

## `GET /health`

Checks whether the public Worker is alive.

Example response:

```json
{
  "ok": true,
  "status": "ok"
}
```

## `GET /config`

Returns allowed features and recommended defaults for the calling key.

## `POST /reply`

Primary endpoint for default Quest integration.

Request:

```json
{
  "transcript": "Hi Neo, introduce yourself in one sentence.",
  "history": [],
  "mode": "fast"
}
```

Response:

```json
{
  "ok": true,
  "transcript": "Hi Neo, introduce yourself in one sentence.",
  "reply": "I am Neo, your intelligent companion designed to enhance your Meta Quest 2 experience with immersive interactions.",
  "modes": {
    "stt": "device",
    "reply": "cloud",
    "tts": "device"
  },
  "fallbacks": []
}
```

## `POST /session/respond`

For app clients that want one structured endpoint.

Request:

```json
{
  "transcript": "What should I say in the demo?",
  "history": [],
  "stt_mode": "device",
  "reply_mode": "cloud",
  "tts_mode": "device"
}
```

## `POST /stt`

Optional cloud speech-to-text path.

Expects multipart form-data with `audio`.

## `POST /tts`

Optional cloud text-to-speech path.

Request:

```json
{
  "text": "Hello from Neo",
  "voice": "default"
}
```

## `POST /v1/chat/completions`

OpenAI-compatible path for existing chat clients.

Request:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Say hello in one sentence."
    }
  ],
  "max_tokens": 80,
  "temperature": 0.5
}
```

## Recommended Quest defaults

- `stt = device`
- `reply = cloud`
- `tts = device`
