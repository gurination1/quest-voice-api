#!/usr/bin/env python3
"""
One-command local bring-up for the Quest Voice API proxy.

This script bootstraps local runtime prerequisites before importing proxy.py:
- ensures ffmpeg/ffprobe exist
- ensures a local API key exists
- downloads a default Piper voice if needed
- optionally starts the local llama-server via ~/assistant/genesis_llm.py
- starts the FastAPI proxy
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import httpx
import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
VOICE_DIR = RUNTIME_DIR / "voices"
JENNY_VOICE_PATH = Path("/home/nyx/piper_voices/en_GB-jenny_dioco-medium.onnx")
DEFAULT_VOICE_NAME = "en_US-lessac-medium"
DEFAULT_VOICE_PATH = VOICE_DIR / f"{DEFAULT_VOICE_NAME}.onnx"
DEFAULT_VOICE_CONFIG_PATH = VOICE_DIR / f"{DEFAULT_VOICE_NAME}.onnx.json"
DEFAULT_VOICE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true"
)
DEFAULT_VOICE_CONFIG_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json?download=true"
)
KEYS_FILE = PROJECT_ROOT / "keys.txt"


def ensure_command(name: str) -> None:
    if shutil.which(name):
        return
    raise SystemExit(f"Missing required command: {name}")


def extract_keys() -> list[str]:
    if not KEYS_FILE.exists():
        return []
    return [
        line.strip()
        for line in KEYS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def ensure_key() -> str:
    keys = extract_keys()
    if keys:
        return keys[0]

    from keygen import generate_key

    key = generate_key()
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    KEYS_FILE.write_text(
        f"# Generated {timestamp} by run_local_api.py\n{key}\n",
        encoding="utf-8",
    )
    return key


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def ensure_default_voice() -> Path:
    if JENNY_VOICE_PATH.exists() and Path(f"{JENNY_VOICE_PATH}.json").exists():
        return JENNY_VOICE_PATH

    if DEFAULT_VOICE_PATH.exists() and DEFAULT_VOICE_CONFIG_PATH.exists():
        return DEFAULT_VOICE_PATH

    print(f"Downloading default Piper voice to {DEFAULT_VOICE_PATH} ...", flush=True)
    download_file(DEFAULT_VOICE_URL, DEFAULT_VOICE_PATH)
    download_file(DEFAULT_VOICE_CONFIG_URL, DEFAULT_VOICE_CONFIG_PATH)
    return DEFAULT_VOICE_PATH


def upstream_ok(url: str) -> bool:
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{url.rstrip('/')}/health")
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def try_start_local_llm(upstream: str, model_key: str) -> bool:
    if not upstream.startswith("http://127.0.0.1:") and not upstream.startswith("http://localhost:"):
        return False

    assistant_dir = Path.home() / "assistant"
    genesis_llm = assistant_dir / "genesis_llm.py"
    if not genesis_llm.exists():
        return False

    if str(assistant_dir) not in sys.path:
        sys.path.insert(0, str(assistant_dir))

    try:
        from genesis_llm import start_model
    except Exception as exc:
        print(f"Automatic llama-server startup unavailable: {exc}", flush=True)
        return False

    print(f"Starting local llama-server via genesis_llm.start_model('{model_key}') ...", flush=True)
    start_model(model_key)
    return upstream_ok(upstream)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--llm-model", default=os.environ.get("NEO_LLM_MODEL", "9B"))
    parser.add_argument("--no-auto-llm", action="store_true")
    args = parser.parse_args()

    ensure_command("ffmpeg")
    ensure_command("ffprobe")

    os.environ.setdefault("LLAMA_HOST", "http://127.0.0.1:8080")
    voice_path = ensure_default_voice()
    os.environ.setdefault("NEO_TTS_VOICE", str(voice_path))
    os.environ.setdefault("NEO_PREWARM_AUDIO", "1")

    key = ensure_key()

    upstream = os.environ["LLAMA_HOST"]
    if not upstream_ok(upstream):
        if args.no_auto_llm:
            print(f"Upstream {upstream} is not healthy and auto-start is disabled.", flush=True)
        else:
            started = try_start_local_llm(upstream, args.llm_model)
            if not started:
                print(
                    f"Upstream {upstream} is still unavailable. "
                    "Audio endpoints will work, but chat proxying will return 502 until llama-server is up.",
                    flush=True,
                )

    import proxy

    print(f"Quest Voice API local key: {key}", flush=True)
    print(f"Default Piper voice: {voice_path}", flush=True)
    print(f"Upstream chat host: {upstream}", flush=True)
    uvicorn.run(proxy.app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
