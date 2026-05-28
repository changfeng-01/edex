from __future__ import annotations

from pathlib import Path

from goa_eval.multi_agent.agents._utils import add_message, store_tool_result
from goa_eval.multi_agent.evidence_index import build_evidence_index, paths_from_evidence_index, write_evidence_index
from goa_eval.multi_agent.trace import record_step
from goa_eval.multi_agent.tools import inspect_artifact_bundle


def run_supervisor_agent(state: dict) -> dict:
    state["active_agent"] = "SupervisorAgent"
    state["next_agent"] = "RouterAgent"
    output_dir = Path(state["output_dir"])
    evidence_index = build_evidence_index(state.get("inputs", {}), output_dir)
    evidence_path = write_evidence_index(evidence_index, output_dir)
    state["evidence_index"] = evidence_index
    state.setdefault("generated_files", {})["evidence_index"] = str(evidence_path)
    discovered_paths = paths_from_evidence_index(evidence_index)
    state.setdefault("inputs", {}).update(discovered_paths)
    bundle_result = inspect_artifact_bundle(state.get("inputs", {}))
    state["artifact_bundle_summary"] = bundle_result.data
    store_tool_result(state, "SupervisorAgent", bundle_result)
    add_message(
        state,
        "SupervisorAgent",
        {
            "summary": "Initialized local multi-agent run.",
            "artifact_completeness": {
                "discovered_count": sum(1 for item in (evidence_index.get("artifacts") or {}).values() if item.get("exists")),
                "artifact_discovery_score": evidence_index.get("artifact_discovery_score"),
                "missing_optional_artifacts": evidence_index.get("missing_optional_artifacts", []),
            },
            "data_source": state.get("data_source"),
            "engineering_validity": state.get("engineering_validity"),
        },
    )
    plan_path = output_dir / "multi_agent_plan.json"
    state.setdefault("generated_files", {})["multi_agent_plan"] = str(plan_path)
    record_step(
        state,
        agent_name="SupervisorAgent",
        node_name="supervisor",
        step_id="supervisor-1",
        status="pass",
        reason="shared state and evidence index initialized",
        output_summary={"next_agent": "RouterAgent", "evidence_index": str(evidence_path)},
    )
    return state
