import json

import pytest

from goa_eval.product.adapters.empyrean_offline import DirectExecutionDisabled, EmpyreanOfflineAdapter
from goa_eval.product.artifact_store import LocalArtifactStore
from goa_eval.product.models import SimulationJobRecord


def test_empyrean_adapter_is_export_import_only_and_never_executes(tmp_path):
    adapter = EmpyreanOfflineAdapter()
    availability = adapter.availability()

    assert availability.available is True
    assert availability.capabilities == ("export", "import")
    assert availability.execution_enabled is False
    with pytest.raises(DirectExecutionDisabled, match="offline"):
        adapter.build_execution(None, None, tmp_path)


def test_export_preserves_batch_and_explicit_empyrean_boundary(tmp_path):
    store = LocalArtifactStore(tmp_path / "artifacts")
    batch = b"candidate_id,x\ncandidate_a,1.0\n"
    batch_ref = store.put_bytes("inputs/simulation_batch.csv", batch)
    job = SimulationJobRecord(
        simulation_job_id="job_empyrean",
        project_id="project_test",
        candidate_ids=("candidate_a",),
        adapter_type="empyrean_offline",
        batch_ref=batch_ref,
    )
    output = tmp_path / "export"

    manifest_path = EmpyreanOfflineAdapter().export_job(job, store, output)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert (output / "simulation_batch.csv").read_bytes() == batch
    assert manifest["execution_mode"] == "offline_import_only"
    assert manifest["tool_invocation"] is False
    assert manifest["candidate_ids"] == ["candidate_a"]
    assert manifest["evidence_boundary"] == {
        "data_source": "exported_empyrean_files",
        "engineering_validity": "simulation_or_tool_export_only",
        "must_resimulate": True,
        "no_local_empyrean_tool_invocation": True,
        "not_silicon_validated": True,
    }


def test_import_delegates_to_existing_offline_importer(tmp_path):
    calls = []

    def importer(**kwargs):
        calls.append(kwargs)
        return {"case_id": kwargs["case_id"], "status": "imported"}

    adapter = EmpyreanOfflineAdapter(importer=importer)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"

    result = adapter.import_results(input_dir=input_dir, output_dir=output_dir, case_id="case_1")

    assert result == {"case_id": "case_1", "status": "imported"}
    assert calls == [{"input_dir": input_dir, "output_dir": output_dir, "case_id": "case_1"}]
