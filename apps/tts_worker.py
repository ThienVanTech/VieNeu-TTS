"""Singleton TTS worker with an asyncio queue.

Ensures only one synthesis runs at a time on the CPU, preventing resource
contention.  Every incoming request is placed in a FIFO queue and resolved
via an ``asyncio.Future`` so the caller can ``await`` the result.
"""

import asyncio
import io
import logging
import os
import subprocess
import time
import uuid
import wave
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

logger = logging.getLogger("Vieneu.API.Worker")

CACHE_DIR = os.getenv("TTS_CACHE_DIR", "storage/audio_cache")


@dataclass
class TTSRequest:
    """A single synthesis job placed on the queue."""

    text: str
    lang: str
    speed: float
    voice_id: Optional[str]
    output_format: str
    future: asyncio.Future
    temperature: float = 0.4
    top_k: int = 50
    max_chars: int = 256


def _apply_speed(audio: np.ndarray, speed: float, sr: int = 24_000) -> np.ndarray:
    """Change playback speed of *audio* via librosa time-stretch.

    Args:
        audio: Float32 waveform array.
        speed: Multiplier (>1 = faster, <1 = slower).  1.0 is a no-op.
        sr: Sample rate.

    Returns:
        Speed-adjusted waveform as float32 numpy array.
    """
    if abs(speed - 1.0) < 0.01:
        return audio
    if len(audio) == 0:
        return audio

    import librosa

    stretched = librosa.effects.time_stretch(audio, rate=speed)
    return stretched.astype(np.float32)


def _wav_bytes(audio: np.ndarray, sr: int = 24_000) -> bytes:
    """Encode a float32 waveform to WAV bytes (PCM-16)."""
    pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _wav_to_mp3(wav_bytes: bytes) -> bytes:
    """Convert WAV bytes to MP3 via ffmpeg subprocess.

    Raises:
        RuntimeError: If ffmpeg is not installed or conversion fails.
    """
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", "pipe:0",
            "-codec:a", "libmp3lame",
            "-b:a", "128k",
            "-f", "mp3",
            "pipe:1",
        ],
        input=wav_bytes,
        capture_output=True,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace")
        raise RuntimeError(f"ffmpeg failed: {stderr[:500]}")
    return proc.stdout


class TTSWorker:
    """Async singleton worker that processes TTS requests sequentially."""

    def __init__(self, tts_engine: Any) -> None:
        self.tts = tts_engine
        self._queue: asyncio.Queue[TTSRequest] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Launch the background consumer task."""
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._consumer())
            logger.info("TTS worker started")

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    async def submit(self, req: TTSRequest) -> str:
        """Put *req* on the queue and return the resulting file path."""
        await self._queue.put(req)
        return await req.future

    async def _consumer(self) -> None:
        """Infinite loop pulling jobs from the queue."""
        while True:
            req = await self._queue.get()
            try:
                path = await asyncio.get_running_loop().run_in_executor(
                    None, self._synthesize, req
                )
                req.future.set_result(path)
            except Exception as exc:
                if not req.future.done():
                    req.future.set_exception(exc)
            finally:
                self._queue.task_done()

    def _synthesize(self, req: TTSRequest) -> str:
        """Run TTS inference + speed adjustment + encode to file.

        Returns:
            Absolute path to the generated audio file.
        """
        start = time.time()
        logger.info(
            f"Synthesizing: lang={req.lang}, speed={req.speed}, "
            f"voice={req.voice_id}, fmt={req.output_format}, "
            f"temp={req.temperature}, top_k={req.top_k}, "
            f"max_chars={req.max_chars}, len={len(req.text)} chars"
        )

        voice_data = None
        if req.voice_id:
            try:
                voice_data = self.tts.get_preset_voice(req.voice_id)
            except Exception:
                logger.warning(
                    f"Voice '{req.voice_id}' not found, using default"
                )

        kwargs: dict[str, Any] = {
            "temperature": req.temperature,
            "top_k": req.top_k,
            "max_chars": req.max_chars,
        }
        if voice_data is not None:
            kwargs["voice"] = voice_data

        audio: np.ndarray = self.tts.infer(req.text, **kwargs)

        audio = _apply_speed(audio, req.speed)

        wav_data = _wav_bytes(audio)

        if req.output_format == "mp3":
            file_ext = "mp3"
            file_data = _wav_to_mp3(wav_data)
        else:
            file_ext = "wav"
            file_data = wav_data

        os.makedirs(CACHE_DIR, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.{file_ext}"
        filepath = os.path.join(CACHE_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(file_data)

        elapsed = time.time() - start
        logger.info(f"Synthesis complete in {elapsed:.2f}s -> {filepath}")
        return filepath
