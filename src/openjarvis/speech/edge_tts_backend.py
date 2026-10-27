"""Edge-TTS backend — free, low-latency Microsoft Neural voices (PT-BR & multilingual).

Provides the iconic Brazilian Portuguese male voice ``pt-BR-AntonioNeural`` (and
``pt-BR-FranciscaNeural``, ``en-GB-RyanNeural`` British Jarvis, etc.) with zero
API keys and zero GPU VRAM overhead. Automatically converts MP3 output to WAV
when ``output_format="wav"`` is requested by the CLI or API server.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from typing import List

from openjarvis.core.registry import TTSRegistry
from openjarvis.speech.tts import TTSBackend, TTSResult

logger = logging.getLogger(__name__)

_DEFAULT_VOICE = "pt-BR-AntonioNeural"

_CURATED_VOICES = [
    # Brazilian Portuguese (J.A.R.V.I.S. / F.R.I.D.A.Y. style)
    "pt-BR-AntonioNeural",
    "pt-BR-FranciscaNeural",
    "pt-BR-ThalitaMultilingualNeural",
    # British English (Classic Paul Bettany J.A.R.V.I.S.)
    "en-GB-RyanNeural",
    "en-GB-ThomasNeural",
    "en-GB-SoniaNeural",
    # US English
    "en-US-ChristopherNeural",
    "en-US-GuyNeural",
    "en-US-AriaNeural",
]


def _clean_text_for_speech(text: str) -> str:
    """Remove Markdown formatting, code blocks, and URLs so Jarvis speaks naturally."""
    # Replace fenced code blocks with a brief spoken notice
    cleaned = re.sub(
        r"```[\s\S]*?```",
        " Código exibido na tela. ",
        text,
    )
    # Remove inline code backticks but keep the word
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    # Convert markdown links [label](url) -> label
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    # Strip raw URLs
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    # Strip markdown headers, bold, italics, bullet markers
    cleaned = re.sub(r"(?m)^\s*#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    cleaned = re.sub(r"(?m)^\s*[-*+]\s+", "", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _speed_to_rate_str(speed: float) -> str:
    """Convert a float speed multiplier (e.g. 1.08) to Edge-TTS rate string (e.g. '+8%')."""
    pct = int(round((speed - 1.0) * 100))
    if pct >= 0:
        return f"+{pct}%"
    return f"{pct}%"


def _mp3_bytes_to_wav(mp3_bytes: bytes) -> tuple[bytes, int, float]:
    """Decode MP3 bytes to 24kHz 16-bit mono WAV bytes using soundfile or PyAV."""
    if not mp3_bytes:
        return b"", 24000, 0.0

    # Try soundfile first (libsndfile >= 1.1 supports MP3 directly)
    try:
        import numpy as np
        import soundfile as sf

        data, sr = sf.read(io.BytesIO(mp3_bytes), dtype="float32")
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        out = io.BytesIO()
        sf.write(out, data, sr, format="WAV", subtype="PCM_16")
        duration = len(data) / float(sr) if sr else 0.0
        return out.getvalue(), int(sr), duration
    except Exception:
        pass

    # Fallback to PyAV (installed with faster-whisper)
    try:
        import wave
        import av
        import numpy as np

        container = av.open(io.BytesIO(mp3_bytes))
        resampler = av.AudioResampler(format="s16", layout="mono", rate=24000)
        pcm_chunks: list[bytes] = []
        total_samples = 0
        for frame in container.decode(audio=0):
            for out_frame in resampler.resample(frame):
                arr = out_frame.to_ndarray()
                pcm_chunks.append(arr.tobytes())
                total_samples += arr.shape[-1]
        for out_frame in resampler.resample(None):
            arr = out_frame.to_ndarray()
            pcm_chunks.append(arr.tobytes())
            total_samples += arr.shape[-1]

        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(b"".join(pcm_chunks))
        return wav_buf.getvalue(), 24000, total_samples / 24000.0
    except Exception as exc:
        logger.debug("MP3->WAV conversion fallback returning raw MP3: %s", exc)
        return mp3_bytes, 24000, 0.0


async def _synthesize_edge_async(text: str, voice: str, rate: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
    audio_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            audio_chunks.append(chunk["data"])
    return b"".join(audio_chunks)


@TTSRegistry.register("edge_tts")
class EdgeTTSBackend(TTSBackend):
    """Microsoft Edge Neural TTS — natural J.A.R.V.I.S. voice in PT-BR and EN."""

    backend_id = "edge_tts"

    def __init__(self, default_voice: str = _DEFAULT_VOICE) -> None:
        self._default_voice = default_voice

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.05,
        output_format: str = "wav",
    ) -> TTSResult:
        voice = (voice_id or self._default_voice).strip()
        # If a Kokoro/OpenAI voice ID was accidentally passed, use our PT-BR Jarvis voice
        if "-" not in voice:
            voice = self._default_voice

        spoken_text = _clean_text_for_speech(text)
        if not spoken_text:
            return TTSResult(
                audio=b"",
                format=output_format,
                voice_id=voice,
                sample_rate=24000,
                metadata={"backend": "edge_tts"},
            )

        rate_str = _speed_to_rate_str(speed)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                mp3_bytes = pool.submit(
                    lambda: asyncio.run(_synthesize_edge_async(spoken_text, voice, rate_str))
                ).result(timeout=30)
        else:
            mp3_bytes = asyncio.run(_synthesize_edge_async(spoken_text, voice, rate_str))

        if output_format.lower() == "wav":
            wav_bytes, sr, duration = _mp3_bytes_to_wav(mp3_bytes)
            return TTSResult(
                audio=wav_bytes,
                format="wav",
                duration_seconds=duration,
                voice_id=voice,
                sample_rate=sr,
                metadata={"backend": "edge_tts"},
            )

        return TTSResult(
            audio=mp3_bytes,
            format="mp3",
            duration_seconds=0.0,
            voice_id=voice,
            sample_rate=24000,
            metadata={"backend": "edge_tts"},
        )

    def available_voices(self) -> List[str]:
        return list(_CURATED_VOICES)

    def health(self) -> bool:
        try:
            import edge_tts  # noqa: F401

            return True
        except ImportError:
            return False


__all__ = ["EdgeTTSBackend"]
