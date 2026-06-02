"""ExecutorAgent — package approved artifacts to disk and finalize the run."""

from datetime import datetime

from agencyos.agents.base import BaseAgent
from agencyos.graph.state import AgencyState, RunSummary


class ExecutorAgent(BaseAgent):
    name = "executor"
    role = "Packager"
    responsibility = "Write approved artifacts to disk, build deliverable bundle, log metrics."
    goal = "A single outputs/<conversation_id>/ folder with every artifact and run_summary.json."

    async def reason(self, state: AgencyState) -> str:
        return f"Packaging artifacts for conversation {state.conversation_id} to outputs/."

    async def act(self, state: AgencyState, reasoning: str) -> dict:
        # TODO: tools.file_io.write_proposal / write_tasks / zip_bundle
        raise NotImplementedError("ExecutorAgent.act not yet implemented")

    def merge(self, state: AgencyState, output: dict) -> AgencyState:
        state.run_summary = RunSummary(
            started_at=state.run_summary.started_at if state.run_summary else datetime.utcnow(),
            ended_at=datetime.utcnow(),
            output_path=output.get("output_path"),
        )
        return state


run = ExecutorAgent()
