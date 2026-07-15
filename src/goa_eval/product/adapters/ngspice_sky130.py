from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

from goa_eval.product.job_runner import ExecutionCommand
from goa_eval.product.simulator_registry import AdapterAvailability
from goa_eval.sky130_transient import _write_minimal_sky130_library


class AdapterUnavailable(RuntimeError):
    pass


ExecutableResolver = Callable[[str], str | None]


class NgspiceSky130Adapter:
    """Strict real-ngspice adapter; it never selects or permits a mock fallback."""

    def __init__(
        self,
        *,
        ngspice_cmd: str = "ngspice",
        pdk_root: Path | None = None,
        executable_resolver: ExecutableResolver = shutil.which,
    ) -> None:
        self._ngspice_cmd = str(ngspice_cmd)
        self._pdk_root = Path(pdk_root).resolve() if pdk_root is not None else _environment_pdk_root()
        self._executable_resolver = executable_resolver

    def availability(self) -> AdapterAvailability:
        reasons: list[str] = []
        if self._resolved_executable() is None:
            reasons.append("ngspice executable not found")
        if self._pdk_library() is None:
            reasons.append("SKY130 PDK library not found")
        return AdapterAvailability(not reasons, tuple(reasons), ("render", "execute", "import"))

    def evidence_metadata(self) -> dict[str, Any]:
        return {
            "simulation_backend": "ngspice",
            "mock_used": False,
            "pdk_available": self._pdk_library() is not None,
            "ngspice_available": self._resolved_executable() is not None,
            # Availability alone is never execution evidence. Result validation may
            # promote this field later; command construction must remain conservative.
            "reportable_as_real_ngspice": False,
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "must_resimulate": True,
        }

    def build_execution(self, job: Any, artifact_store: Any, work_dir: Path) -> ExecutionCommand:
        availability = self.availability()
        if not availability.available:
            raise AdapterUnavailable("; ".join(availability.reasons))
        if artifact_store is None or not job.input_manifest_ref:
            raise ValueError("ngspice job requires an immutable input manifest")
        manifest_ref = artifact_store.ref_from_uri(job.input_manifest_ref)
        manifest = json.loads(artifact_store.resolve(manifest_ref).read_text(encoding="utf-8"))
        netlist_uri = manifest.get("netlist_ref")
        if not isinstance(netlist_uri, str):
            raise ValueError("ngspice input manifest requires netlist_ref")
        netlist_ref = artifact_store.ref_from_uri(netlist_uri)
        source_text = artifact_store.resolve(netlist_ref).read_text(encoding="utf-8")
        _validate_safe_netlist(source_text)
        library = self._pdk_library()
        if library is None:
            raise AdapterUnavailable("SKY130 PDK library not found")
        render_library = library
        technology_root = self._technology_root()
        if technology_root is not None and (technology_root / "libs.ref" / "sky130_fd_pr" / "spice").is_dir():
            render_library = _write_minimal_sky130_library(work_dir, technology_root)
        rendered = _render_library_path(source_text, render_library)
        if rendered == source_text and "sky130.lib.spice" in source_text.lower():
            raise ValueError("SKY130 model library reference could not be rendered")
        work_dir.mkdir(parents=True, exist_ok=True)
        netlist_path = work_dir / "circuit.spice"
        netlist_path.write_text(rendered, encoding="utf-8")
        executable = self._resolved_executable()
        if executable is None:
            raise AdapterUnavailable("ngspice executable not found")
        return ExecutionCommand(
            argv=(str(Path(executable).resolve()), "-n", "-b", "-o", "ngspice.log", netlist_path.name),
            cwd=work_dir,
            evidence=self.evidence_metadata(),
            output_files=("ngspice.log",),
        )

    def import_results(
        self,
        result_path: Path,
        *,
        expected_candidate_ids: Sequence[str] = (),
    ) -> pd.DataFrame:
        path = Path(result_path)
        if not path.is_file() or path.is_symlink():
            raise ValueError("ngspice result must be a regular CSV file")
        frame = pd.read_csv(path)
        required = {"candidate_id", "data_source", "engineering_validity", "must_resimulate"}
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise ValueError(f"ngspice result missing columns: {missing}")
        if not frame["data_source"].eq("real_simulation_csv").all():
            raise ValueError("ngspice result data_source must remain real_simulation_csv")
        if not frame["engineering_validity"].eq("simulation_only").all():
            raise ValueError("ngspice result engineering_validity must remain simulation_only")
        if not frame["must_resimulate"].map(_strict_true).all():
            raise ValueError("ngspice result must_resimulate must remain true")
        if expected_candidate_ids and set(frame["candidate_id"].astype(str)) != set(expected_candidate_ids):
            raise ValueError("ngspice result candidate IDs do not match the simulation job")
        return frame

    def _resolved_executable(self) -> str | None:
        direct = Path(self._ngspice_cmd)
        if direct.is_file():
            return str(direct.resolve())
        resolved = self._executable_resolver(self._ngspice_cmd)
        return str(Path(resolved).resolve()) if resolved else None

    def _pdk_library(self) -> Path | None:
        if self._pdk_root is None:
            return None
        candidates = (
            self._pdk_root / "libs.tech" / "ngspice" / "sky130.lib.spice",
            self._pdk_root / "libs.tech" / "combined" / "sky130.lib.spice",
            self._pdk_root / "sky130A" / "libs.tech" / "ngspice" / "sky130.lib.spice",
            self._pdk_root / "sky130A" / "libs.tech" / "combined" / "sky130.lib.spice",
            self._pdk_root / "libraries" / "sky130_fd_pr" / "latest" / "models" / "sky130.lib.spice",
        )
        return next((path.resolve() for path in candidates if path.is_file() and not path.is_symlink()), None)

    def _technology_root(self) -> Path | None:
        if self._pdk_root is None:
            return None
        candidates = (self._pdk_root, self._pdk_root / "sky130A")
        return next(
            (
                path.resolve()
                for path in candidates
                if (path / "libs.tech").is_dir() and (path / "libs.ref").is_dir() and not path.is_symlink()
            ),
            None,
        )


def _environment_pdk_root() -> Path | None:
    raw = os.environ.get("PDK_ROOT") or os.environ.get("SKYWATER_PDK_ROOT")
    if not raw:
        return None
    path = Path(raw).resolve()
    return path if path.is_dir() and not path.is_symlink() else None


def _render_library_path(netlist: str, library: Path) -> str:
    pattern = re.compile(r'(\.lib\s+)["\']?sky130\.lib\.spice["\']?(\s+\S+)', re.IGNORECASE)
    return pattern.sub(rf'\1"{library.as_posix()}"\2', netlist)


def _strict_true(value: Any) -> bool:
    return value is True or value == 1 or (isinstance(value, str) and value.strip().lower() == "true")


_ALLOWED_DIRECTIVES = {
    ".ac",
    ".dc",
    ".end",
    ".ends",
    ".global",
    ".ic",
    ".meas",
    ".measure",
    ".nodeset",
    ".op",
    ".option",
    ".param",
    ".print",
    ".save",
    ".subckt",
    ".temp",
    ".title",
    ".tran",
}
_ALLOWED_DEVICE_PREFIXES = frozenset({"b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "q", "r", "s", "v", "w", "x"})


def _validate_safe_netlist(netlist: str) -> None:
    encoded = netlist.encode("utf-8")
    if len(encoded) > 1024 * 1024:
        raise ValueError("unsafe ngspice netlist: file exceeds 1 MiB")
    lines = netlist.splitlines()
    if len(lines) > 20_000:
        raise ValueError("unsafe ngspice netlist: too many lines")
    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        lower = line.lower()
        if len(line) > 4096 or ";" in line or "\x00" in line:
            raise ValueError(f"unsafe ngspice netlist directive at line {number}")
        if re.search(r"\b(file\s*=|shell|system|source|load)\b", lower):
            raise ValueError(f"unsafe ngspice netlist host access at line {number}")
        if lower.startswith(".lib"):
            if not re.fullmatch(r"\.lib\s+[\"']?sky130\.lib\.spice[\"']?\s+(tt|ss|ff|sf|fs)", lower):
                raise ValueError(f"unsafe ngspice netlist library at line {number}")
            continue
        if line.startswith("."):
            directive = lower.split(maxsplit=1)[0]
            if directive not in _ALLOWED_DIRECTIVES:
                raise ValueError(f"unsafe ngspice netlist directive at line {number}: {directive}")
            continue
        if line.startswith("+"):
            continue
        if lower[0] not in _ALLOWED_DEVICE_PREFIXES or '"' in line or "'" in line:
            raise ValueError(f"unsafe ngspice netlist element at line {number}")
