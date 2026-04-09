"""Telnyx media stream WebSocket handler.

Telnyx's bidirectional media streaming is a WebSocket where each message is
a small JSON envelope:

    {"event": "connected",  "version": "..."}
    {"event": "start",       "start": {"stream_id": "...", "call_control_id": "..."}}
    {"event": "media",       "media": {"payload": "<base64 PCM>", "track": "inbound"}}
    {"event": "stop",        "stop": {}}

To play audio back at the caller, we send messages of the same shape with
`event: media` — Telnyx mixes our frames into the outbound track.

We negotiated L16 PCM at 16 kHz mono in streaming_start, so inbound payloads
are int16 LE 16 kHz mono — which is what voxtral STT expects, with no
resampling needed. TTS output is 24 kHz and gets resampled to 16 kHz before
being sent out.

Turn detection: we buffer inbound PCM until we see ``VOICE_CALL_STT_SILENCE_MS``
of below-threshold RMS, then fire STT on the accumulated buffer. Very simple
VAD — good enough for Phase 1. Barge-in (interrupting bot while it speaks)
is deferred to Phase 2.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from typing import Any, Optional


# Strip tool-call XML / function-call markup that some models (Mistral large
# in particular) emit in the assistant content field instead of using the
# structured tool_calls API. We can't synthesize JSON or XML out loud, so
# any reply containing only this markup is treated as "no useful answer".
#
# Two markup styles seen so far in the wild:
#   1. XML-tagged:  <tool_call>{...}</tool_call>
#                   <function_call>{...}</function_call>
#                   <|tool_call_begin|>...<|tool_call_end|>
#   2. Function-call syntax (most recent):
#                   tool_name({"key": "value"})
#                   task_create({"agent_id": "..."})
#
# The function-call form is harder to detect because legitimate text can
# contain parens. We use a strict pattern: an identifier followed by ``({``
# and matching close. JSON nesting handled with a small bracket-balancer.
_XML_TOOL_CALL_RE = re.compile(
    r"<tool_call>.*?</tool_call>|<function_call>.*?</function_call>|"
    r"<\|tool_call_begin\|>.*?<\|tool_call_end\|>",
    re.DOTALL | re.IGNORECASE,
)
_FUNCTION_CALL_START_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\(\s*\{")


def _strip_function_call_syntax(text: str) -> str:
    """Remove ``identifier({...})`` patterns from text via bracket matching.

    Handles nested JSON braces correctly. The model sometimes also leaves
    a trailing comma or unclosed quote — we just chomp until we find the
    matching ``)`` or run out of characters.
    """
    out = []
    i = 0
    while i < len(text):
        m = _FUNCTION_CALL_START_RE.search(text, i)
        if not m:
            out.append(text[i:])
            break
        # Append text before the match.
        out.append(text[i : m.start()])
        # Skip past the call: balance braces starting from the `{` we found.
        # m.end() points just after `({`. The brace count starts at 1.
        depth = 1
        j = m.end()
        while j < len(text) and depth > 0:
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            j += 1
        # j now points just after the matching `}`. Skip optional `)`.
        if j < len(text) and text[j] == ")":
            j += 1
        i = j
    return "".join(out)


def _sanitize_agent_reply(text: str) -> str:
    """Remove tool-call markup (XML or function-call syntax) and return text."""
    if not text:
        return ""
    cleaned = _XML_TOOL_CALL_RE.sub("", text)
    cleaned = _strip_function_call_syntax(cleaned)
    # Drop bare JSON objects that survived (model emitting raw JSON dicts).
    cleaned = re.sub(r"\{[^{}]*\}", "", cleaned)
    return cleaned.strip()

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models.voice_call import VoiceCall, VoiceCallTurn
import numpy as np

from . import call_state_store
from .agent_bridge import VoiceAgentSession, run_agent_turn
from .audio_codec import (
    BYTES_PER_MS_8K,
    SoxrStreamDownsampler,
    TELNYX_PCM_SAMPLE_RATE,
    VOXTRAL_STT_SAMPLE_RATE,
    VOXTRAL_TTS_SAMPLE_RATE,
    decode_g711,
    encode_g711,
    float32_to_int16_dither,
    pcm_rms,
    resample_pcm,
    silence_byte_for_encoding,
)
from .state_machine import CallRuntime, local_call_runtime
from .telnyx_client import TelnyxClient
from .voxtral_client import (
    VoxtralError,
    _iter_voxtral_tts_float32,
    transcribe_pcm,
)

logger = logging.getLogger(__name__)

# ── Tuning ──────────────────────────────────────────────────────────────────
# All durations in milliseconds. Frame sizes are derived from the negotiated
# Telnyx PCM rate (8 kHz after μ-law decode → 16 bytes/ms of int16 LE PCM).

SILENCE_RMS_THRESHOLD = 250  # int16 RMS below this = silence. Tune per mic + carrier.
OUTBOUND_FRAME_MS = 20       # 20 ms = 160 μ-law bytes — standard telephony frame size

# Max PCM we'll ever accumulate for a single user turn (30 s @ 8 kHz).
# Just a safety cap to prevent runaway memory if VAD never fires
# end-of-speech.
MAX_TURN_BUFFER_BYTES = BYTES_PER_MS_8K * 30_000


async def handle_media_stream(
    ws: WebSocket,
    *,
    call_id: str,
) -> None:
    """Lifecycle of a single Telnyx media stream WebSocket connection.

    This worker becomes the **owner** of the call's audio loop. We:

    1. Read persistent state from Redis (cross-worker safe — populated by
       whichever worker handled the initial POST /api/voice/call)
    2. Construct a per-worker CallRuntime in this worker's local registry
    3. Build a VoiceAgentSession with the persistent system_prompt + agent_id
    4. Start the max-duration timer here on the owner worker
    5. Pump inbound media events until the WS closes
    6. Clean up local state on disconnect

    Webhooks for this call may continue arriving on OTHER workers — they
    only update DB state and don't touch our local runtime.
    """
    await ws.accept()

    # Load persistent state from Redis (any worker can do this).
    persistent = call_state_store.get(call_id)
    if persistent is None:
        logger.warning(
            "Media stream WS: no Redis state for call_id=%s (call likely ended or never started)",
            call_id,
        )
        await ws.close(code=1008)
        return

    if not persistent.get("use_voxtral"):
        # Telnyx-only mode shouldn't be opening a media stream.
        # If it does anyway, just close and let Telnyx-only flow handle it.
        logger.warning(
            "Media stream WS opened for non-voxtral call %s — closing",
            call_id,
        )
        await ws.close(code=1003)
        return

    # Construct the per-worker CallRuntime. This is local to THIS worker —
    # other workers don't see it. The conversation history (VoiceAgentSession)
    # also lives here because in voxtral mode all turns happen on this worker.
    runtime = local_call_runtime.create(
        call_id,
        direction=persistent.get("direction") or "outbound",
        media_encoding=persistent.get("media_encoding") or "PCMU",
        use_voxtral=True,
        telnyx_call_control_id=persistent.get("telnyx_call_control_id"),
        initial_message=persistent.get("initial_message"),
    )
    runtime.agent_session = VoiceAgentSession(
        call_id=call_id,
        agent_id=persistent.get("agent_id") or "",
        user_id=persistent.get("user_id") or None,
        system_prompt=persistent.get("system_prompt"),
    )
    runtime.ws = ws
    logger.info(
        "Call %s media stream connected (pid=%s)",
        call_id,
        __import__("os").getpid(),
    )

    # Max-duration watchdog: previously this was started in service.initiate_outbound
    # but that runs on a potentially different worker. Move it here so it runs
    # on the audio loop owner where it can actually act on the runtime.
    runtime.max_duration_task = asyncio.create_task(
        _max_duration_timer(call_id, settings.VOICE_CALL_MAX_DURATION_SEC)
    )

    # The conversation loop runs independently of the frame pump. It waits
    # for user speech and fires agent turns in the background.
    loop_task = asyncio.create_task(_conversation_loop(runtime))
    runtime.loop_task = loop_task

    # Inbound PCM buffer for the current user turn (populated by frame pump,
    # consumed by conversation loop via transfer_user_turn()).
    turn_buffer = bytearray()
    silence_ms_accumulator = 0
    min_turn_ms = settings.VOICE_CALL_STT_MIN_TURN_MS
    silence_cutoff_ms = settings.VOICE_CALL_STT_SILENCE_MS

    in_speech = False         # have we heard non-silent audio yet?
    speech_ms = 0             # ms of non-silent audio in current turn

    try:
        async for message in _iter_ws_json(ws):
            event = message.get("event")

            if event == "connected":
                # Telnyx handshake — nothing to do.
                continue

            if event == "start":
                # Telnyx puts stream_id at the TOP level of every WS message,
                # not nested inside the `start` payload. We grab it here
                # so outbound media events can echo it.
                runtime.stream_id = (
                    message.get("stream_id")
                    or (message.get("start") or {}).get("stream_id")
                )
                start_payload = message.get("start") or {}
                media_format = start_payload.get("media_format") or {}
                negotiated_encoding = (media_format.get("encoding") or "PCMU").upper()
                negotiated_sample_rate = int(
                    media_format.get("sample_rate") or 8000
                )
                runtime.media_encoding = negotiated_encoding
                runtime.inbound_sample_rate = negotiated_sample_rate
                # Mirror the negotiated encoding + stream_id to Redis so any
                # other worker that handles a webhook for this call sees the
                # current state.
                call_state_store.update(
                    call_id,
                    {
                        "media_encoding": negotiated_encoding,
                        "stream_id": runtime.stream_id or "",
                    },
                )
                logger.info(
                    "Media stream started for call %s: encoding=%s, sample_rate=%s",
                    call_id,
                    negotiated_encoding,
                    negotiated_sample_rate,
                )
                # Speak opening message. The conversation loop will pick it
                # up via the lock; we set the event here to signal "ready".
                if not runtime.initial_message_sent and runtime.initial_message:
                    asyncio.create_task(
                        _speak_and_then_listen(runtime, runtime.initial_message)
                    )
                    runtime.initial_message_sent = True
                continue

            if event == "media":
                media = message.get("media") or {}
                track = (media.get("track") or "").lower()
                payload_b64 = media.get("payload")

                # Accept any "inbound" track variant; reject only known
                # outbound echoes. Telnyx has been seen to use "inbound",
                # "inbound_track", or omit the field — be permissive.
                if track and "outbound" in track:
                    continue
                if not payload_b64:
                    continue

                # Skip ALL processing if bot is currently speaking — prevents
                # self-STT loops AND saves CPU during long TTS playback so the
                # speak loop's pacing isn't competing with VAD work. Barge-in
                # (Phase 2) will revisit this.
                if runtime.turn_lock.locked():
                    if turn_buffer:
                        turn_buffer.clear()
                    in_speech = False
                    speech_ms = 0
                    silence_ms_accumulator = 0
                    continue

                # Decode the negotiated G.711 codec (PCMU or PCMA) to
                # int16 LE PCM at 8 kHz before buffering.
                g711_bytes = base64.b64decode(payload_b64)
                pcm_frame = decode_g711(g711_bytes, runtime.media_encoding)

                # bytes/ms = sample_rate * 2 (int16) / 1000. Computed from
                # the negotiated rate (defensive against any future codec
                # change), but in practice this is BYTES_PER_MS_8K = 16.
                inbound_bytes_per_ms = runtime.inbound_sample_rate * 2 // 1000
                frame_ms = (
                    len(pcm_frame) // inbound_bytes_per_ms
                    if inbound_bytes_per_ms
                    else 0
                )
                frame_rms = pcm_rms(bytes(pcm_frame))
                is_silent = frame_rms < SILENCE_RMS_THRESHOLD

                if not in_speech:
                    # Begin-of-speech: drop silent frames; start buffering on
                    # the first non-silent frame.
                    if not is_silent:
                        in_speech = True
                        speech_ms = frame_ms
                        silence_ms_accumulator = 0
                        turn_buffer.extend(pcm_frame)
                    # else: discard silent frame — no point buffering it
                    continue

                # In a speech turn: always buffer the frame.
                turn_buffer.extend(pcm_frame)
                if len(turn_buffer) > MAX_TURN_BUFFER_BYTES:
                    del turn_buffer[:-MAX_TURN_BUFFER_BYTES]

                if is_silent:
                    silence_ms_accumulator += frame_ms
                else:
                    silence_ms_accumulator = 0
                    speech_ms += frame_ms

                # End-of-speech: trailing silence long enough AND we captured
                # at least min_turn_ms of actual speech (not just silence).
                if (
                    silence_ms_accumulator >= silence_cutoff_ms
                    and speech_ms >= min_turn_ms
                ):
                    captured = bytes(turn_buffer)
                    turn_buffer.clear()
                    silence_ms_accumulator = 0
                    speech_ms = 0
                    in_speech = False
                    asyncio.create_task(
                        _handle_user_turn(runtime, captured)
                    )
                continue

            if event == "stop":
                logger.info("Telnyx media stream stop event for call %s", call_id)
                break

    except WebSocketDisconnect:
        logger.info("Media stream WS disconnected for call %s", call_id)
    except Exception:
        logger.exception("Media stream loop crashed for call %s", call_id)
    finally:
        try:
            if not loop_task.done():
                loop_task.cancel()
        except Exception:
            pass
        # Tear down per-worker local state. Other workers don't see this
        # registry. Redis state is cleaned up by the call.hangup webhook
        # handler (which can run on any worker).
        local_call_runtime.remove(call_id)


async def _max_duration_timer(call_id: str, seconds: int) -> None:
    """Hard-cap timer — hangs up the call if it exceeds ``seconds``.

    Runs on the WS owner worker so it can find the local runtime to
    cancel asyncio tasks. Reads the call's cci from Redis (the WS owner
    might not have it cached if it raced with state updates).
    """
    try:
        await asyncio.sleep(seconds)
    except asyncio.CancelledError:
        return

    runtime = local_call_runtime.get(call_id)
    cci = None
    if runtime is not None and runtime.telnyx_call_control_id:
        cci = runtime.telnyx_call_control_id
    else:
        # Fall back to Redis lookup.
        persistent = call_state_store.get(call_id)
        if persistent:
            cci = persistent.get("telnyx_call_control_id")

    if not cci:
        return

    logger.warning(
        "Max duration (%ss) hit for call %s — hanging up", seconds, call_id
    )
    try:
        client = TelnyxClient()
        await client.hangup(call_control_id=cci)
    except Exception:
        logger.exception("Failed to hangup call %s on max duration", call_id)


async def _iter_ws_json(ws: WebSocket):
    """Iterate over parsed JSON messages from a WebSocket."""
    while True:
        text = await ws.receive_text()
        try:
            yield json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Received non-JSON WS message: %s", text[:200])


async def _conversation_loop(runtime: CallRuntime) -> None:
    """Currently a no-op shell — frame pump hands off to _handle_user_turn()
    directly. Kept as a spawn-point so Phase 2 features (barge-in timers,
    watchdog for silence, etc.) have a home.
    """
    try:
        # Keep the task alive until the call ends. We don't actually do
        # periodic work here today — all logic is driven by inbound frames.
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        pass


async def _speak_and_then_listen(
    runtime: CallRuntime,
    text: str,
) -> None:
    """Synthesize `text` via voxtral, send as audio frames, persist as turn."""
    async with runtime.turn_lock:
        try:
            await _speak_text(runtime, text, speaker="bot")
        except Exception:
            logger.exception(
                "Failed to speak text for call %s", runtime.call_id
            )


async def _handle_user_turn(runtime: CallRuntime, pcm: bytes) -> None:
    """End-to-end user turn: transcribe → agent → speak reply."""
    if runtime.agent_session is None:
        logger.warning(
            "User turn ready but no agent session for call %s",
            runtime.call_id,
        )
        return

    async with runtime.turn_lock:
        # STT — voxtral prefers 16 kHz. Resample from whatever Telnyx
        # negotiated for inbound (8 kHz for PCMU, 16 kHz for L16). When
        # the rates already match this is a no-op inside resample_pcm.
        pcm_16k = resample_pcm(
            pcm, runtime.inbound_sample_rate, VOXTRAL_STT_SAMPLE_RATE
        )
        try:
            transcript = await transcribe_pcm(
                pcm_16k,
                sample_rate=VOXTRAL_STT_SAMPLE_RATE,
                language="en",
            )
        except Exception:
            logger.exception("STT failed during call %s", runtime.call_id)
            return

        if not transcript.strip():
            return  # Empty transcript — silently skip; common for noise/breath

        logger.info("Call %s user: %r", runtime.call_id, transcript)

        _persist_turn(runtime.call_id, speaker="user", text=transcript)

        try:
            reply = await run_agent_turn(runtime.agent_session, transcript)
        except Exception:
            logger.exception("Agent turn failed for call %s", runtime.call_id)
            reply = "I hit an error. Could you try again?"

        # Strip any tool-call XML the model embedded in the content (Mistral
        # large does this) and use the natural-language remainder. If nothing
        # is left, fall back to a generic acknowledgment so the user isn't
        # left in dead silence.
        spoken = _sanitize_agent_reply(reply)
        if not spoken:
            logger.warning(
                "Call %s agent reply was only tool-call markup — using fallback",
                runtime.call_id,
            )
            spoken = "Let me think about that for a moment."

        logger.info("Call %s bot: %r", runtime.call_id, spoken[:200])

        try:
            await _speak_text(runtime, spoken, speaker="bot")
        except Exception:
            logger.exception(
                "Failed to speak agent reply for call %s",
                runtime.call_id,
            )


async def _speak_text(
    runtime: CallRuntime,
    text: str,
    *,
    speaker: str,
) -> None:
    """Synthesize text via Voxtral, frame-stream to Telnyx, persist the turn.

    Buffered pipeline using PCMU @ 8 kHz on the outbound side, mirroring
    pipecat's production Telnyx serializer (which is the de-facto reference
    for voice-AI on Telnyx):

        Voxtral SSE float32 chunks @ 24 kHz
            → float32_to_int16_dither (TPDF dither at the float→int16 boundary)
            → SoxrStreamDownsampler 24k → 8k (libsoxr "VHQ", same lib pipecat uses)
            → peak normalize to 0.9 (linear gain — Voxtral is too quiet without)
            → encode_g711 PCMU
            → fixed-cadence 20 ms frame loop over WebSocket

    Why each step:
    - We dither + quantize FIRST (in float32 chunks as they arrive) so the
      soxr int16 stream resampler gets correctly-quantized input. soxr's
      VHQ filter then handles the 24 → 8 kHz downsampling with chunk-
      boundary state, which is the highest-quality option short of HD voice.
    - Peak normalize to 0.9 only — Voxtral synthesizes at ~-11 dBFS RMS
      and would be inaudible on a phone line otherwise. No nonlinear
      processing (a soft-clip experiment was a disaster).
    - μ-law encode + 160-byte (20 ms) frames — the standard telephony
      packing that every Telnyx codec sample uses.

    Telnyx is now configured in streaming_start with no explicit codec
    (PCMU 8 kHz default), matching ``team-telnyx/demo-python-telnyx/
    fastapi-v2v-over-media-streaming`` (Telnyx's own AI demo).

    The full TTS is pre-buffered before send so Telnyx gets a continuous
    20 ms cadence with no underruns from Mistral's bursty delta emission.

    MUST be called inside runtime.turn_lock — prevents overlapping TTS
    and self-STT loops while the bot is talking.
    """
    ws = runtime.ws
    if ws is None:
        logger.warning(
            "No WebSocket on runtime %s — cannot speak", runtime.call_id
        )
        return

    # ── DSP pipeline matching smoke_tts_quality.py exactly ─────────────────
    f32_chunks: list[np.ndarray] = []
    try:
        async for f32 in _iter_voxtral_tts_float32(
            text,
            voice_id=settings.VOXTRAL_VOICE_ID,
            api_key=settings.MISTRAL_API_KEY,
            model=settings.VOXTRAL_TTS_MODEL,
        ):
            f32_chunks.append(f32)
    except VoxtralError as exc:
        logger.warning("Voxtral TTS failed for call %s: %s", runtime.call_id, exc)
        return
    except Exception:
        logger.exception("Unexpected error during Voxtral TTS for call %s", runtime.call_id)
        return

    if not f32_chunks:
        logger.warning("Voxtral TTS returned no chunks for call %s", runtime.call_id)
        return

    # ── Peak normalization (linear gain) ──────────────────────────────────
    # Voxtral synthesizes very quietly (~0.04 RMS / -11 dBFS peak typical).
    # Boost so the loudest sample reaches 0.9 (-0.9 dBFS) before resampling
    # and dithering. Doing this in float32 before quantization is the cleanest
    # place — no clipping, no compander interaction. Linear gain only;
    # nonlinear shaping (soft-clip / tanh) was tried and produced broadband
    # distortion. Pipecat's reference doesn't normalize because their TTS
    # providers (ElevenLabs, Cartesia) deliver at proper levels — Voxtral
    # does not, so we have to.
    full_f32 = np.concatenate(f32_chunks)
    peak = float(np.max(np.abs(full_f32))) if full_f32.size else 0.0
    rms = (
        float(np.sqrt(np.mean(full_f32 * full_f32))) if full_f32.size else 0.0
    )
    if peak > 1e-4:
        gain = 0.9 / peak
        full_f32 = full_f32 * gain
        gain_db = 20 * float(np.log10(gain))
        post_peak = 0.9
    else:
        gain_db = 0.0
        post_peak = 0.0

    # ── float32 24 kHz → int16 24 kHz (TPDF dither) ───────────────────────
    # Quantize once at the boundary using TPDF dither so the int16 stream
    # going into soxr is correctly dithered. (soxr's stream resampler is
    # int16 in / int16 out, matching pipecat's ``SOXRStreamAudioResampler``
    # configuration. Float32 → int16 needs to happen before resampling.)
    pcm_24k_int16 = float32_to_int16_dither(full_f32)

    # ── 24 kHz → 8 kHz via libsoxr "VHQ" stream resampler ─────────────────
    # The same resampler pipecat uses for production Twilio/Telnyx voice
    # agents. Maintains internal state across chunks and uses a much
    # higher-quality kernel than scipy's resample_poly or our previous
    # hand-rolled 63-tap Kaiser FIR. This is the single highest-leverage
    # change in the whole audio path.
    downsampler = SoxrStreamDownsampler(
        in_rate=VOXTRAL_TTS_SAMPLE_RATE,
        out_rate=TELNYX_PCM_SAMPLE_RATE,
    )
    pcm_8k_int16_arr = np.concatenate(
        [downsampler.process(pcm_24k_int16), downsampler.flush()]
    )
    pcm_8k_int16 = pcm_8k_int16_arr.tobytes()

    # ── PCMU encode ────────────────────────────────────────────────────────
    # Standard G.711 μ-law via audioop.lin2ulaw (one byte per sample).
    # Telnyx's bidirectional path defaults to PCMU 8 kHz on both directions,
    # so the bytes we send here are exactly what Telnyx expects.
    OUTBOUND_CODEC = "PCMU"
    audio_bytes = encode_g711(pcm_8k_int16, OUTBOUND_CODEC)

    duration_ms = (
        len(pcm_8k_int16) // 2 * 1000 // TELNYX_PCM_SAMPLE_RATE
    )
    logger.info(
        "TTS levels call=%s codec=PCMU/8k duration_ms=%d gain=%+.1fdB "
        "rms_in=%.3f peak_out=%.3f",
        runtime.call_id,
        duration_ms,
        gain_db,
        rms,
        post_peak,
    )

    # PCMU @ 8 kHz: 1 byte/sample × 8 samples/ms = 8 bytes/ms.
    # 20 ms frame = 160 bytes — the standard telephony packing.
    bytes_per_ms_g711 = TELNYX_PCM_SAMPLE_RATE // 1000  # 8
    frame_bytes = bytes_per_ms_g711 * OUTBOUND_FRAME_MS  # 160
    if frame_bytes <= 0:
        return

    silence_byte = silence_byte_for_encoding(OUTBOUND_CODEC)

    total = len(audio_bytes)
    frame_period_s = OUTBOUND_FRAME_MS / 1000.0
    num_frames = (total + frame_bytes - 1) // frame_bytes

    # Pre-build every WS envelope upfront. The hot loop then only does
    # send + sleep — no base64, no JSON, no string concatenation per frame.
    # For a 10 s reply that's 500 frames; pre-building takes <5 ms total.
    #
    # Envelope shape matches Telnyx's official V2V demo and pipecat's
    # TelnyxFrameSerializer EXACTLY: just `event` and `media.payload`.
    # No `stream_id` field — Telnyx's reference implementations omit it.
    envelopes: list[str] = []
    for i in range(num_frames):
        chunk = audio_bytes[i * frame_bytes : (i + 1) * frame_bytes]
        if len(chunk) < frame_bytes:
            chunk = chunk + silence_byte * (frame_bytes - len(chunk))
        envelopes.append(
            json.dumps(
                {
                    "event": "media",
                    "media": {"payload": base64.b64encode(chunk).decode("ascii")},
                }
            )
        )

    # Monotonic-deadline pacer: each frame's send target is computed from
    # the loop start time, NOT from the previous iteration. This means a
    # slow ws.send_text() (5-10 ms of JSON+base64+TCP) doesn't push every
    # subsequent frame later — the next sleep just shrinks to compensate.
    loop = asyncio.get_running_loop()
    loop_start = loop.time()

    # Diagnostics: measure per-frame send latency, count frames that miss
    # their deadline, and track the worst lag. Logged once at end-of-speak
    # so we can correlate with audible glitches.
    behind_count = 0
    max_lag_ms = 0.0
    send_total_s = 0.0
    send_max_s = 0.0

    for frame_index, envelope in enumerate(envelopes):
        send_t0 = loop.time()
        try:
            await ws.send_text(envelope)
        except Exception:
            logger.exception(
                "WebSocket send failed mid-speak for call %s",
                runtime.call_id,
            )
            return
        send_dt = loop.time() - send_t0
        send_total_s += send_dt
        if send_dt > send_max_s:
            send_max_s = send_dt

        next_deadline = loop_start + (frame_index + 1) * frame_period_s
        now = loop.time()
        delay = next_deadline - now
        if delay > 0:
            await asyncio.sleep(delay)
        else:
            behind_count += 1
            lag_ms = -delay * 1000.0
            if lag_ms > max_lag_ms:
                max_lag_ms = lag_ms

    wall_ms = (loop.time() - loop_start) * 1000.0
    logger.info(
        "TTS pacing call=%s frames=%d wall_ms=%.0f expected_ms=%d "
        "behind=%d max_lag_ms=%.1f send_avg_us=%.0f send_max_us=%.0f",
        runtime.call_id,
        num_frames,
        wall_ms,
        num_frames * OUTBOUND_FRAME_MS,
        behind_count,
        max_lag_ms,
        (send_total_s / num_frames) * 1e6 if num_frames else 0.0,
        send_max_s * 1e6,
    )

    _persist_turn(runtime.call_id, speaker=speaker, text=text)


def _persist_turn(call_id: str, *, speaker: str, text: str) -> None:
    """Insert a VoiceCallTurn row. Best-effort — logs + continues on failure."""
    db: Optional[Session] = None
    try:
        db = SessionLocal()
        # Compute next turn_index
        existing = (
            db.query(VoiceCallTurn)
            .filter(VoiceCallTurn.call_id == call_id)
            .count()
        )
        turn = VoiceCallTurn(
            call_id=call_id,
            turn_index=existing,
            speaker=speaker,
            text=text,
        )
        db.add(turn)
        db.commit()
    except Exception:
        logger.exception(
            "Failed to persist voice call turn for call %s", call_id
        )
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db is not None:
            db.close()
