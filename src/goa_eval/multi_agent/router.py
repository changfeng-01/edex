from __future__ import annotations


def route_task(task_type: str, profile: str, inputs: dict) -> dict[str, str]:
    task_text = (task_type or "").lower()
    profile_text = (profile or "").lower()
    input_keys = set(inputs or {})

    if profile_text.startswith("goa") or "goa" in task_text:
        return {
            "selected_domain_agent": "GOAAgent",
            "handoff_to": "GOAAgent",
            "reason": "profile or task_type indicates GOA / 8T1C evaluation",
        }
    if profile_text.startswith("sky130") or "sky130" in task_text:
        return {
            "selected_domain_agent": "SKY130Agent",
            "handoff_to": "SKY130Agent",
            "reason": "profile or task_type indicates SKY130 evaluation",
        }
    if input_keys & {"waveform", "real_metrics", "score_summary", "leaderboard"}:
        return {
            "selected_domain_agent": "GenericWaveformAgent",
            "handoff_to": "GenericWaveformAgent",
            "reason": "waveform-derived evaluation files are available but profile is generic",
        }
    if "netlist" in input_keys:
        return {
            "selected_domain_agent": "NetlistAgent",
            "handoff_to": "NetlistAgent",
            "reason": "netlist is available and waveform evaluation files are absent",
        }
    return {
        "selected_domain_agent": "unsupported",
        "handoff_to": "CriticAgent",
        "reason": "insufficient inputs for domain routing",
    }
