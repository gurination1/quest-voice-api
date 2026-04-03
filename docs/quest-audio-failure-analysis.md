# Quest Audio Integration Failure Analysis

This note is the reference point for the local `proxy.py` audio extension and for Quest-side integration choices.

## What the proxy can and cannot control

The proxy can:

- accept recorded audio and run local STT
- synthesize speech server-side and return audio bytes
- enforce API-key auth and size limits
- normalize Quest/browser audio formats before STT

The proxy cannot:

- force a browser or Quest app to choose the headset microphone
- force a browser or Quest app to route playback to a specific speaker
- override headset permission prompts, iframe permission policy, or autoplay policy
- prevent another Quest app from holding audio focus

## Verified platform constraints

- `getUserMedia()` only works in secure contexts, and the browser may reject with `NotAllowedError` or `NotFoundError`. Source: MDN `MediaDevices.getUserMedia()` https://developer.mozilla.org/docs/Web/API/MediaDevices/getUserMedia
- `getUserMedia()` may also never resolve if the user ignores the permission prompt. Source: MDN `MediaDevices.getUserMedia()` https://developer.mozilla.org/docs/Web/API/MediaDevices/getUserMedia
- `setSinkId()` is secure-context only, can be blocked by `speaker-selection` permission policy, and requires user permission for non-default output devices. Source: MDN `HTMLMediaElement.setSinkId()` https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/setSinkId
- `SpeechRecognition` in the Web Speech API is not a safe baseline dependency across browsers, so browser-native recognition should be treated as opportunistic rather than guaranteed. Source: MDN `Web Speech API` https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API
- Media recording format support must be checked at runtime, and even a supported MIME type can still fail if device resources are constrained. Source: MDN `MediaRecorder.isTypeSupported()` https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/isTypeSupported_static
- Browser audio often needs a user gesture before Web Audio resumes cleanly. Source: MDN `AudioContext.resume()` and autoplay guide https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/resume and https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay
- FastAPI multipart upload handling requires `python-multipart`. Source: FastAPI request-files docs https://fastapi.tiangolo.com/tutorial/request-files/
- Piper requires a voice `.onnx` plus matching `.onnx.json`, and can emit WAV or raw PCM. Source: Rhasspy sample generator README https://github.com/rhasspy/piper-sample-generator

## Failure modes and mitigations

1. Microphone permission denied or never answered

- Symptom: no audio capture starts, no transcript arrives.
- Countermeasure: keep device STT as preferred mode, but expose `/v1/audio/transcriptions` as a fallback when Quest app can at least record or upload audio blobs later.

2. Browser is not in a secure context

- Symptom: `navigator.mediaDevices` is missing or `getUserMedia()` fails immediately.
- Countermeasure: use HTTPS for any browser-hosted Quest flow. For native Android/Quest app code, bypass browser capture and record through Android APIs.

3. Output device routing is inconsistent

- Symptom: speech plays on the wrong output or default route only.
- Countermeasure: assume default headset route. Treat explicit speaker selection as optional, not required, because `setSinkId()` support is limited and permission-gated.

4. Quest/Android audio focus conflicts

- Symptom: microphone capture stops, TTS ducks badly, or another app blocks recording.
- Countermeasure: make device STT and device TTS the primary path in the Quest app, request transient focus only, and keep server TTS as a fallback asset delivery path.

5. Unsupported or unstable recording MIME type

- Symptom: uploaded recordings fail or produce decode errors.
- Countermeasure: probe preferred types on-device with `MediaRecorder.isTypeSupported()` and server-side normalize everything through `ffmpeg` to mono 16 kHz WAV before Whisper.

6. Silence hallucinations or junk transcripts

- Symptom: Whisper returns filler or non-speech text.
- Countermeasure: enable `vad_filter`, disable `condition_on_previous_text`, and normalize input before transcription.

7. Large uploads stall or exhaust memory

- Symptom: long recordings time out or spike RAM.
- Countermeasure: enforce byte caps, reject oversize uploads early, and normalize in a temp directory.

8. TTS fails because voice assets are missing

- Symptom: synthesis endpoint errors on model load.
- Countermeasure: keep the voice model configurable with `NEO_TTS_VOICE`, default to a known local voice, return explicit 400 errors, and auto-download the default voice in `./start_local_api.sh`.

9. Client expects MP3 but server produces WAV

- Symptom: playback fails in strict clients.
- Countermeasure: support `wav`, `mp3`, `aac`, `opus`, and `pcm`, with `ffmpeg` handling the transcode.

10. Server side works but Quest hardware still misbehaves

- Symptom: STT/TTS endpoints pass tests but live headset UX is flaky.
- Countermeasure: instrument the Quest app separately for permission state, current audio route, focus changes, and recording errors. The proxy should not be blamed for device-layer focus bugs it cannot observe directly.

## Practical integration recommendation

Best default for Quest remains:

- `STT = device`
- `reply = cloud or local proxy`
- `TTS = device`

Use the new local proxy audio endpoints as controlled fallbacks and for remote teammates:

- `POST /v1/audio/transcriptions`
- `POST /v1/audio/speech`

That gives you a resilient system without over-committing to browser features that are still permission- and device-dependent.
