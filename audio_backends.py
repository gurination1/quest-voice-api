import io
import os
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel
from piper.config import SynthesisConfig
from piper.voice import PiperVoice


PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
JENNY_VOICE_PATH = Path("/home/nyx/piper_voices/en_GB-jenny_dioco-medium.onnx")
DEFAULT_VOICE_NAME = "en_US-lessac-medium"
DEFAULT_RUNTIME_VOICE = RUNTIME_DIR / "voices" / f"{DEFAULT_VOICE_NAME}.onnx"
DEFAULT_PIPER_MODEL = os.environ.get(
    "NEO_TTS_VOICE",
    str(JENNY_VOICE_PATH if JENNY_VOICE_PATH.exists() else DEFAULT_RUNTIME_VOICE),
)
DEFAULT_WHISPER_MODEL = os.environ.get("NEO_STT_MODEL", "small.en")
MAX_AUDIO_BYTES = int(os.environ.get("NEO_MAX_AUDIO_BYTES", str(25 * 1024 * 1024)))
MAX_TTS_CHARS = int(os.environ.get("NEO_MAX_TTS_CHARS", "4096"))
FFMPEG_TIMEOUT_SECONDS = int(os.environ.get("NEO_FFMPEG_TIMEOUT_SECONDS", "120"))
STT_BEAM_SIZE = int(os.environ.get("NEO_STT_BEAM_SIZE", "1"))
STT_BEST_OF = int(os.environ.get("NEO_STT_BEST_OF", str(max(STT_BEAM_SIZE, 1))))
STT_VAD_MIN_SILENCE_MS = int(os.environ.get("NEO_STT_VAD_MIN_SILENCE_MS", "500"))
TTS_NOISE_SCALE = float(os.environ.get("NEO_TTS_NOISE_SCALE", "0.667"))
TTS_NOISE_W_SCALE = float(os.environ.get("NEO_TTS_NOISE_W_SCALE", "0.8"))
TTS_LENGTH_SCALE = float(os.environ.get("NEO_TTS_LENGTH_SCALE", "1.0"))


class AudioBackendError(RuntimeError):
    pass


@dataclass
class TranscriptionResult:
    text: str
    language: str | None
    duration: float | None
    segments: list[dict[str, Any]]


def _detect_whisper_runtime() -> tuple[str, str]:
    try:
        import torch

        if torch.cuda.is_available():
            return ("cuda", os.environ.get("NEO_STT_COMPUTE_TYPE", "float16"))
    except Exception:
        pass
    return ("cpu", os.environ.get("NEO_STT_COMPUTE_TYPE", "int8"))


@lru_cache(maxsize=1)
def get_whisper_model() -> WhisperModel:
    device, compute_type = _detect_whisper_runtime()
    return WhisperModel(DEFAULT_WHISPER_MODEL, device=device, compute_type=compute_type)


@lru_cache(maxsize=4)
def get_piper_voice(model_path: str) -> PiperVoice:
    config_path = Path(f"{model_path}.json")
    if not Path(model_path).exists():
        raise AudioBackendError(
            f"missing Piper voice model: {model_path}. "
            "Run ./start_local_api.sh so the default voice is downloaded automatically, "
            "or set NEO_TTS_VOICE to a valid .onnx file."
        )
    if not config_path.exists():
        raise AudioBackendError(
            f"missing Piper voice config: {config_path}. "
            "Piper requires both the .onnx file and the matching .onnx.json file."
        )
    return PiperVoice.load(model_path)


def _ffmpeg_normalize_to_wav(input_path: str, output_path: str) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        output_path,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise AudioBackendError("ffmpeg is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioBackendError("ffmpeg normalization timed out") from exc
    if result.returncode != 0:
        raise AudioBackendError(f"ffmpeg normalization failed: {result.stderr.strip()}")


def _ffprobe_duration(path: str) -> float | None:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def transcribe_bytes(
    audio_bytes: bytes,
    *,
    filename: str = "upload.bin",
    language: str | None = None,
    prompt: str | None = None,
    temperature: float = 0.0,
    word_timestamps: bool = False,
) -> TranscriptionResult:
    if not audio_bytes:
        raise AudioBackendError("audio payload is empty")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise AudioBackendError(
            f"audio payload exceeds limit of {MAX_AUDIO_BYTES // (1024 * 1024)} MB"
        )

    suffix = Path(filename).suffix or ".bin"
    with tempfile.TemporaryDirectory(prefix="neo-audio-") as temp_dir:
        source_path = os.path.join(temp_dir, f"input{suffix}")
        normalized_path = os.path.join(temp_dir, "normalized.wav")
        with open(source_path, "wb") as handle:
            handle.write(audio_bytes)

        _ffmpeg_normalize_to_wav(source_path, normalized_path)
        duration = _ffprobe_duration(normalized_path)

        segments, info = get_whisper_model().transcribe(
            normalized_path,
            language=language,
            task="transcribe",
            beam_size=STT_BEAM_SIZE,
            best_of=STT_BEST_OF,
            temperature=temperature,
            condition_on_previous_text=False,
            initial_prompt=prompt,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": STT_VAD_MIN_SILENCE_MS},
            word_timestamps=word_timestamps,
            no_speech_threshold=0.6,
        )
        collected_segments = []
        text_parts: list[str] = []
        for segment in segments:
            entry: dict[str, Any] = {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
            }
            if word_timestamps and getattr(segment, "words", None):
                entry["words"] = [
                    {
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                        "probability": word.probability,
                    }
                    for word in segment.words
                ]
            collected_segments.append(entry)
            if entry["text"]:
                text_parts.append(entry["text"])

        return TranscriptionResult(
            text=" ".join(text_parts).strip(),
            language=getattr(info, "language", None),
            duration=duration,
            segments=collected_segments,
        )


def _pcm_to_wav(audio_bytes: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_bytes)
    return buffer.getvalue()


def _ffmpeg_transcode(wav_bytes: bytes, response_format: str) -> bytes:
    format_map = {
        "mp3": ["-f", "mp3"],
        "aac": ["-f", "adts"],
        "flac": ["-f", "flac"],
        "opus": ["-c:a", "libopus", "-f", "ogg"],
    }
    args = format_map.get(response_format)
    if args is None:
        raise AudioBackendError(f"unsupported response_format: {response_format}")

    command = ["ffmpeg", "-y", "-i", "pipe:0", *args, "pipe:1"]
    try:
        result = subprocess.run(
            command,
            input=wav_bytes,
            capture_output=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise AudioBackendError("ffmpeg is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioBackendError("ffmpeg audio transcode timed out") from exc
    if result.returncode != 0:
        raise AudioBackendError("ffmpeg audio transcode failed")
    return result.stdout


def synthesize_speech(
    text: str,
    *,
    voice_model: str | None = None,
    response_format: str = "mp3",
) -> tuple[bytes, str]:
    clean_text = (text or "").strip()
    if not clean_text:
        raise AudioBackendError("input text is required")
    if len(clean_text) > MAX_TTS_CHARS:
        raise AudioBackendError(f"input text exceeds limit of {MAX_TTS_CHARS} characters")

    voice = get_piper_voice(voice_model or DEFAULT_PIPER_MODEL)
    synth_config = SynthesisConfig(
        length_scale=TTS_LENGTH_SCALE,
        noise_scale=TTS_NOISE_SCALE,
        noise_w_scale=TTS_NOISE_W_SCALE,
    )
    audio_chunks = []
    for chunk in voice.synthesize(clean_text, syn_config=synth_config):
        audio_chunks.append(chunk.audio_int16_bytes)
    if not audio_chunks:
        raise AudioBackendError("piper returned no audio")

    wav_bytes = _pcm_to_wav(b"".join(audio_chunks), voice.config.sample_rate)
    if response_format == "wav":
        return wav_bytes, "audio/wav"
    if response_format == "pcm":
        return b"".join(audio_chunks), "audio/L16"

    transcoded = _ffmpeg_transcode(wav_bytes, response_format)
    media_type = {
        "mp3": "audio/mpeg",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "opus": "audio/ogg",
    }[response_format]
    return transcoded, media_type


def warm_audio_backends(*, preload_stt: bool = False) -> dict[str, Any]:
    details: dict[str, Any] = {
        "tts_voice": DEFAULT_PIPER_MODEL,
        "stt_model": DEFAULT_WHISPER_MODEL,
    }

    voice = get_piper_voice(DEFAULT_PIPER_MODEL)
    details["tts_sample_rate"] = voice.config.sample_rate

    if preload_stt:
        model = get_whisper_model()
        details["stt_device"] = getattr(model, "device", None)

    return details
