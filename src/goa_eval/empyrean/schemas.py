from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from goa_eval.schemas import RESULT_VERSION, SCHEMA_VERSION


STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_WARNING = "warning"
STATUS_NOT_PROVIDED = "not_provided"
STATUS_NOT_EVALUABLE = "not_evaluable"
STATUS_UNKNOWN = "unknown"

VALID_STATUSES = {
    STATUS_PASSED,
    STATUS_FAILED,
    STATUS_WARNING,
    STATUS_NOT_PROVIDED,
    STATUS_NOT_EVALUABLE,
    STATUS_UNKNOWN,
}

TOOLCHAIN = "empyrean_fpd_offline"
EXECUTION_MODE = "offline_import_only"
DATA_SOURCE_EXPORTED = "exported_empyrean_files"
DATA_SOURCE_USER_PROVIDED = "user_provided_exported_files"
ENGINEERING_VALIDITY = "simulation_or_tool_export_only"


@dataclass(frozen=True)
class EmpyreanCaseInput:
    input_dir: Path
    output_dir: Path
    case_id: str


@dataclass(frozen=True)
class VerificationReportStatus:
    status: str
    error_count: int | None = None
    warning_count: int | None = None
    raw_report_path: str | None = None
    error_types: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PhysicalVerificationSummary:
    schema_version: str
    result_version: str
    drc: VerificationReportStatus
    lvs: VerificationReportStatus
    erc: VerificationReportStatus
    pve: VerificationReportStatus | None = None


@dataclass(frozen=True)
class ParasiticSummary:
    schema_version: str
    result_version: str
    status: str
    has_rc_data: bool
    resistance_unit: str | None = None
    capacitance_unit: str | None = None
    total_resistance: float | None = None
    total_capacitance: float | None = None
    max_resistance: float | None = None
    max_capacitance: float | None = None
    net_count: int = 0
    raw_file_path: str | None = None
    grouped_by_net: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""


@dataclass(frozen=True)
class ModelArtifactSummary:
    schema_version: str
    result_version: str
    status: str
    artifacts: list[dict[str, Any]]


@dataclass(frozen=True)
class WaveformConversionResult:
    schema_version: str
    result_version: str
    status: str
    input_path: str
    normalized_waveform_path: str
    column_map_path: str
    time_column: str
    signal_count: int


def base_versions() -> dict[str, str]:
    return {"schema_version": SCHEMA_VERSION, "result_version": RESULT_VERSION}


def evidence_boundary(data_source: str = DATA_SOURCE_EXPORTED) -> dict[str, Any]:
    return {
        "data_source": data_source,
        "engineering_validity": ENGINEERING_VALIDITY,
        "must_resimulate": True,
        "no_local_empyrean_tool_invocation": True,
        "not_silicon_validated": True,
    }
