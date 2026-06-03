"""Tests for the TranscriptionAgent + Groq Whisper tool (Groq client mocked)."""

from pathlib import Path

from agencyos.agents.transcription import TranscriptionAgent
from agencyos.graph.state import AgencyState, TranscriptMeta


async def test_agent_transcribes_audio(monkeypatch):
    async def fake_transcribe(audio_path):  # noqa: ANN001
        assert Path(audio_path).name == "meeting.mp3"
        return {
            "transcript": "hello world",
            "meta": {"duration_sec": 12.5, "speaker_count": 1, "language": "en"},
        }

    monkeypatch.setattr(
        "agencyos.tools.transcription.groq_whisper_transcribe", fake_transcribe
    )

    agent = TranscriptionAgent()
    state = AgencyState(user_id="u", audio_path=Path("meeting.mp3"))
    out = await agent.act(state, reasoning="r")
    assert out["transcript"] == "hello world"

    merged = agent.merge(state, out)
    assert merged.transcript == "hello world"
    assert isinstance(merged.transcript_meta, TranscriptMeta)
    assert merged.transcript_meta.duration_sec == 12.5


async def test_agent_without_audio_returns_empty():
    agent = TranscriptionAgent()
    out = await agent.act(AgencyState(user_id="u"), reasoning="r")
    assert out["transcript"] == ""
    assert out["meta"]["speaker_count"] == 0


async def test_tool_maps_groq_response(monkeypatch, tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF....")

    class _Resp:
        text = "transcribed text"
        duration = 8.0
        language = "en"

    class _Transcriptions:
        async def create(self, **kwargs):
            assert kwargs["model"]  # whisper model passed
            assert kwargs["response_format"] == "verbose_json"
            return _Resp()

    class _Audio:
        transcriptions = _Transcriptions()

    class _FakeGroq:
        def __init__(self, **kwargs):
            self.audio = _Audio()

    monkeypatch.setattr("groq.AsyncGroq", _FakeGroq)

    from agencyos.tools.transcription import groq_whisper_transcribe

    result = await groq_whisper_transcribe(audio)
    assert result["transcript"] == "transcribed text"
    assert result["meta"]["duration_sec"] == 8.0
    assert result["meta"]["language"] == "en"
    assert result["meta"]["speaker_count"] == 1
