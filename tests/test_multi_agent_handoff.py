import json

from goa_eval.multi_agent.handoff import create_handoff_record, write_handoff_trace


def test_handoff_record_contains_required_fields(tmp_path):
    record = create_handoff_record("RouterAgent", "SKY130Agent", "profile match", ["profile", "inputs"])

    assert record.from_agent == "RouterAgent"
    assert record.to_agent == "SKY130Agent"
    assert record.reason == "profile match"
    assert record.state_keys_passed == ["profile", "inputs"]
    assert record.timestamp

    path = tmp_path / "handoff.jsonl"
    write_handoff_trace(path, [record])
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["handoff_status"] == "success"
