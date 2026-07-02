"""
Audio Surveillance — ambient listening, sound-triggered recording, keyword spotting.
Extends agent/audio_recorder.py.
"""
import os
import asyncio
import struct
import math
import tempfile
from pathlib import Path
from datetime import datetime
from loguru import logger

_monitoring = False
_threshold = 300
_monitor_task = None


def _rms(data: bytes) -> float:
    """Calculate RMS energy from raw audio data."""
    if len(data) < 2:
        return 0
    count = len(data) // 2
    fmt = "<" + "h" * count
    try:
        samples = struct.unpack(fmt, data[:count * 2])
        sum_squares = sum(s * s for s in samples)
        return math.sqrt(sum_squares / count)
    except Exception:
        return 0


async def _monitor_loop(duration_seconds: int, alert_callback):
    """Monitor ambient sound, record when above threshold."""
    import pyaudio
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100

    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                    input=True, frames_per_buffer=CHUNK)

    recorded = False
    frames = []
    start_time = datetime.now()

    while _monitoring and (datetime.now() - start_time).seconds < duration_seconds:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            energy = _rms(data)

            if energy > _threshold:
                frames.append(data)
                if not recorded:
                    logger.info(f"Sound detected (RMS: {energy:.0f})")
                    recorded = True
            elif recorded:
                pass
        except Exception:
            await asyncio.sleep(0.1)

    stream.stop_stream()
    stream.close()
    p.terminate()

    if recorded and frames:
        import wave
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        wf = wave.open(tmp.name, "wb")
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))
        wf.close()

        if alert_callback:
            await alert_callback(tmp.name)

        return tmp.name
    return None


def listen(seconds: int = 10) -> str:
    """Simple listen - records microphone for N seconds."""
    from agent.audio_recorder import record_audio
    result = record_audio(seconds)
    return result


async def ambient_start(duration: int = 300, threshold: int = 300, callback=None):
    global _monitoring, _threshold, _monitor_task
    if _monitoring:
        return "Ambient monitoring sudah aktif."

    _monitoring = True
    _threshold = threshold

    async def _run():
        while _monitoring:
            result = await _monitor_loop(duration, callback)
            if result:
                logger.info(f"Ambient recording saved: {result}")

    _monitor_task = asyncio.create_task(_run())
    return f"Ambient monitoring started (threshold: {threshold}, duration: {duration}s)"


def ambient_stop():
    global _monitoring, _monitor_task
    _monitoring = False
    if _monitor_task:
        _monitor_task.cancel()
        _monitor_task = None
    return "Ambient monitoring stopped."


def ambient_status():
    return f"Ambient monitoring: {'AKTIF' if _monitoring else 'TIDAK AKTIF'}"
