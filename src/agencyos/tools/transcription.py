"""Groq Whisper transcription tool."""

from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential



@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def groq_whisper_transcribe(audio_path: Path) -> dict:
    """Send an audio file to Groq Whisper and return the transcript + metadata.

    Returns a dict shaped like {"transcript": str, "meta": {...}}.
    """
    # TODO: use groq.AsyncGroq().audio.transcriptions.create(...)
    raise NotImplementedError
