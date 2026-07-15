import json
import os
import subprocess

import pandas as pd
import pytest

from goa_eval.product.adapters.ngspice_sky130 import AdapterUnavailable, NgspiceSky130Adapter
from goa_eval.product.artifact_store import LocalArtifactStore
from goa_eval.product.models import SimulationJobRecord


def _job_with_netlist(store, netlist_text):
    netlist_ref = store.put_bytes("inputs/circuit.spice", netlist_text.encode("utf-8"))
    manifest_ref = store.put_bytes(
        "inputs/manifest.json",
        json.dumps({"netlist_ref": netlist_ref.uri}).encode("utf-8"),
    )
    return SimulationJobRecord(
        simulation_job_id="job_ngspice",
        project_id="project_test",
        candidate_ids=(),
        adapter_type="ngspice_sky130",
        input_manifest_ref=manifest_ref.uri,
    )


def _pdk(tmp_path):
    pdk_root = tmp_path / "sky130A"
    library = pdk_root / "libs.tech" / "ngspice" / "sky130.lib.spice"
    library.parent.mkdir(parents=True)
    library.write_text(".lib tt\n.endl tt\n", encoding="utf-8")
    return pdk_root, library


def test_missing_ngspice_or_pdk_fails_closed_without_mock_fallback(tmp_path):
    adapter = NgspiceSky130Adapter(
        ngspice_cmd="missing-ngspice",
        pdk_root=tmp_path / "missing-pdk",
        executable_resolver=lambda _command: None,
    )

    availability = adapter.availability()

    assert availability.available is False
    assert set(availability.reasons) == {"ngspice executable not found", "SKY130 PDK library not found"}
    assert adapter.evidence_metadata()["mock_used"] is False
    with pytest.raises(AdapterUnavailable, match="ngspice executable not found"):
        adapter.build_execution(_job_with_netlist(LocalArtifactStore(tmp_path / "artifacts"), ".end\n"), None, tmp_path)


def test_available_adapter_renders_only_registered_real_ngspice_command(tmp_path):
    executable = tmp_path / "ngspice.exe"
    executable.write_bytes(b"")
    pdk_root, library = _pdk(tmp_path)
    store = LocalArtifactStore(tmp_path / "artifacts")
    job = _job_with_netlist(store, '.lib "sky130.lib.spice" tt\n.tran 1n 2n\n.end\n')
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    adapter = NgspiceSky130Adapter(
        ngspice_cmd=str(executable),
        pdk_root=pdk_root,
        executable_resolver=lambda _command: str(executable),
    )

    command = adapter.build_execution(job, store, work_dir)

    rendered = (work_dir / "circuit.spice").read_text(encoding="utf-8")
    assert command.argv == (str(executable.resolve()), "-b", "-o", "ngspice.log", "circuit.spice")
    assert library.resolve().as_posix() in rendered
    assert "mock" not in " ".join(command.argv).lower()
    assert command.evidence == {
        "simulation_backend": "ngspice",
        "mock_used": False,
        "pdk_available": True,
        "ngspice_available": True,
        "reportable_as_real_ngspice": False,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }


def test_availability_is_read_only_and_never_invokes_subprocess(tmp_path, monkeypatch):
    executable = tmp_path / "ngspice"
    executable.write_bytes(b"")
    pdk_root, _ = _pdk(tmp_path)
    monkeypatch.setattr("subprocess.run", lambda *_args, **_kwargs: pytest.fail("subprocess was invoked"))
    adapter = NgspiceSky130Adapter(
        ngspice_cmd=str(executable),
        pdk_root=pdk_root,
        executable_resolver=lambda _command: str(executable),
    )

    assert adapter.availability().available is True


def test_result_import_preserves_simulation_only_boundary_and_candidate_identity(tmp_path):
    pdk_root, _ = _pdk(tmp_path)
    executable = tmp_path / "ngspice"
    executable.write_bytes(b"")
    adapter = NgspiceSky130Adapter(
        ngspice_cmd=str(executable),
        pdk_root=pdk_root,
        executable_resolver=lambda _command: str(executable),
    )
    result = tmp_path / "results.csv"
    frame = pd.DataFrame(
        [
            {
                "candidate_id": "candidate_a",
                "overall_score": 88.0,
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            }
        ]
    )
    frame.to_csv(result, index=False)

    imported = adapter.import_results(result, expected_candidate_ids=("candidate_a",))
    assert imported.to_dict(orient="records") == frame.to_dict(orient="records")

    frame.assign(engineering_validity="physical_validation").to_csv(result, index=False)
    with pytest.raises(ValueError, match="engineering_validity"):
        adapter.import_results(result, expected_candidate_ids=("candidate_a",))


@pytest.mark.skipif(
    os.getenv("CIRCUITPILOT_RUN_REAL_NGSPICE") != "1",
    reason="requires an explicitly enabled real ngspice/SKY130 environment",
)
def test_optional_real_ngspice_sky130_execution(tmp_path):
    adapter = NgspiceSky130Adapter()
    availability = adapter.availability()
    if not availability.available:
        pytest.fail(f"explicit real-ngspice run requested but unavailable: {availability.reasons}")
    store = LocalArtifactStore(tmp_path / "artifacts")
    job = _job_with_netlist(
        store,
        "\n".join(
            [
                '.lib "sky130.lib.spice" tt',
                "Vd drain 0 1.8",
                "Vg gate 0 1.8",
                "X1 drain gate 0 0 sky130_fd_pr__nfet_01v8 W=1 L=0.15",
                ".op",
                ".end",
                "",
            ]
        ),
    )
    work_dir = tmp_path / "real-ngspice"
    work_dir.mkdir()
    command = adapter.build_execution(job, store, work_dir)

    completed = subprocess.run(
        command.argv,
        cwd=command.cwd,
        shell=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert (work_dir / "ngspice.log").is_file()
