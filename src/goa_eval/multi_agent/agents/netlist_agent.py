from __future__ import annotations

from pathlib import Path

from goa_eval.multi_agent.agents._utils import add_message, store_tool_result
from goa_eval.multi_agent.handoff import append_handoff
from goa_eval.parsers.netlist_parser import parse_netlist
from goa_eval.multi_agent.tools import inspect_netlist_integrity


def run_netlist_agent(state: dict) -> dict:
    state["active_agent"] = "NetlistAgent"
    netlist = state.get("inputs", {}).get("netlist")
    summary = {
        "not_implemented_yet": True,
        "supported_features": ["basic netlist parse when existing parser accepts the file"],
        "limitations": ["no waveform metrics available", "no ngspice closed loop is implemented in this multi-agent MVP"],
        "next_steps": ["provide waveform, real_metrics, score_summary, or leaderboard for deterministic evaluation"],
    }
    if netlist and Path(str(netlist)).exists():
        parsed = parse_netlist(Path(str(netlist)))
        integrity = inspect_netlist_integrity(netlist)
        store_tool_result(state, "NetlistAgent", integrity)
        summary.update(
            {
                "not_implemented_yet": False,
                "device_count": len(parsed.devices),
                "subckt_count": len(parsed.subckts),
                "warnings": parsed.warnings,
                "integrity_issues": integrity.warnings + integrity.failures,
            }
        )
    state["netlist_summary"] = summary
    add_message(state, "NetlistAgent", {"netlist_summary": summary})
    append_handoff(state, "NetlistAgent", "CriticAgent", "netlist-only task has no waveform evaluation artifacts", ["netlist_summary"])
    return state
