"""Groq Whisper transcription tool."""

from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def groq_whisper_transcribe(audio_path: Path) -> dict:
    """Transcribe an audio file via Groq Whisper.

    Returns {"transcript": str, "meta": {duration_sec, speaker_count, language}}.
    Whisper does not diarize, so speaker_count is reported as 1.
    """
    from groq import AsyncGroq

    client = AsyncGroq(api_key=settings.groq_api_key)
    resp = await client.audio.transcriptions.create(
        model=settings.groq_whisper_model,
        file=Path(audio_path),
        response_format="verbose_json",
    )
    return {
        "transcript": resp.text,
        "meta": {
            "duration_sec": float(getattr(resp, "duration", 0.0) or 0.0),
            "speaker_count": 1,
            "language": getattr(resp, "language", None) or "unknown",
        },
    }
