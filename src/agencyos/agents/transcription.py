"""TranscriptionAgent — audio → text via Groq Whisper."""

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState, TranscriptMeta


class TranscriptionAgent(BaseAgent):
    name = "transcription"
    role = "Audio-to-text specialist"
    responsibility = "Convert audio uploads to cleaned, segmented transcripts."
    goal = "Faithful, timestamp-clean transcript ready for extraction."

    async def reason(self, state: AgencyState) -> str:
        return f"Transcribing audio at {state.audio_path} via Groq Whisper."

    async def act(self, state: AgencyState, reasoning: str) -> dict:
        # PLACEHOLDER: real Groq Whisper call lands later.
        return {
            "transcript": f"(placeholder transcript of {state.audio_path})",
            "meta": {"duration_sec": 0.0, "speaker_count": 1, "language": "en"},
        }

    def merge(self, state: AgencyState, output: dict) -> AgencyState:
        state.transcript = output["transcript"]
        state.transcript_meta = TranscriptMeta(**output["meta"])
        return state


run = TranscriptionAgent()
