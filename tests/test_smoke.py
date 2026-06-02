"""Smoke tests — verifies the package imports and the graph wires."""

import pytest


def test_package_imports() -> None:
    import agencyos

    assert agencyos.__version__


def test_state_schema_constructs() -> None:
    from agencyos.graph.state import AgencyState

    s = AgencyState(user_id="tester")
    assert s.conversation_id
    assert s.audit_log == []
    assert s.attempt_count == {}


def test_calculator_safe_eval() -> None:
    from agencyos.tools.calculator import safe_eval

    assert safe_eval("2 + 3 * 4") == 14.0
    with pytest.raises(ValueError):
        safe_eval("__import__('os').system('echo hi')")


def test_graph_builder_wires_all_agents() -> None:
    pytest.importorskip("langgraph")
    pytest.importorskip("langchain_groq")
    from agencyos.graph.builder import build_graph

    g = build_graph()
    expected = {
        "manager",
        "transcription",
        "requirement",
        "clarification",
        "planning",
        "task_generation",
        "risk",
        "proposal",
        "validator",
        "executor",
    }
    assert expected.issubset(set(g.nodes.keys()))
