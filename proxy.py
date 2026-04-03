"""
Local auth proxy for Quest Voice API.

It keeps the existing OpenAI-compatible chat pass-through and adds optional
local STT/TTS endpoints for Quest and remote teammates.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from audio_backends import (
    AudioBackendError,
    DEFAULT_PIPER_MODEL,
    DEFAULT_WHISPER_MODEL,
    synthesize_speech,
    transcribe_bytes,
    warm_audio_backends,
)


def _load_env_file() -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


_load_env_file()


def load_keys() -> set[str]:
    env_keys = os.environ.get("NEO_API_KEYS", "")
    if env_keys:
        return {k.strip() for k in env_keys.split(",") if k.strip()}

    keys_file = os.path.join(os.path.dirname(__file__), "keys.txt")
    if os.path.exists(keys_file):
        with open(keys_file, encoding="utf-8") as handle:
            return {
                line.strip()
                for line in handle
                if line.strip() and not line.lstrip().startswith("#")
            }

    print("WARNING: No keys found. Run python3 keygen.py first.")
    return set()


VALID_KEYS: set[str] = load_keys()
LLAMA_BASE = os.environ.get("LLAMA_HOST", "http://localhost:8080")
UPSTREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=60.0)
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("NEO_CORS_ALLOW_ORIGINS", "*").split(",")
    if origin.strip()
]
DEFAULT_ASSISTANT_MODEL = os.environ.get("NEO_ASSISTANT_MODEL", "nyx")
DEFAULT_SYSTEM_PROMPT = os.environ.get(
    "NEO_DEFAULT_SYSTEM_PROMPT",
    (
        "You are Neo, a voice-first AI assistant for a Meta Quest experience. "
        "Never say you are Qwen, a language model, or an AI model unless the user directly asks about the underlying model. "
        "If asked who you are, say you are Neo. "
        "Speak naturally in short, clear sentences that sound good when read aloud. "
        "Do not use markdown, bullet points, emojis, or stage directions. "
        "Do not read punctuation names aloud. "
        "Keep answers concise and helpful."
    ),
)
ENABLE_DEFAULT_SYSTEM_PROMPT = os.environ.get("NEO_ENABLE_DEFAULT_SYSTEM_PROMPT", "1") == "1"
SANITIZE_TTS_INPUT = os.environ.get("NEO_TTS_SANITIZE_INPUT", "1") == "1"

app = FastAPI(title="Quest Voice API Local Proxy", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["content-type", "content-length"],
    max_age=86400,
)


def verify(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token not in VALID_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")


def _json_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"message": message}})


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _timestamp_granularities(form: Any) -> set[str]:
    values = form.getlist("timestamp_granularities[]")
    if not values:
        single = form.get("timestamp_granularities")
        if single:
            values = [single]
    return {str(value).strip().lower() for value in values if str(value).strip()}


def _format_timestamp(seconds: float) -> str:
    total_ms = max(int(round(seconds * 1000)), 0)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    return _format_timestamp(seconds).replace(",", ".")


def _segments_to_srt(segments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.extend(
            [
                str(index),
                f"{_format_timestamp(segment['start'])} --> {_format_timestamp(segment['end'])}",
                segment["text"],
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _segments_to_vtt(segments: list[dict[str, Any]]) -> str:
    lines = ["WEBVTT", ""]
    for segment in segments:
        lines.extend(
            [
                f"{_format_timestamp_vtt(segment['start'])} --> {_format_timestamp_vtt(segment['end'])}",
                segment["text"],
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _ensure_default_chat_identity(body: bytes) -> tuple[bytes, bool]:
    if not ENABLE_DEFAULT_SYSTEM_PROMPT:
        return body, False

    try:
        payload = json.loads(body)
    except Exception:
        return body, False

    messages = payload.get("messages")
    if not isinstance(messages, list):
        return body, False

    has_system_message = any(
        isinstance(message, dict) and message.get("role") == "system"
        for message in messages
    )
    changed = False

    if not payload.get("model"):
        payload["model"] = DEFAULT_ASSISTANT_MODEL
        changed = True

    if not has_system_message:
        payload["messages"] = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}, *messages]
        changed = True

    if not changed:
        return body, False

    return json.dumps(payload).encode("utf-8"), True


def _sanitize_tts_text(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return cleaned

    cleaned = re.sub(r"```.*?```", " ", cleaned, flags=re.S)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", cleaned)
    cleaned = re.sub(r"[*_#~>\[\]\(\)]", " ", cleaned)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"\bQwen\b", "Neo", cleaned, flags=re.I)
    cleaned = re.sub(r"[^\x00-\x7F]+", " ", cleaned)
    cleaned = re.sub(r"[!?.;,:\-]{2,}", ".", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" .")
    return cleaned


async def _proxy_json_request(path: str, body: bytes) -> Response:
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        try:
            resp = await client.post(
                f"{LLAMA_BASE}{path}",
                content=body,
                headers={"Content-Type": "application/json"},
            )
        except httpx.RequestError as exc:
            return _json_error(502, f"upstream request failed: {exc}")

    content_type = resp.headers.get("content-type", "application/json")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=content_type.split(";", 1)[0],
        headers={"content-type": content_type},
    )


@app.on_event("startup")
async def startup_event() -> None:
    if os.environ.get("NEO_PREWARM_AUDIO", "1") == "1":
        preload_stt = os.environ.get("NEO_PRELOAD_STT", "0") == "1"
        try:
            await asyncio.to_thread(warm_audio_backends, preload_stt=preload_stt)
        except Exception as exc:
            print(f"Audio prewarm skipped: {exc}")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "upstream": LLAMA_BASE,
        "keys_loaded": len(VALID_KEYS),
        "audio": {
            "stt_model": DEFAULT_WHISPER_MODEL,
            "tts_voice": DEFAULT_PIPER_MODEL,
        },
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: str = Header(default=None)):
    verify(authorization)
    body = await request.body()
    body, _ = _ensure_default_chat_identity(body)
    headers = {"Content-Type": "application/json"}

    try:
        payload = json.loads(body)
        stream = payload.get("stream", False)
    except Exception:
        stream = False

    if stream:
        client = httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT)
        upstream_request = client.build_request(
            "POST",
            f"{LLAMA_BASE}/v1/chat/completions",
            content=body,
            headers=headers,
        )
        try:
            upstream_response = await client.send(upstream_request, stream=True)
        except httpx.RequestError as exc:
            await client.aclose()
            return _json_error(502, f"upstream request failed: {exc}")
        return StreamingResponse(
            upstream_response.aiter_bytes(),
            media_type=upstream_response.headers.get("content-type", "text/event-stream"),
            status_code=upstream_response.status_code,
            background=BackgroundTask(
                _close_streaming_resources,
                upstream_response,
                client,
            ),
        )

    return await _proxy_json_request("/v1/chat/completions", body)


async def _close_streaming_resources(
    response: httpx.Response,
    client: httpx.AsyncClient,
) -> None:
    await response.aclose()
    await client.aclose()


@app.post("/v1/completions")
async def completions(request: Request, authorization: str = Header(default=None)):
    verify(authorization)
    body = await request.body()
    return await _proxy_json_request("/v1/completions", body)


@app.post("/v1/audio/transcriptions")
@app.post("/stt")
async def audio_transcriptions(
    request: Request,
    authorization: str = Header(default=None),
):
    verify(authorization)
    try:
        form = await request.form()
        upload = form.get("file") or form.get("audio")
        if upload is None:
            return _json_error(400, "multipart field 'file' or 'audio' is required")
        payload = await upload.read()
        response_format = str(form.get("response_format") or "json")
        timestamp_granularities = _timestamp_granularities(form)
        language = str(form.get("language")) if form.get("language") else None
        prompt = str(form.get("prompt")) if form.get("prompt") else None
        temperature = _coerce_float(form.get("temperature"), 0.0)
        result = await asyncio.to_thread(
            transcribe_bytes,
            payload,
            filename=getattr(upload, "filename", None) or "audio.bin",
            language=language,
            prompt=prompt,
            temperature=temperature,
            word_timestamps=response_format == "verbose_json"
            and ("word" in timestamp_granularities or not timestamp_granularities),
        )
    except AudioBackendError as exc:
        return _json_error(400, str(exc))
    except Exception as exc:
        return _json_error(500, f"transcription failed: {exc}")

    if response_format == "text":
        return Response(content=result.text, media_type="text/plain")

    if response_format == "verbose_json":
        return JSONResponse(
            {
                "task": "transcribe",
                "language": result.language,
                "duration": result.duration,
                "text": result.text,
                "segments": result.segments,
            }
        )

    if response_format == "srt":
        return Response(content=_segments_to_srt(result.segments), media_type="text/plain")

    if response_format == "vtt":
        return Response(content=_segments_to_vtt(result.segments), media_type="text/vtt")

    return JSONResponse({"text": result.text, "language": result.language, "duration": result.duration})


@app.post("/v1/audio/speech")
@app.post("/tts")
async def audio_speech(
    request: Request,
    authorization: str = Header(default=None),
):
    verify(authorization)
    try:
        body = await request.json()
    except Exception:
        return _json_error(400, "invalid JSON body")

    text = body.get("input") or body.get("text")
    response_format = (body.get("response_format") or "mp3").lower()
    voice = body.get("voice_model") or body.get("voice")
    if SANITIZE_TTS_INPUT and isinstance(text, str):
        text = _sanitize_tts_text(text)

    try:
        audio_bytes, media_type = await asyncio.to_thread(
            synthesize_speech,
            text,
            voice_model=voice,
            response_format=response_format,
        )
    except AudioBackendError as exc:
        return _json_error(400, str(exc))
    except Exception as exc:
        return _json_error(500, f"speech synthesis failed: {exc}")

    return Response(content=audio_bytes, media_type=media_type)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    if not VALID_KEYS:
        print("No API keys loaded. Run python3 keygen.py to generate one, then restart.")
        sys.exit(1)

    print(f"Quest Voice API proxy running on {args.host}:{args.port}")
    print(f"Upstream llama.cpp: {LLAMA_BASE}")
    print(f"Keys loaded: {len(VALID_KEYS)}")
    print(f"Local STT model: {DEFAULT_WHISPER_MODEL}")
    print(f"Local TTS voice: {DEFAULT_PIPER_MODEL}")
    uvicorn.run(app, host=args.host, port=args.port)
