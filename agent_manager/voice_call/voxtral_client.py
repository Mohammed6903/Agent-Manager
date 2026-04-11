"""Voxtral (Mistral) STT + TTS client.

Wraps Mistral's /v1/audio/speech (TTS) and /v1/audio/transcriptions (STT)
endpoints. Three layers of TTS API:

1. ``_iter_voxtral_tts_float32`` (private) — the raw SSE reader.
   Yields one numpy float32 array per ``speech.audio.delta`` event.
   This is the only function that talks HTTP/SSE for TTS.

2. ``stream_tts_g711`` (public) — the streaming TTS pipeline.
   Async generator that yields fixed-size G.711 frames as Mistral chunks
   arrive. Internally: float32 → stateful 24→8 kHz downsampler → dither
   → int16 → G.711 encode → frame splitter. The streaming downsampler is
   constructed per-call, never shared.

3. ``synthesize_tts`` (public, backward compatible) — buffered convenience
   wrapper. Collects all chunks, returns a single bytes buffer at the
   requested sample rate. Used by anything that wants the full audio
   up-front (offline tests, smoke scripts, etc.).

Key gotchas (from reference_mistral_audio_api.md):

- ``response_format=pcm`` returns FLOAT32 LE samples in [-1, 1], NOT
  int16 like every other audio API. We sanity-check on first delta and
  log a loud warning if Mistral ever silently changes this.

- The streaming TTS response is SSE with two event types:
    event: speech.audio.delta    → {"audio_data": "<base64 float32>"}
    event: speech.audio.done

STT is unchanged from the previous implementation — see ``transcribe_pcm``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import AsyncIterator, Optional

import httpx
import numpy as np

from ..config import settings
from .audio_codec import (
    SoxrStreamDownsampler,
    TELNYX_PCM_SAMPLE_RATE,
    VOXTRAL_TTS_SAMPLE_RATE,
    encode_g711,
    float32_to_int16_dither,
    pcm_to_wav,
    resample_pcm,
    silence_byte_for_encoding,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.mistral.ai/v1"
TTS_TIMEOUT = httpx.Timeout(30.0, connect=15.0)
# STT uploads can be large (30+ seconds of PCM = ~1 MB WAV) and Mistral's
# transcription endpoint takes time to process. 60 s read timeout with a
# generous connect timeout for the India→EU hop.
STT_TIMEOUT = httpx.Timeout(60.0, connect=15.0)

# How long we wait between SSE chunks before declaring a stream stalled.
# Mistral's first delta usually arrives within ~500-700 ms; subsequent
# deltas are much faster. 10 s is a generous "something went wrong" cap.
TTS_CHUNK_TIMEOUT_S = 10.0

# Whether we've already logged a "Mistral returned int16, not float32" warning
# in this process. We log it loudly once, then suppress to avoid log spam.
_FORMAT_WARNING_LOGGED = False


class VoxtralError(Exception):
    pass


# ── Streaming TTS ────────────────────────────────────────────────────────────


async def _iter_voxtral_tts_float32(
    text: str,
    *,
    voice_id: str,
    api_key: str,
    model: str,
) -> AsyncIterator[np.ndarray]:
    """Yield float32 numpy arrays at 24 kHz as SSE deltas arrive.

    Private. The only function that talks HTTP/SSE for TTS — both
    ``stream_tts_g711`` and ``synthesize_tts`` consume this iterator.

    Behavior:
    - One retry on httpx.TransportError / httpx.ReadTimeout during the
      INITIAL CONNECT only. Mid-stream errors fail-fast (no retry) so we
      never replay text halfway through.
    - Per-chunk SSE timeout via asyncio.wait_for. If the stream stalls
      mid-utterance, raises VoxtralError.
    - Sanity check on first delta: if the audio_data magnitude looks like
      int16 (>1.5), log a loud warning ONCE — Mistral may have changed
      the undocumented float32 format.
    """
    body = {
        "model": model,
        "input": text,
        "voice_id": voice_id,
        "response_format": "pcm",
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    # Single retry on initial connect failures only.
    async def _open_stream(client: httpx.AsyncClient):
        return client.stream(
            "POST",
            f"{BASE_URL}/audio/speech",
            headers=headers,
            json=body,
        )

    async with httpx.AsyncClient(timeout=TTS_TIMEOUT) as client:
        try:
            stream_cm = await _open_stream(client)
        except (httpx.TransportError, httpx.ReadTimeout) as exc:
            logger.warning("Voxtral TTS connect failed (retrying once): %s", exc)
            stream_cm = await _open_stream(client)

        async with stream_cm as resp:
            if resp.status_code >= 400:
                body_text = await resp.aread()
                raise VoxtralError(
                    f"Voxtral TTS HTTP {resp.status_code}: "
                    f"{body_text.decode('utf-8', 'replace')[:500]}"
                )

            sse_iter = _iter_sse_events(resp)
            first_delta_seen = False
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(
                            sse_iter.__anext__(), timeout=TTS_CHUNK_TIMEOUT_S
                        )
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        raise VoxtralError(
                            f"Voxtral TTS stream stalled (>{TTS_CHUNK_TIMEOUT_S}s with no delta)"
                        )

                    data_str = event.get("data")
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    ev_type = data.get("type") or event.get("event")

                    if ev_type == "speech.audio.delta":
                        audio_b64 = data.get("audio_data")
                        if not audio_b64:
                            continue
                        raw = base64.b64decode(audio_b64)
                        # Decode as float32 LE.
                        samples = np.frombuffer(raw, dtype="<f4")
                        if samples.size == 0:
                            continue

                        # First-delta sanity check.
                        if not first_delta_seen:
                            first_delta_seen = True
                            global _FORMAT_WARNING_LOGGED
                            peak = float(np.max(np.abs(samples))) if samples.size else 0.0
                            if peak > 1.5 and not _FORMAT_WARNING_LOGGED:
                                _FORMAT_WARNING_LOGGED = True
                                logger.warning(
                                    "Voxtral TTS first delta has out-of-[-1,1] "
                                    "samples (peak=%.3f) — Mistral may have "
                                    "changed the undocumented PCM format from "
                                    "float32 to int16. Audio quality will be "
                                    "wrong until this is fixed.",
                                    peak,
                                )

                        yield samples
                    elif ev_type == "speech.audio.done":
                        break
            finally:
                # Make sure the SSE iterator's resources are cleaned up
                # even if the consumer cancels mid-stream (future barge-in).
                aclose = getattr(sse_iter, "aclose", None)
                if aclose is not None:
                    try:
                        await aclose()
                    except Exception:
                        pass


async def stream_tts_g711(
    text: str,
    *,
    encoding: str,
    frame_ms: int = 20,
    voice_id: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> AsyncIterator[bytes]:
    """Stream Voxtral TTS as ready-to-send G.711 frames.

    Yields fixed-size G.711 frames (1 byte per sample at 8 kHz, so
    ``frame_ms * 8`` bytes per frame; 160 bytes for the standard 20 ms
    telephony frame). Frames arrive as fast as Mistral generates audio,
    so the caller can begin sending them to Telnyx within ~500 ms-1 s
    of the request — much faster than the previous "buffer everything,
    then process" path that took 2-4 s.

    Args:
        text: Text to synthesize.
        encoding: Telnyx-negotiated G.711 codec, ``"PCMU"`` or ``"PCMA"``.
        frame_ms: Frame duration in milliseconds. Standard telephony is 20.
        voice_id, api_key, model: Optional overrides; defaults from settings.

    Raises:
        VoxtralError: on missing config, HTTP errors, or stream stalls.
    """
    api_key = api_key or settings.MISTRAL_API_KEY
    voice_id = voice_id or settings.VOXTRAL_VOICE_ID
    model = model or settings.VOXTRAL_TTS_MODEL

    if not api_key:
        raise VoxtralError("MISTRAL_API_KEY not configured")
    if not voice_id:
        raise VoxtralError("voice_id required")

    # G.711 at 8 kHz: 1 byte per sample → 8 bytes per ms.
    bytes_per_ms = 8
    frame_bytes = bytes_per_ms * frame_ms

    # libsoxr "VHQ" stream resampler — same backend pipecat uses for
    # production Telnyx voice agents. Maintains internal history across
    # SSE chunks so there are no boundary artifacts.
    downsampler = SoxrStreamDownsampler(
        in_rate=VOXTRAL_TTS_SAMPLE_RATE,
        out_rate=TELNYX_PCM_SAMPLE_RATE,
    )
    rng = np.random.default_rng()
    leftover = bytearray()

    async for f32_chunk in _iter_voxtral_tts_float32(
        text, voice_id=voice_id, api_key=api_key, model=model
    ):
        # 24 kHz float32 → 24 kHz int16 (TPDF dither at the boundary)
        pcm16_24k = float32_to_int16_dither(f32_chunk, rng=rng)
        # 24 kHz int16 → 8 kHz int16 via stateful soxr
        pcm16_8k = downsampler.process(pcm16_24k)
        if pcm16_8k.size == 0:
            continue
        # int16 → G.711 (PCMU or PCMA)
        g711 = encode_g711(pcm16_8k.tobytes(), encoding)
        leftover.extend(g711)

        # Yield as many full frames as we have ready.
        while len(leftover) >= frame_bytes:
            frame = bytes(leftover[:frame_bytes])
            del leftover[:frame_bytes]
            yield frame

    # Stream finished — drain the soxr filter state so the final phoneme
    # isn't truncated.
    tail_8k = downsampler.flush()
    if tail_8k.size > 0:
        g711_tail = encode_g711(tail_8k.tobytes(), encoding)
        leftover.extend(g711_tail)

    # Drain remaining full frames.
    while len(leftover) >= frame_bytes:
        frame = bytes(leftover[:frame_bytes])
        del leftover[:frame_bytes]
        yield frame

    # Final partial frame: pad with codec-specific silence to fixed length
    # so the caller never sees a short frame.
    if leftover:
        silence = silence_byte_for_encoding(encoding)
        padding = silence * (frame_bytes - len(leftover))
        yield bytes(leftover) + padding


async def synthesize_tts(
    text: str,
    *,
    voice_id: Optional[str] = None,
    target_sample_rate: Optional[int] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> bytes:
    """Buffered (non-streaming) TTS for callers that want the full audio.

    Synthesize ``text`` into 16-bit LE PCM mono audio at ``target_sample_rate``
    (defaults to Mistral's native 24 kHz). Implemented on top of the streaming
    SSE iterator + scipy resampling.

    Use ``stream_tts_g711`` instead for telephony pipelines — this wrapper is
    intended for one-shot uses (smoke tests, file generation, offline batch).
    """
    api_key = api_key or settings.MISTRAL_API_KEY
    voice_id = voice_id or settings.VOXTRAL_VOICE_ID
    model = model or settings.VOXTRAL_TTS_MODEL

    if not api_key:
        raise VoxtralError("MISTRAL_API_KEY not configured")
    if not voice_id:
        raise VoxtralError("voice_id required")

    chunks: list[np.ndarray] = []
    async for f32 in _iter_voxtral_tts_float32(
        text, voice_id=voice_id, api_key=api_key, model=model
    ):
        chunks.append(f32)

    if not chunks:
        return b""

    full = np.concatenate(chunks)
    pcm24k = float32_to_int16_dither(full).tobytes()

    if target_sample_rate is None or target_sample_rate == VOXTRAL_TTS_SAMPLE_RATE:
        return pcm24k
    return resample_pcm(pcm24k, VOXTRAL_TTS_SAMPLE_RATE, target_sample_rate)


# ── STT (unchanged) ──────────────────────────────────────────────────────────


async def transcribe_pcm(
    pcm: bytes,
    *,
    sample_rate: int,
    language: str = "en",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Transcribe a PCM s16 LE mono audio buffer via Mistral's batch STT.

    The voice-call pipeline calls this once per detected user turn (after
    silence), passing the accumulated PCM for that turn.

    Returns the final transcribed text. Empty string if transcription fails
    or returns nothing.
    """
    api_key = api_key or settings.MISTRAL_API_KEY
    model = model or settings.VOXTRAL_STT_MODEL

    if not api_key:
        raise VoxtralError("MISTRAL_API_KEY not configured")
    if not pcm:
        return ""

    wav_bytes = pcm_to_wav(pcm, sample_rate=sample_rate)

    files = {
        "file": ("chunk.wav", wav_bytes, "audio/wav"),
    }
    data = {
        "model": model,
        "language": language,
        "stream": "true",
    }

    final_text = ""

    async with httpx.AsyncClient(timeout=STT_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/audio/transcriptions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "text/event-stream",
            },
            files=files,
            data=data,
        ) as resp:
            if resp.status_code >= 400:
                body_text = await resp.aread()
                logger.warning(
                    "Voxtral STT HTTP %s: %s",
                    resp.status_code,
                    body_text.decode("utf-8", "replace")[:500],
                )
                return ""

            async for event in _iter_sse_events(resp):
                data_str = event.get("data")
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    payload = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "transcription.done":
                    txt = payload.get("text") or ""
                    if txt:
                        final_text = txt
                # transcription.text.delta events are partials; we ignore them
                # here and only use the final .done text.

    return final_text


# ── SSE parser ───────────────────────────────────────────────────────────────


async def _iter_sse_events(
    response: httpx.Response,
) -> AsyncIterator[dict]:
    """Async iterator over Server-Sent Events from an httpx streamed response.

    Yields {"event": str | None, "data": str} for each complete event. Handles
    multi-line events and keepalive comments.
    """
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk
        while True:
            sep_idx = buffer.find("\n\n")
            if sep_idx == -1:
                break
            raw_event = buffer[:sep_idx]
            buffer = buffer[sep_idx + 2 :]
            yield _parse_sse_block(raw_event)
    if buffer.strip():
        yield _parse_sse_block(buffer)


def _parse_sse_block(block: str) -> dict:
    event_type: Optional[str] = None
    data_lines: list[str] = []
    for line in block.split("\n"):
        if line.startswith(":"):  # keepalive comment
            continue
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    return {"event": event_type, "data": "\n".join(data_lines) if data_lines else None}
