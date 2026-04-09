"""Sanity check: does synthesize_tts(target_sample_rate=8000) produce
audio that matches the smoke script's StreamingDownsampler path?

Both paths are scipy-based but they take different routes:

  - synthesize_tts: float32 → dither → int16 24k → scipy.resample_poly → int16 8k
  - smoke script:   float32 → StreamingDownsampler24kTo8k (lfilter+state) → dither → int16 8k

If they sound different (or one of them is silent / clipped / quiet),
that explains why the call sounds bad even though the smoke WAV sounded good.
"""

from __future__ import annotations

import asyncio
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from agent_manager.config import settings
from agent_manager.voice_call.audio_codec import (
    StreamingDownsampler24kTo8k,
    float32_to_int16_dither,
)
from agent_manager.voice_call.voxtral_client import (
    _iter_voxtral_tts_float32,
    synthesize_tts,
)


SENTENCE = "The quick brown fox jumps over the lazy dog. She sells seashells by the seashore."
OUT_DIR = Path("/tmp/tts_diff")


def write_wav(path: Path, pcm_int16_bytes: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm_int16_bytes)


def stats(name: str, samples_i16: np.ndarray) -> None:
    if samples_i16.size == 0:
        print(f"  {name:30s} EMPTY")
        return
    rms = float(np.sqrt(np.mean(samples_i16.astype(np.float64) ** 2)))
    peak = int(np.max(np.abs(samples_i16)))
    nz = int(np.count_nonzero(samples_i16))
    print(
        f"  {name:30s} samples={samples_i16.size:8d}  "
        f"rms={rms:8.1f}  peak={peak:6d}  nonzero={nz}/{samples_i16.size}"
    )


async def main() -> None:
    if not settings.MISTRAL_API_KEY:
        raise SystemExit("MISTRAL_API_KEY missing")

    print(f"[diff] Synthesizing test sentence...")

    # Path A: smoke-script path (StreamingDownsampler on float32)
    chunks: list[np.ndarray] = []
    async for f32 in _iter_voxtral_tts_float32(
        SENTENCE,
        voice_id=settings.VOXTRAL_VOICE_ID,
        api_key=settings.MISTRAL_API_KEY,
        model=settings.VOXTRAL_TTS_MODEL,
    ):
        chunks.append(f32)
    full_f32 = np.concatenate(chunks)

    ds = StreamingDownsampler24kTo8k()
    out_8k_smoke = np.concatenate([ds.process(full_f32), ds.flush()])
    smoke_int16 = float32_to_int16_dither(out_8k_smoke)

    # Path B: synthesize_tts(target_sample_rate=8000) — what _speak_text uses now
    synth_bytes = await synthesize_tts(SENTENCE, target_sample_rate=8000)
    synth_int16 = np.frombuffer(synth_bytes, dtype=np.int16)

    # Path C: native 24k (no resampling, ceiling)
    native_int16 = float32_to_int16_dither(full_f32)

    print()
    print("Stats:")
    stats("native_24k (ceiling)", native_int16)
    stats("smoke_path_8k (good)", smoke_int16)
    stats("synthesize_tts_8k (used by call)", synth_int16)

    write_wav(OUT_DIR / "native_24k.wav", native_int16.tobytes(), 24000)
    write_wav(OUT_DIR / "smoke_path_8k.wav", smoke_int16.tobytes(), 8000)
    write_wav(OUT_DIR / "synthesize_tts_8k.wav", synth_int16.tobytes(), 8000)

    print()
    print(f"Wrote 3 WAVs to {OUT_DIR}/")
    print()
    print("Listen and tell me which sounds bad:")
    print(f"  ffplay -autoexit -nodisp {OUT_DIR}/smoke_path_8k.wav")
    print(f"  ffplay -autoexit -nodisp {OUT_DIR}/synthesize_tts_8k.wav")


if __name__ == "__main__":
    asyncio.run(main())
