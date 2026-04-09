"""A/B comparison for Voxtral TTS audio quality (manual diagnostic).

NOT a unit test. Hits the real Mistral API. Requires MISTRAL_API_KEY in
your environment.

Run::

    .venv/bin/python scripts/smoke_tts_quality.py

Outputs three WAV files in /tmp/tts_quality/ for manual A/B listening:

    voxtral_native_24k.wav
        Voxtral's raw 24 kHz output (no resampling). The "ceiling" — what
        the source audio sounds like before any telephony degradation.

    new_scipy_8k.wav
        Voxtral 24 kHz → scipy lfilter+decimate → dither → int16 → 8 kHz WAV.
        This is what the new streaming pipeline produces (post-resample,
        pre-G.711-encode). If the new path is correct this should sound
        clean — bandlimited but natural, no metallic artifacts.

    old_audioop_8k.wav
        Voxtral 24 kHz → float→int16 hard clip → audioop.ratecv → 8 kHz WAV.
        The legacy pipeline. Should sound metallic / muddy. The whole point
        of the rewrite is for new_scipy to sound noticeably better than this.

Listen with::

    ffplay -autoexit /tmp/tts_quality/voxtral_native_24k.wav
    ffplay -autoexit /tmp/tts_quality/new_scipy_8k.wav
    ffplay -autoexit /tmp/tts_quality/old_audioop_8k.wav

Or use Audacity to view spectrograms — the old version will show aliased
energy folded back into the audible band; the new one won't.
"""

from __future__ import annotations

import asyncio
import audioop
import os
import sys
import wave
from pathlib import Path

# Make the OpenClawApi package importable when running from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from agent_manager.config import settings  # noqa: E402
from agent_manager.voice_call.audio_codec import (  # noqa: E402
    StreamingDownsampler24kTo8k,
    VOXTRAL_TTS_SAMPLE_RATE,
    float32_to_int16_dither,
    pcm_to_wav,
)
from agent_manager.voice_call.voxtral_client import (  # noqa: E402
    _iter_voxtral_tts_float32,
)

OUT_DIR = Path("/tmp/tts_quality")
SENTENCE = "The quick brown fox jumps over the lazy dog. She sells seashells by the seashore."


def write_wav(path: Path, pcm_int16_bytes: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_int16_bytes)


async def collect_voxtral_float32() -> np.ndarray:
    """Synthesize the test sentence and return the full float32 24 kHz buffer."""
    if not settings.MISTRAL_API_KEY:
        raise SystemExit("MISTRAL_API_KEY not set in environment / .env")

    chunks: list[np.ndarray] = []
    async for chunk in _iter_voxtral_tts_float32(
        SENTENCE,
        voice_id=settings.VOXTRAL_VOICE_ID,
        api_key=settings.MISTRAL_API_KEY,
        model=settings.VOXTRAL_TTS_MODEL,
    ):
        chunks.append(chunk)

    if not chunks:
        raise SystemExit("Voxtral returned no audio chunks")
    return np.concatenate(chunks)


def make_native_wav(f32_24k: np.ndarray) -> bytes:
    """Native 24 kHz: just dither + quantize, no resampling."""
    return float32_to_int16_dither(f32_24k).tobytes()


def make_new_scipy_wav(f32_24k: np.ndarray) -> bytes:
    """New path: stateful scipy downsampler 24→8 kHz + dither (no normalization)."""
    ds = StreamingDownsampler24kTo8k()
    out_8k = np.concatenate([ds.process(f32_24k), ds.flush()])
    return float32_to_int16_dither(out_8k).tobytes()


def make_normalized_wav(f32_24k: np.ndarray) -> bytes:
    """Telephony path: scipy downsample + peak normalization to -1 dBFS + dither.

    Mirrors what _speak_text now does. Voxtral synthesizes at ~-11 dBFS which
    is too quiet for PSTN; this boosts to ~-1 dBFS so the voice rides above
    G.711 quantization and carrier compression.
    """
    ds = StreamingDownsampler24kTo8k()
    out_8k = np.concatenate([ds.process(f32_24k), ds.flush()])
    peak = float(np.max(np.abs(out_8k))) if out_8k.size else 0.0
    if peak > 1e-4:
        out_8k = out_8k * (0.9 / peak)
    return float32_to_int16_dither(out_8k).tobytes()


def make_old_audioop_wav(f32_24k: np.ndarray) -> bytes:
    """Legacy path: hard-clip float→int16, then audioop linear-interp resample.

    Mirrors the previous pipeline exactly so the A/B is fair.
    """
    # Hard clip + naive int16 conversion (the pre-rewrite behavior).
    clipped = np.clip(f32_24k, -1.0, 1.0)
    int16_24k = np.rint(clipped * 32767.0).astype(np.int16).tobytes()
    # audioop.ratecv linear-interp downsample.
    converted, _ = audioop.ratecv(int16_24k, 2, 1, 24000, 8000, None)
    return converted


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[smoke_tts_quality] Synthesizing test sentence via real Voxtral...")
    print(f"    sentence: {SENTENCE!r}")
    print(f"    voice_id: {settings.VOXTRAL_VOICE_ID}")
    print(f"    model:    {settings.VOXTRAL_TTS_MODEL}")

    f32_24k = await collect_voxtral_float32()
    duration_s = f32_24k.size / VOXTRAL_TTS_SAMPLE_RATE
    print(
        f"[smoke_tts_quality] Got {f32_24k.size} samples @ 24 kHz "
        f"(~{duration_s:.2f} s of audio)"
    )

    # Native 24 kHz reference
    native_path = OUT_DIR / "voxtral_native_24k.wav"
    write_wav(native_path, make_native_wav(f32_24k), 24000)
    print(f"  ✓ wrote {native_path}")

    # New scipy 8 kHz path (no normalization — what was tested before)
    new_path = OUT_DIR / "new_scipy_8k.wav"
    write_wav(new_path, make_new_scipy_wav(f32_24k), 8000)
    print(f"  ✓ wrote {new_path}")

    # Telephony path (scipy + peak normalization → louder, what _speak_text does now)
    norm_path = OUT_DIR / "telephony_normalized_8k.wav"
    write_wav(norm_path, make_normalized_wav(f32_24k), 8000)
    print(f"  ✓ wrote {norm_path}")

    # Legacy audioop 8 kHz path
    old_path = OUT_DIR / "old_audioop_8k.wav"
    write_wav(old_path, make_old_audioop_wav(f32_24k), 8000)
    print(f"  ✓ wrote {old_path}")

    print()
    print("Listen and compare:")
    print(f"  ffplay -autoexit -nodisp {native_path}    # ceiling (24 kHz native)")
    print(f"  ffplay -autoexit -nodisp {new_path}       # NEW pipeline (should sound clean)")
    print(f"  ffplay -autoexit -nodisp {old_path}       # OLD pipeline (should sound metallic)")
    print()
    print("Or use Audacity to view spectrograms — old should show aliased energy")
    print("folded back; new should not.")


if __name__ == "__main__":
    asyncio.run(main())
