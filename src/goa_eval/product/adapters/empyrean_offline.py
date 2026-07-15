from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

from goa_eval.empyrean.case_importer import run_empyrean_import
from goa_eval.empyrean.schemas import DATA_SOURCE_EXPORTED, evidence_boundary
from goa_eval.product.simulator_registry import AdapterAvailability


class DirectExecutionDisabled(PermissionError):
    pass


Importer = Callable[..., dict[str, Any]]


class EmpyreanOfflineAdapter:
    """Export/import bridge for user-operated Empyrean tools; never invokes them."""

    def __init__(self, *, importer: Importer = run_empyrean_import) -> None:
        self._importer = importer

    def availability(self) -> AdapterAvailability:
        return AdapterAvailability(True, (), ("export", "import"), execution_enabled=False)

    def evidence_metadata(self) -> dict[str, Any]:
        return evidence_boundary(DATA_SOURCE_EXPORTED)

    def build_execution(self, _job: Any, _artifact_store: Any, _work_dir: Path) -> None:
        raise DirectExecutionDisabled("Empyrean adapter is offline export/import only; direct execution is disabled")

    def export_job(self, job: Any, artifact_store: Any, output_dir: Path) -> Path:
        output = Path(output_dir).resolve()
        if output.exists() and (not output.is_dir() or output.is_symlink()):
            raise ValueError(f"Empyrean export destination is invalid: {output}")
        output.mkdir(parents=True, exist_ok=True)
        if job.batch_ref is None:
            raise ValueError("Empyrean export requires a simulation batch")
        batch_source = artifact_store.resolve(job.batch_ref)
        batch_destination = output / "simulation_batch.csv"
        if batch_destination.exists():
            if batch_destination.read_bytes() != batch_source.read_bytes():
                raise ValueError("Empyrean export cannot overwrite a different simulation batch")
        else:
            shutil.copyfile(batch_source, batch_destination)
        manifest = {
            "schema_version": "1.0",
            "simulation_job_id": job.simulation_job_id,
            "adapter_type": "empyrean_offline",
            "candidate_ids": list(job.candidate_ids),
            "batch_file": batch_destination.name,
            "batch_sha256": job.batch_ref.sha256,
            "execution_mode": "offline_import_only",
            "tool_invocation": False,
            "evidence_boundary": self.evidence_metadata(),
        }
        manifest_path = output / "empyrean_export_manifest.json"
        payload = (json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if manifest_path.exists() and manifest_path.read_bytes() != payload:
            raise ValueError("Empyrean export manifest already exists with different content")
        manifest_path.write_bytes(payload)
        return manifest_path

    def import_results(self, *, input_dir: Path, output_dir: Path, case_id: str, **kwargs: Any) -> dict[str, Any]:
        return self._importer(
            input_dir=Path(input_dir),
            output_dir=Path(output_dir),
            case_id=str(case_id),
            **kwargs,
        )
