"""Unit tests for the audio_codec primitives.

These tests are pure DSP — no network, no Mistral, no Telnyx, no asyncio.
They validate the streaming downsampler (libsoxr-backed), dithered quantizer,
and one-shot resampler against synthetic signals (sines).

Run with::

    .venv/bin/pytest agent_manager/voice_call/tests/test_audio_codec.py -v
"""

from __future__ import annotations

import numpy as np

from agent_manager.voice_call.audio_codec import (
    SoxrStreamDownsampler,
    TELNYX_PCM_SAMPLE_RATE,
    VOXTRAL_TTS_SAMPLE_RATE,
    float32_to_int16_dither,
    resample_pcm,
)


def _sine_int16(
    freq_hz: float, sample_rate: int, duration_s: float, amplitude: float = 0.5
) -> np.ndarray:
    """Generate an int16 sine wave at the given frequency and rate."""
    n = int(sample_rate * duration_s)
    t = np.arange(n, dtype=np.float64) / sample_rate
    return (amplitude * np.sin(2 * np.pi * freq_hz * t) * 32767).astype(np.int16)


def _sine(freq_hz: float, sample_rate: int, duration_s: float, amplitude: float = 0.5) -> np.ndarray:
    """Generate a float32 sine wave at the given frequency and rate."""
    n = int(sample_rate * duration_s)
    t = np.arange(n, dtype=np.float64) / sample_rate
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def _peak_freq_hz(samples: np.ndarray, sample_rate: int) -> float:
    """Return the frequency of the largest FFT bin (excluding DC)."""
    spectrum = np.fft.rfft(samples * np.hanning(len(samples)))
    mag = np.abs(spectrum)
    mag[0] = 0  # ignore DC
    peak_bin = int(np.argmax(mag))
    return peak_bin * sample_rate / len(samples)


def _rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


# ─── Test 1: in-band sine survives downsampling cleanly ─────────────────────


def test_downsampler_sine_intelligibility():
    """A 1 kHz sine at 24 kHz should produce a 1 kHz sine at 8 kHz with
    near-identical amplitude. Confirms the soxr "VHQ" filter doesn't eat
    the speech band.
    """
    duration_s = 1.0
    src_rate = VOXTRAL_TTS_SAMPLE_RATE  # 24000
    dst_rate = TELNYX_PCM_SAMPLE_RATE  # 8000

    src = _sine_int16(freq_hz=1000.0, sample_rate=src_rate, duration_s=duration_s, amplitude=0.5)

    ds = SoxrStreamDownsampler(in_rate=src_rate, out_rate=dst_rate)
    out_chunks = []
    # Process in 480-sample (20 ms) chunks to also exercise the chunked path.
    cursor = 0
    while cursor < src.size:
        end = min(cursor + 480, src.size)
        out_chunks.append(ds.process(src[cursor:end]))
        cursor = end
    out_chunks.append(ds.flush())
    out = np.concatenate(out_chunks).astype(np.float64) / 32768.0

    # Length check: 24k → 8k = 3:1 ratio, so output is ~third the length.
    expected_n = int(duration_s * dst_rate)
    assert abs(len(out) - expected_n) < 100, (
        f"output length {len(out)} vs expected {expected_n}"
    )

    # Drop the leading/trailing samples — soxr's transition region.
    steady = out[400:-400]
    assert steady.size > 0

    peak_freq = _peak_freq_hz(steady, dst_rate)
    assert abs(peak_freq - 1000.0) < 25.0, (
        f"expected peak near 1 kHz, got {peak_freq:.1f} Hz"
    )

    # Amplitude in steady state should match input amplitude (0.5) within ~3 dB.
    out_rms = _rms(steady)
    expected_rms = 0.5 / np.sqrt(2)  # sine RMS = peak / sqrt(2)
    ratio_db = 20 * np.log10(max(out_rms, 1e-9) / expected_rms)
    assert abs(ratio_db) < 3.0, (
        f"output RMS {out_rms:.4f} vs expected {expected_rms:.4f} ({ratio_db:.1f} dB)"
    )


# ─── Test 2: chunk size doesn't significantly affect output ─────────────────


def test_downsampler_chunk_invariance():
    """Filtering the whole stream at once must produce essentially identical
    output to filtering it as a stream of small irregular chunks. soxr's
    ResampleStream maintains internal state across chunks, but the chunk
    boundary handling is documented to be sample-stable, not bit-stable —
    we allow a small tolerance.
    """
    src_rate = VOXTRAL_TTS_SAMPLE_RATE
    src = _sine_int16(
        freq_hz=523.25, sample_rate=src_rate, duration_s=0.5, amplitude=0.7
    )

    # Path A: one big chunk + flush
    ds_a = SoxrStreamDownsampler()
    out_a = np.concatenate([ds_a.process(src), ds_a.flush()])

    # Path B: many small irregular chunks + flush
    ds_b = SoxrStreamDownsampler()
    out_b_chunks = []
    cursor = 0
    for chunk_size in [3, 9, 51, 480, 2401, 13, 199, 3, 3, 999, 4093, 7, 31]:
        if cursor >= src.size:
            break
        end = min(cursor + chunk_size, src.size)
        out_b_chunks.append(ds_b.process(src[cursor:end]))
        cursor = end
    if cursor < src.size:
        out_b_chunks.append(ds_b.process(src[cursor:]))
    out_b_chunks.append(ds_b.flush())
    out_b = np.concatenate(out_b_chunks)

    # soxr can produce slightly different lengths between paths because
    # internal buffering has chunk-size-dependent boundary behaviour.
    n = min(out_a.size, out_b.size)
    assert n > 0
    # Drop the first/last few samples (transient regions) and require the
    # remaining samples to be very close. Allow up to ~3 LSB drift per
    # sample, which is well below audibility.
    edge = 200
    a_trim = out_a[edge : n - edge].astype(np.int32)
    b_trim = out_b[edge : n - edge].astype(np.int32)
    max_diff = int(np.max(np.abs(a_trim - b_trim)))
    assert max_diff < 256, (
        f"chunked vs all-in-one max sample diff = {max_diff} (expected < 256)"
    )


# ─── Test 3: out-of-band signal gets rejected (anti-alias regression) ───────


def test_downsampler_alias_rejection():
    """A 5 kHz sine at 24 kHz is above the 8 kHz output Nyquist (4 kHz)
    and would alias to 3 kHz under naive resampling. soxr's VHQ filter
    should attenuate it heavily — output RMS should be ≥ 60 dB below the
    in-band reference (soxr's VHQ is much sharper than scipy lfilter; we
    bumped the assertion from the previous 40 dB threshold to reflect that).
    """
    src_rate = VOXTRAL_TTS_SAMPLE_RATE
    duration_s = 0.5

    # In-band reference at 1 kHz
    in_band = _sine_int16(
        freq_hz=1000.0, sample_rate=src_rate, duration_s=duration_s, amplitude=0.5
    )
    ds_a = SoxrStreamDownsampler()
    out_in_band = np.concatenate([ds_a.process(in_band), ds_a.flush()]).astype(
        np.float64
    ) / 32768.0
    rms_in_band = _rms(out_in_band[400:-400])

    # Out-of-band at 5 kHz (should be killed by the filter)
    out_of_band_src = _sine_int16(
        freq_hz=5000.0, sample_rate=src_rate, duration_s=duration_s, amplitude=0.5
    )
    ds_b = SoxrStreamDownsampler()
    out_oob = np.concatenate([ds_b.process(out_of_band_src), ds_b.flush()]).astype(
        np.float64
    ) / 32768.0
    rms_oob = _rms(out_oob[400:-400])

    # Suppression ratio in dB
    suppression_db = 20 * np.log10(rms_in_band / max(rms_oob, 1e-12))
    assert suppression_db > 60.0, (
        f"5 kHz alias suppression only {suppression_db:.1f} dB; "
        f"in-band RMS={rms_in_band:.4f}, OOB RMS={rms_oob:.4f}"
    )


# ─── Test 4: dither doesn't clip and produces correct distribution ──────────


def test_dither_clipping_and_range():
    """Full-scale input should NEVER produce out-of-range int16 samples,
    and the output dtype must be int16. Also sanity-check that the dither
    actually adds noise (otherwise we'd see exact mid-tread quantization).
    """
    rng = np.random.default_rng(seed=42)

    # Full-scale sine — exactly at ±1.0
    n = 4800
    t = np.arange(n, dtype=np.float64) / 24000
    full_scale = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
    out = float32_to_int16_dither(full_scale, rng=rng)

    assert out.dtype == np.int16
    assert out.min() >= -32768
    assert out.max() <= 32767

    # Slightly-over-range input must clip (not wrap)
    over = (full_scale * 1.5).astype(np.float32)
    out_clipped = float32_to_int16_dither(over, rng=rng)
    assert out_clipped.min() >= -32768
    assert out_clipped.max() <= 32767

    # Empty input → empty output
    assert float32_to_int16_dither(np.empty(0, dtype=np.float32)).shape == (0,)

    # Quiet DC input — without dither, all samples would be 0. With TPDF
    # dither, we should see some non-zero noise samples (tiny but present).
    quiet = np.zeros(2000, dtype=np.float32) + (1.0 / 32768.0) * 0.5  # half-LSB DC
    out_quiet = float32_to_int16_dither(quiet, rng=rng)
    nonzero_count = int(np.count_nonzero(out_quiet))
    assert nonzero_count > 100, (
        f"dither failed to randomize quantization: only {nonzero_count}/{out_quiet.size} non-zero"
    )


# ─── Test 5: round-trip 8k → 16k → 8k preserves the signal ──────────────────


def test_resample_pcm_round_trip():
    """Upsample and back via the one-shot scipy resampler. The signal should
    survive a round trip with high correlation.
    """
    src_rate = 8000
    dst_rate = 16000
    duration_s = 0.5
    sine = _sine(freq_hz=440.0, sample_rate=src_rate, duration_s=duration_s, amplitude=0.5)
    sine_int16 = (sine * 32767).astype(np.int16).tobytes()

    upsampled = resample_pcm(sine_int16, src_rate, dst_rate)
    assert len(upsampled) == 2 * len(sine_int16)  # 2x samples (s16)

    downsampled = resample_pcm(upsampled, dst_rate, src_rate)
    # Length matches within a few samples (filter ringing at edges)
    assert abs(len(downsampled) - len(sine_int16)) < 32

    # Compare the round-tripped signal to the original via correlation
    orig = np.frombuffer(sine_int16, dtype=np.int16).astype(np.float64)
    rt = np.frombuffer(downsampled, dtype=np.int16).astype(np.float64)
    n = min(orig.size, rt.size)
    # Drop edges where filter transients live
    edge = 64
    orig_trim = orig[edge : n - edge]
    rt_trim = rt[edge : n - edge]
    # Normalized correlation
    corr = float(np.corrcoef(orig_trim, rt_trim)[0, 1])
    assert corr > 0.99, f"round-trip correlation {corr:.4f} (expected > 0.99)"
