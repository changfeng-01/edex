from __future__ import annotations

import json
from pathlib import Path

from goa_eval.multi_agent.schemas import HandoffRecord


def create_handoff_record(from_agent: str, to_agent: str, reason: str, state_keys_passed: list[str]) -> HandoffRecord:
    return HandoffRecord(
        from_agent=from_agent,
        to_agent=to_agent,
        reason=reason,
        state_keys_passed=state_keys_passed,
    )


def append_handoff(state: dict, from_agent: str, to_agent: str, reason: str, state_keys_passed: list[str]) -> dict:
    record = create_handoff_record(from_agent, to_agent, reason, state_keys_passed)
    state.setdefault("handoff_records", []).append(record.to_dict())
    return state


def write_handoff_trace(path: Path, records: list[HandoffRecord | dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for record in records:
        payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
        lines.append(json.dumps(payload, ensure_ascii=False))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
