"""Tests for the agent registry + capabilities menu (no LLM, no DB)."""

from agents.registry import AGENTS, capabilities, capabilities_text


def test_registry_excludes_manager_includes_specialists():
    names = set(AGENTS)
    assert "manager" not in names  # orchestrator is not a capability
    assert {
        "transcription",
        "requirement",
        "clarification",
        "planning",
        "task_generation",
        "risk",
        "proposal",
        "validator",
        "clickup",
        "progress_report",
    } == names


def test_capabilities_derive_display_names():
    by_name = {c.name: c for c in capabilities()}
    assert by_name["task_generation"].display_name == "Task Generation"
    assert by_name["requirement"].display_name == "Requirement"
    # metadata is pulled straight off the agent instances
    assert by_name["risk"].goal == AGENTS["risk"].goal


def test_capabilities_text_lists_every_agent_and_renders():
    text = capabilities_text(input_kind="a meeting transcript")
    assert "a meeting transcript" in text
    assert "end to end" in text
    for cap in capabilities():
        assert cap.display_name in text
        assert cap.responsibility in text


def test_capabilities_text_has_no_unrendered_jinja():
    text = capabilities_text()
    assert "{{" not in text and "{%" not in text
