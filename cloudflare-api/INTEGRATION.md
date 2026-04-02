# Quest Integration Contract

This backend is designed for an existing Meta Quest 2 app that already renders the 3D model.

## Recommended default routing

- `STT`: device
- `Reply`: cloud
- `TTS`: device

## Auth

Send one of:

- `Authorization: Bearer YOUR_KEY`
- `x-api-key: YOUR_KEY`

## Startup flow

1. Call `GET /health`
2. Call `GET /config`
3. Detect local device STT and TTS availability
4. Lock initial mode to:
   - `device` STT if available, otherwise `cloud`
   - `cloud` reply
   - `device` TTS if available, otherwise `cloud`

## Core request

Use `POST /session/respond` for the main interaction loop.

Example:

```json
{
  "transcript": "What should I say in the demo?",
  "history": [
    "User: Hello",
    "Assistant: Hi, I am ready."
  ],
  "stt_mode": "device",
  "reply_mode": "cloud",
  "tts_mode": "device",
  "voice": "default"
}
```

Response:

```json
{
  "ok": true,
  "transcript": "What should I say in the demo?",
  "reply": "Say that the avatar hears you in real time and answers through the cloud API.",
  "tts_audio": null,
  "modes": {
    "stt": "device",
    "reply": "cloud",
    "tts": "device"
  },
  "fallbacks": []
}
```

## Fallback rules

- If device STT fails, switch to `POST /stt`
- If cloud reply fails, keep subtitles visible and show a retry affordance
- If device TTS fails, switch to `POST /tts` if the key allows cloud TTS
- If both TTS paths fail, keep reply text visible and continue interaction

## Audio behavior guidance

For best coexistence with other Quest audio:

- Use speech-oriented audio attributes
- Request transient ducking instead of permanent focus
- Keep spoken replies short
- Never block subtitle display on TTS completion

## OpenAI-compatible mode

If the existing app already uses an OpenAI-style client, it can call:

- `POST /v1/chat/completions`

with the same bearer key.
