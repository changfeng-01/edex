"""Transistor-level netlist adapter for PIA next-run simulation batches."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from goa_eval.pia_ca_llso.simulation_contract import import_simulation_results


TRANSISTOR_LEVEL_PARAMETER_COLUMNS = [
    "M_pullup_W",
    "M_pullup_L",
    "M_pulldown_W",
    "M_pulldown_L",
    "M_reset_W",
    "M_reset_L",
    "M_bootstrap_W",
    "M_bootstrap_L",
    "C_load",
    "C_boot",
    "VDD",
    "VSS",
    "VGH",
    "VGL",
    "Vth_shift",
    "CLK_rise_time",
    "CLK_fall_time",
]


def render_transistor_level_netlist(template_text: str, row: Mapping[str, Any]) -> str:
    """Render a SPICE template using {name} or {{name}} placeholders."""
    rendered = template_text
    for key, value in row.items():
        rendered = rendered.replace("{{" + str(key) + "}}", _spice_value(value))
        rendered = rendered.replace("{" + str(key) + "}", _spice_value(value))
    return rendered


def build_transistor_level_netlists(
    simulation_batch: pd.DataFrame,
    *,
    template_path: str | Path,
    output_dir: str | Path,
    parameter_columns: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Write one rendered netlist per candidate and a manifest for audit."""
    if "candidate_id" not in simulation_batch.columns:
        raise ValueError("simulation_batch is missing candidate_id")

    template = Path(template_path).read_text(encoding="utf-8")
    out_dir = Path(output_dir)
    netlist_dir = out_dir / "netlists"
    netlist_dir.mkdir(parents=True, exist_ok=True)
    parameter_columns = list(parameter_columns or TRANSISTOR_LEVEL_PARAMETER_COLUMNS)

    records: list[dict[str, Any]] = []
    for index, row in simulation_batch.reset_index(drop=True).iterrows():
        candidate_id = str(row["candidate_id"])
        netlist_name = f"{index + 1:03d}_{_safe_stem(candidate_id)}.spice"
        netlist_path = netlist_dir / netlist_name
        netlist_path.write_text(render_transistor_level_netlist(template, row.to_dict()), encoding="utf-8")
        records.append(
            {
                "candidate_id": candidate_id,
                "netlist_path": str(netlist_path),
                "parameter_columns_json": json.dumps(parameter_columns, ensure_ascii=False),
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
                "evidence_state": "pending_simulation",
            }
        )

    manifest = {
        "adapter": "transistor_level_netlist",
        "template_path": str(template_path),
        "netlist_count": len(records),
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
        "claim_boundary": "rendered netlists are next-run simulation inputs, not validated results",
    }
    (out_dir / "transistor_level_netlist_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return pd.DataFrame(records), manifest


def import_transistor_level_results(
    result_csv: str | Path,
    simulation_batch: pd.DataFrame,
    config: Mapping[str, Any],
    generation: int,
) -> pd.DataFrame:
    """Import externally evaluated transistor-level simulation rows."""
    return import_simulation_results(
        result_csv=result_csv,
        simulation_batch=simulation_batch,
        config=config,
        generation=generation,
    )


def _safe_stem(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "candidate"


def _spice_value(value: Any) -> str:
    if pd.isna(value):
        return "0"
    return str(value)
