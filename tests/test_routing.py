"""Pure unit tests for the dependency/routing model (no LLM, no DB)."""

from agencyos.graph.routing import (
    DEPENDENCIES,
    FULL_PIPELINE,
    missing_prerequisites,
    topological_order,
)
from agencyos.graph.state import (
    AgencyState,
    Plan,
    Requirements,
    Task,
)


def _state(**kwargs) -> AgencyState:
    return AgencyState(user_id="tester", **kwargs)


# ─── missing_prerequisites ────────────────────────────────────────────


def test_proposal_from_scratch_needs_requirement_and_planning():
    s = _state()
    missing = missing_prerequisites(s, "proposal")
    # requirement must come before planning
    assert missing == ["requirement", "planning"]


def test_prereqs_skip_already_satisfied_steps():
    s = _state(requirements=Requirements(client_goals=["grow"]))
    # requirement is done, so only planning remains for a proposal
    assert missing_prerequisites(s, "proposal") == ["planning"]


def test_risk_pulls_planning_and_tasks_transitively():
    s = _state()
    missing = missing_prerequisites(s, "risk")
    assert missing == ["requirement", "planning", "task_generation"]


def test_no_prereqs_when_everything_present():
    s = _state(
        requirements=Requirements(),
        plan=Plan(summary="x"),
        tasks=[Task(id="1", title="t", description="d", priority=1, milestone="m")],
    )
    assert missing_prerequisites(s, "risk") == []


def test_requirement_has_no_agent_prereqs():
    assert missing_prerequisites(_state(), "requirement") == []


# ─── topological_order ────────────────────────────────────────────────


def test_topo_orders_requested_set_only():
    # request out of order; should be reordered, no extra agents pulled in
    ordered = topological_order(["proposal", "requirement", "planning"])
    assert ordered.index("requirement") < ordered.index("planning") < ordered.index("proposal")
    assert set(ordered) == {"requirement", "planning", "proposal"}


def test_topo_drops_unknown_agents():
    assert topological_order(["requirement", "bogus"]) == ["requirement"]


def test_topo_does_not_add_prerequisites():
    # asking only for proposal yields only proposal (prereq-pulling is a separate concern)
    assert topological_order(["proposal"]) == ["proposal"]


def test_full_pipeline_is_topologically_valid():
    ordered = topological_order(FULL_PIPELINE)
    for agent, deps in DEPENDENCIES.items():
        if agent not in ordered:
            continue
        for dep in deps:
            if dep in ordered:
                assert ordered.index(dep) < ordered.index(agent)
