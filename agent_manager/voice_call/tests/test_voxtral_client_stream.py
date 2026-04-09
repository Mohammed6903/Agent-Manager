"""End-to-end wiring test for the streaming TTS generator.

Monkey-patches the SSE iterator with a synthetic float32 sine, runs
``stream_tts_g711`` to completion, asserts the output frames are correctly
sized G.711 frames that decode back to the original sine.

Pure DSP — no network, no Mistral, no Telnyx.
"""

from __future__ import annotations

import asyncio
import audioop

import numpy as np
import pytest

from agent_manager.voice_call import voxtral_client
from agent_manager.voice_call.audio_codec import VOXTRAL_TTS_SAMPLE_RATE


def _sine_24k(freq_hz: float, duration_s: float, amplitude: float = 0.5) -> np.ndarray:
    n = int(VOXTRAL_TTS_SAMPLE_RATE * duration_s)
    t = np.arange(n, dtype=np.float64) / VOXTRAL_TTS_SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


@pytest.mark.parametrize("encoding", ["PCMU", "PCMA"])
def test_stream_tts_g711_sine(monkeypatch, encoding):
    """Inject a 1 kHz sine into the SSE iterator. The output frames should
    be exactly the right shape, decode back to the same sine in the 8 kHz
    output, and the total length should match (within one frame's worth)
    the input duration.
    """
    duration_s = 1.0
    freq = 1000.0
    sine = _sine_24k(freq, duration_s)

    # Yield in irregular chunk sizes to also exercise the chunked path of
    # the streaming downsampler.
    async def fake_iter(text, *, voice_id, api_key, model):
        chunks_sizes = [480, 1, 7, 1024, 480, 200, 480, 999]
        cursor = 0
        for cs in chunks_sizes:
            end = min(cursor + cs, sine.size)
            if cursor >= sine.size:
                break
            yield sine[cursor:end]
            cursor = end
        if cursor < sine.size:
            yield sine[cursor:]

    monkeypatch.setattr(voxtral_client, "_iter_voxtral_tts_float32", fake_iter)
    # Bypass the API key / voice id checks in stream_tts_g711.
    monkeypatch.setattr(voxtral_client.settings, "MISTRAL_API_KEY", "test-key")
    monkeypatch.setattr(voxtral_client.settings, "VOXTRAL_VOICE_ID", "test-voice")

    frame_ms = 20

    async def collect():
        result: list[bytes] = []
        async for frame in voxtral_client.stream_tts_g711(
            "ignored", encoding=encoding, frame_ms=frame_ms
        ):
            result.append(frame)
        return result

    frames = asyncio.run(collect())

    assert len(frames) > 0, "stream_tts_g711 yielded no frames"

    # Each frame is exactly the expected size (1 byte/sample × 8 samples/ms × frame_ms)
    expected_frame_bytes = 8 * frame_ms
    for i, f in enumerate(frames):
        assert len(f) == expected_frame_bytes, (
            f"frame #{i} has {len(f)} bytes, expected {expected_frame_bytes}"
        )

    # Total bytes ≈ duration × 8 bytes/ms × 1000, ± one frame for the padded tail
    total_bytes = sum(len(f) for f in frames)
    expected_bytes = int(duration_s * 8 * 1000)
    assert abs(total_bytes - expected_bytes) <= expected_frame_bytes, (
        f"total bytes {total_bytes} vs expected {expected_bytes}"
    )

    # Decode the G.711 stream back to int16 PCM @ 8 kHz, run an FFT, confirm
    # the dominant frequency is still ~1 kHz.
    g711_concat = b"".join(frames)
    if encoding == "PCMU":
        pcm_bytes = audioop.ulaw2lin(g711_concat, 2)
    else:
        pcm_bytes = audioop.alaw2lin(g711_concat, 2)
    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float64)
    # Drop edges where filter group delay + padding-silence live
    edge = 200
    steady = samples[edge:-edge]
    assert steady.size > 0

    spectrum = np.abs(np.fft.rfft(steady * np.hanning(len(steady))))
    spectrum[0] = 0
    peak_bin = int(np.argmax(spectrum))
    peak_freq = peak_bin * 8000.0 / len(steady)
    assert abs(peak_freq - freq) < 30.0, (
        f"decoded peak {peak_freq:.1f} Hz vs expected {freq:.1f} Hz"
    )
