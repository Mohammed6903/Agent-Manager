"""Audio format helpers for the voice-call pipeline.

Telnyx media streaming defaults to **G.711 (PCMU μ-law or PCMA A-law) at
8 kHz mono** — the universal telephony codec. Voxtral TTS returns float32 LE
PCM at 24 kHz, and Voxtral STT prefers 16 kHz int16 LE PCM input.

This module provides:

- **Codec dispatch** (decode_g711 / encode_g711) for the negotiated G.711 flavor
- **One-shot resampling** (resample_pcm) via ``soxr.resample`` (libsoxr,
  quality="VHQ"), used by the inbound STT path (8 kHz → 16 kHz upsample)
  and the buffered ``synthesize_tts`` compatibility wrapper.
- **Streaming resampling** (SoxrStreamDownsampler) via ``soxr.ResampleStream``
  (quality="VHQ"), used by the outbound TTS pipeline. soxr maintains
  internal history across chunks so there are no boundary artifacts.
  This is the same resampler pipecat (the leading voice-AI framework) uses
  for its production Telnyx serializer.
- **Dithered quantization** (float32_to_int16_dither) using TPDF dither
  to avoid quantization distortion on quiet passages.
- **WAV wrapping** (pcm_to_wav) for the Voxtral batch STT endpoint.
- **VAD primitive** (pcm_rms) for begin-of-speech / end-of-speech detection
  on the inbound side.

audioop is stdlib, deprecated in Python 3.13. The G.711 dispatch and
pcm_rms still rely on it; on 3.13+ install ``audioop-lts`` as a drop-in.
"""

from __future__ import annotations

import audioop
import io
import wave

import numpy as np
import soxr

# ── Internal audio invariants ───────────────────────────────────────────────
PCM_SAMPLE_WIDTH = 2  # bytes per sample (16-bit)
PCM_CHANNELS = 1  # mono

# ── Telnyx negotiated format (PCMU/PCMA at 8 kHz) ──────────────────────────
# Both inbound and outbound use G.711 8 kHz. This matches the production
# voice-AI pipelines used by pipecat and Telnyx's own V2V demo. L16/HD
# codecs were tried and abandoned — see plan file for the research trail.
TELNYX_PCM_SAMPLE_RATE = 8000  # PCM rate after we decode G.711
BYTES_PER_MS_8K = TELNYX_PCM_SAMPLE_RATE * PCM_SAMPLE_WIDTH // 1000  # 16

# ── Voxtral preferred rates ─────────────────────────────────────────────────
VOXTRAL_STT_SAMPLE_RATE = 16000  # What we feed to /audio/transcriptions
VOXTRAL_TTS_SAMPLE_RATE = 24000  # What /audio/speech PCM returns


# ─────────────────────────────────────────────────────────────────────────────
# Streaming downsampler (24 kHz → 8 kHz) — soxr "VHQ" backend
# ─────────────────────────────────────────────────────────────────────────────


class SoxrStreamDownsampler:
    """Stateful 24 kHz → 8 kHz (or any rate pair) downsampler using libsoxr.

    Wraps ``soxr.ResampleStream`` with quality="VHQ" — the gold-standard
    practical resampler used by pipecat, Audacity, ffmpeg, and librosa.
    Maintains internal history across chunks so there are no boundary
    artifacts when input arrives in arbitrary-sized pieces (which is the
    case with Voxtral SSE TTS chunks).

    Constructed fresh per TTS request — never share across requests, the
    soxr stream state is request-local.

    Usage::

        ds = SoxrStreamDownsampler()
        for f32_chunk in tts_chunks_24k:
            out_8k_int16 = ds.process(f32_chunk)
            consume(out_8k_int16)
        tail = ds.flush()
        consume(tail)

    Input is float32 numpy in [-1, 1]; output is int16 numpy at the
    target rate. The float→int16 quantization happens once at the boundary
    via TPDF dither, applied externally by ``float32_to_int16_dither``
    after concatenation — see ``_speak_text``. ``process`` here returns
    int16 directly because soxr's stream resampler is configured with
    ``dtype="int16"`` (matching pipecat's setup).
    """

    def __init__(
        self,
        in_rate: int = VOXTRAL_TTS_SAMPLE_RATE,
        out_rate: int = TELNYX_PCM_SAMPLE_RATE,
    ) -> None:
        self._in_rate = in_rate
        self._out_rate = out_rate
        self._stream = soxr.ResampleStream(
            in_rate=in_rate,
            out_rate=out_rate,
            num_channels=1,
            quality="VHQ",
            dtype="int16",
        )

    def process(self, x_int16: np.ndarray) -> np.ndarray:
        """Resample a chunk of int16 input.

        Returns the corresponding resampled int16 samples. May return an
        empty array if the chunk is too short to produce any output yet
        (samples are buffered inside soxr's filter state).
        """
        if x_int16.size == 0:
            return np.empty(0, dtype=np.int16)
        if x_int16.dtype != np.int16:
            x_int16 = x_int16.astype(np.int16, copy=False)
        return self._stream.resample_chunk(x_int16)

    def flush(self) -> np.ndarray:
        """Drain remaining samples from the soxr filter state.

        Call once at end-of-stream. soxr signals end-of-stream via
        ``resample_chunk`` with the ``last=True`` flag (an empty input
        with last=True returns the buffered tail).
        """
        return self._stream.resample_chunk(
            np.empty(0, dtype=np.int16), last=True
        )


# ─────────────────────────────────────────────────────────────────────────────
# Float32 → int16 conversion (dithered)
# ─────────────────────────────────────────────────────────────────────────────


def float32_to_int16_dither(
    x: np.ndarray, rng: np.random.Generator | None = None
) -> np.ndarray:
    """Convert float32 samples in [-1, 1] to int16 with TPDF dither.

    TPDF (triangular probability density function) dither is the standard
    "free" quality bump for audio quantization — adds ~2 LSB peak-to-peak
    of triangular noise before rounding, which decorrelates quantization
    error from the signal and audibly removes harshness on quiet passages.

    Cheap (~one numpy op), well below G.711's quantization floor.
    """
    if x.size == 0:
        return np.empty(0, dtype=np.int16)
    if rng is None:
        rng = np.random.default_rng()
    # Two uniform draws → triangular distribution. Scale to ~1 LSB at int16
    # full-scale (1/32768 in normalized [-1, 1] space), then *2 since the
    # difference of two uniforms peaks at ±1 not ±0.5.
    n = x.size
    dither = (rng.random(n, dtype=np.float32) - rng.random(n, dtype=np.float32)) * (
        1.0 / 32768.0
    )
    scaled = (x.astype(np.float32, copy=False) + dither) * 32767.0
    np.clip(scaled, -32768.0, 32767.0, out=scaled)
    return np.rint(scaled).astype(np.int16)


def float32_le_to_int16_le(data: bytes) -> bytes:
    """Convert Mistral's float32 LE PCM bytes to int16 LE bytes.

    Mistral's /v1/audio/speech with response_format=pcm returns float32 LE
    samples in [-1.0, 1.0], NOT int16 like most APIs. We convert at the
    boundary so the rest of the pipeline can assume s16le.

    Now uses numpy + dither (was a pure-python struct loop with hard
    clipping). Same signature for backward compatibility.
    """
    if not data:
        return b""
    samples = np.frombuffer(data, dtype="<f4")
    return float32_to_int16_dither(samples).tobytes()


# ─────────────────────────────────────────────────────────────────────────────
# One-shot resampling (used by inbound STT + buffered synthesize_tts wrapper)
# ─────────────────────────────────────────────────────────────────────────────


def resample_pcm(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """One-shot resample int16 LE mono PCM via libsoxr.

    Uses ``soxr.resample`` with ``quality="VHQ"`` — the same VHQ setting
    pipecat uses for streaming, but in one-shot mode for offline / per-call
    paths (inbound STT 8 kHz → 16 kHz upsample, the buffered
    ``synthesize_tts`` wrapper). For streaming TTS use
    ``SoxrStreamDownsampler`` instead, which keeps state across chunks.
    """
    if src_rate == dst_rate:
        return pcm
    if not pcm:
        return b""

    samples = np.frombuffer(pcm, dtype=np.int16)
    out = soxr.resample(samples, src_rate, dst_rate, quality="VHQ")
    return out.astype(np.int16, copy=False).tobytes()


# ─────────────────────────────────────────────────────────────────────────────
# G.711 codec dispatch
# ─────────────────────────────────────────────────────────────────────────────


def ulaw_to_pcm(ulaw: bytes) -> bytes:
    """G.711 μ-law → 16-bit LE PCM mono.

    μ-law is 1 byte per sample. Output is 2 bytes per sample (s16 LE).
    Sample rate is preserved (caller must know it's 8 kHz typically).
    """
    if not ulaw:
        return b""
    return audioop.ulaw2lin(ulaw, PCM_SAMPLE_WIDTH)


def alaw_to_pcm(alaw: bytes) -> bytes:
    """G.711 A-law → 16-bit LE PCM mono. Same shape as ``ulaw_to_pcm``."""
    if not alaw:
        return b""
    return audioop.alaw2lin(alaw, PCM_SAMPLE_WIDTH)


def pcm_to_ulaw(pcm: bytes) -> bytes:
    """16-bit LE PCM mono → G.711 μ-law.

    Output is half the size (1 byte per sample). Sample rate is preserved.
    """
    if not pcm:
        return b""
    return audioop.lin2ulaw(pcm, PCM_SAMPLE_WIDTH)


def pcm_to_alaw(pcm: bytes) -> bytes:
    """16-bit LE PCM mono → G.711 A-law."""
    if not pcm:
        return b""
    return audioop.lin2alaw(pcm, PCM_SAMPLE_WIDTH)


def decode_g711(payload: bytes, encoding: str) -> bytes:
    """Dispatch G.711 decoding based on the negotiated codec name.

    Telnyx reports the codec in ``media_format.encoding`` of the start event:
    ``"PCMU"`` (μ-law) or ``"PCMA"`` (A-law). Anything else falls back to
    μ-law since it's the most common telephony default.
    """
    if (encoding or "").upper() == "PCMA":
        return alaw_to_pcm(payload)
    return ulaw_to_pcm(payload)


def encode_g711(pcm: bytes, encoding: str) -> bytes:
    """Dispatch G.711 encoding based on the negotiated codec name."""
    if (encoding or "").upper() == "PCMA":
        return pcm_to_alaw(pcm)
    return pcm_to_ulaw(pcm)


def silence_byte_for_encoding(encoding: str) -> bytes:
    """G.711 silence byte for codec-specific frame padding.

    PCMU silence is 0xFF, PCMA silence is 0xD5. Used to pad short final
    frames to a fixed length without producing audible clicks.
    """
    return b"\xd5" if (encoding or "").upper() == "PCMA" else b"\xff"


# ─────────────────────────────────────────────────────────────────────────────
# WAV wrapping + RMS
# ─────────────────────────────────────────────────────────────────────────────


def pcm_to_wav(pcm: bytes, sample_rate: int = VOXTRAL_STT_SAMPLE_RATE) -> bytes:
    """Wrap raw int16 LE mono PCM in a WAV container.

    The Mistral STT batch endpoint accepts WAV, so we wrap audio buffers
    before uploading them.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(PCM_CHANNELS)
        wav.setsampwidth(PCM_SAMPLE_WIDTH)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buf.getvalue()


def pcm_rms(pcm: bytes) -> int:
    """Compute the RMS energy of a PCM chunk.

    Used for silence detection — we consider a frame "silent" if its RMS is
    below a threshold. stdlib audioop.rms handles int16 correctly.
    """
    if not pcm:
        return 0
    return audioop.rms(pcm, PCM_SAMPLE_WIDTH)
