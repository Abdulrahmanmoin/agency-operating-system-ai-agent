"""Tests for the document loader + RequirementAnalysisAgent (LLM mocked, no network)."""

from agencyos.agents.requirement import RequirementAnalysisAgent
from agencyos.graph.state import AgencyState, Requirements
from agencyos.tools.document_loader import load_document


# ─── document loader ──────────────────────────────────────────────────


def test_load_txt(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("client wants a website", encoding="utf-8")
    assert load_document(f) == "client wants a website"


def test_load_unsupported_raises(tmp_path):
    f = tmp_path / "data.xyz"
    f.write_text("x", encoding="utf-8")
    try:
        load_document(f)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


# ─── source_material helper ───────────────────────────────────────────


def test_source_material_prefers_transcript():
    s = AgencyState(user_id="u", transcript="spoken", notes_text="written")
    assert s.source_material() == "spoken"


def test_source_material_falls_back_to_notes():
    s = AgencyState(user_id="u", notes_text="written")
    assert s.source_material() == "written"


# ─── requirement extraction (mocked Groq) ─────────────────────────────


class _FakeStructured:
    def __init__(self, result):
        self._result = result
        self.captured_messages = None

    async def ainvoke(self, messages):
        self.captured_messages = messages
        return self._result


class _FakeModel:
    def __init__(self, result):
        self.structured = _FakeStructured(result)

    def with_structured_output(self, _schema, **_kwargs):
        return self.structured


def _patch_model(monkeypatch, result, holder=None):
    model = _FakeModel(result)
    if holder is not None:
        holder["model"] = model
    monkeypatch.setattr("agencyos.agents.requirement.get_chat_model", lambda *a, **k: model)


async def test_requirement_extracts_via_llm(monkeypatch):
    expected = Requirements(
        client_goals=["launch DTC store"],
        services=["e-commerce site", "SEO"],
        deadline="mid-October",
        budget="$40,000",
    )
    holder: dict = {}
    _patch_model(monkeypatch, expected, holder)

    agent = RequirementAnalysisAgent()
    state = AgencyState(user_id="u", notes_text="We want to launch a DTC coffee store by October. Budget ~40k.")
    out = await agent.act(state, reasoning="r")

    assert out.client_goals == ["launch DTC store"]
    assert out.budget == "$40,000"
    # the source text was actually passed into the prompt
    user_msg = holder["model"].structured.captured_messages[-1]["content"]
    assert "DTC coffee store" in user_msg


async def test_requirement_empty_source_skips_llm(monkeypatch):
    # If get_chat_model were called it would explode — assert it is NOT called.
    def _boom(*a, **k):
        raise AssertionError("LLM should not be called when there is no source material")

    monkeypatch.setattr("agencyos.agents.requirement.get_chat_model", _boom)

    agent = RequirementAnalysisAgent()
    out = await agent.act(AgencyState(user_id="u"), reasoning="r")
    assert out == Requirements()


async def test_requirement_reason_mentions_char_count():
    agent = RequirementAnalysisAgent()
    s = AgencyState(user_id="u", notes_text="abcde")
    reasoning = await agent.reason(s)
    assert "5 chars" in reasoning
