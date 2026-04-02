import os
from typing import Literal

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


UPSTREAM_MODE = os.getenv("UPSTREAM_MODE", "openai").lower()
UPSTREAM_URL = os.getenv("UPSTREAM_URL", "https://api.openai.com/v1/responses")
UPSTREAM_API_KEY = os.getenv("UPSTREAM_API_KEY", "")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "default")

app = FastAPI(title="VR Caption Cloud Backend", version="1.0.0")


class ReplyRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=1000)
    history: list[str] = Field(default_factory=list, max_length=12)
    mode: str | None = None


class ReplyResponse(BaseModel):
    reply: str
    provider: str


def verify_api_key(authorization: str | None):
    if not BACKEND_API_KEY:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != BACKEND_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


@app.get("/health")
async def health():
    return {"status": "ok", "provider": UPSTREAM_MODE}


@app.post("/reply", response_model=ReplyResponse)
async def reply(request: ReplyRequest, authorization: str | None = Header(default=None)):
    verify_api_key(authorization)

    transcript = request.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is required")

    if UPSTREAM_MODE == "llama":
        text = await call_llama_server(transcript, request.history)
        return ReplyResponse(reply=text, provider="llama")

    text = await call_openai_responses(transcript, request.history)
    return ReplyResponse(reply=text, provider="openai")


async def call_openai_responses(transcript: str, history: list[str]) -> str:
    if not UPSTREAM_API_KEY:
        return offline_reply(transcript)

    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are a reply engine for a live subtitle app used in a VR demo. "
                            "Keep replies brief, clear, and easy to read on screen. "
                            "Answer in one or two short sentences."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"Conversation history:\n{format_history(history)}\n\n"
                            f"Latest transcript:\n{transcript}"
                        ),
                    }
                ],
            },
        ],
        "max_output_tokens": 90,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            UPSTREAM_URL,
            headers={
                "Authorization": f"Bearer {UPSTREAM_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    for item in data.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    return offline_reply(transcript)


async def call_llama_server(transcript: str, history: list[str]) -> str:
    payload = {
        "model": LLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a reply engine for a live subtitle app used in a VR demo. "
                    "Keep replies brief, clear, and easy to read on screen. "
                    "Answer in one or two short sentences."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Conversation history:\n{format_history(history)}\n\n"
                    f"Latest transcript:\n{transcript}"
                ),
            },
        ],
        "temperature": 0.6,
        "max_tokens": 90,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{UPSTREAM_URL.rstrip('/')}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
        or offline_reply(transcript)
    )


def format_history(history: list[str]) -> str:
    if not history:
        return "No previous turns."
    return "\n".join(history[-6:])


def offline_reply(transcript: str) -> str:
    return f'Heard "{transcript}". The remote model is not configured yet, but the app is connected.'
