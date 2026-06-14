"""TranscriptionAgent — audio → text via Groq Whisper."""

from agents.base import BaseAgent
from graph.state import AgencyState, TranscriptMeta


class TranscriptionAgent(BaseAgent):
    name = "transcription"
    role = "Audio-to-text specialist"
    responsibility = "Convert audio uploads to cleaned, segmented transcripts."
    goal = "Faithful, timestamp-clean transcript ready for extraction."

    async def reason(self, state: AgencyState) -> str:
        return f"Transcribing audio at {state.audio_path} via Groq Whisper ({state.audio_path and 'present' or 'no file'})."

    async def act(self, state: AgencyState, reasoning: str) -> dict:
        from tools.transcription import groq_whisper_transcribe

        if state.audio_path is None:
            return {
                "transcript": "",
                "meta": {"duration_sec": 0.0, "speaker_count": 0, "language": "unknown"},
            }
        return await groq_whisper_transcribe(state.audio_path)

    def merge(self, state: AgencyState, output: dict) -> AgencyState:
        state.transcript = output["transcript"]
        state.transcript_meta = TranscriptMeta(**output["meta"])
        return state


run = TranscriptionAgent()
