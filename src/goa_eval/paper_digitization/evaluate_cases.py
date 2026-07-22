from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from goa_eval.io_utils import write_json
from goa_eval.paper_digitization.schemas import (
    ENGINEERING_VALIDITY,
    PAPER_CLAIM_BOUNDARY,
    PAPER_DIGITIZED_DATA_SOURCE,
    SOURCE_TYPE_PAPER_DIGITIZED,
    SPEC_BY_PAPER_ID,
)
from goa_eval.real_waveform_eval import run_real_waveform_evaluation


def evaluate_paper_cases(*, index_path: Path, output_root: Path) -> list[dict[str, Any]]:
    index = pd.read_csv(index_path) if index_path.exists() else pd.DataFrame()
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for _, row in index.iterrows():
        case_id = str(row.get("case_id") or "").strip()
        if not case_id:
            continue
        run_dir = output_root / case_id
        try:
            waveform_path = Path(str(row.get("waveform_path")))
            internal_raw = row.get("internal_waveform_path")
            internal_path = Path(str(internal_raw)) if pd.notna(internal_raw) and str(internal_raw).strip() else None
            paper_id = str(row.get("paper_id") or "")
            spec_path = SPEC_BY_PAPER_ID.get(paper_id, Path("config/spec.yaml"))
            evidence_metadata = {
                "data_source": PAPER_DIGITIZED_DATA_SOURCE,
                "source_type": SOURCE_TYPE_PAPER_DIGITIZED,
                "weak_label": True,
                "engineering_validity": ENGINEERING_VALIDITY,
                "claim_boundary": PAPER_CLAIM_BOUNDARY,
                "simulation_backend": "paper_digitized_csv",
                "evidence_level": "level_1_external_csv",
                "mock_used": False,
                "optimizer_claim_level": "candidate_generated",
            }
            summary = run_real_waveform_evaluation(
                waveform_path=waveform_path,
                internal_waveform_path=internal_path,
                output_dir=run_dir,
                spec_path=spec_path,
                stage_count=_optional_int(row.get("stage_count")),
                output_node_pattern=_optional_str(row.get("output_node_pattern")),
                topology=_optional_str(row.get("topology_id")),
                evidence_metadata=evidence_metadata,
            )
            rows.append(
                {
                    "case_id": case_id,
                    "paper_id": paper_id,
                    "status": "evaluated",
                    "run_dir": str(run_dir),
                    "overall_status": summary.get("Overall_status"),
                    "stage_count": summary.get("stage_count"),
                    "data_source": PAPER_DIGITIZED_DATA_SOURCE,
                    "engineering_validity": ENGINEERING_VALIDITY,
                    "message": "",
                }
            )
        except Exception as exc:
            run_dir.mkdir(parents=True, exist_ok=True)
            status = {
                "case_id": case_id,
                "paper_id": str(row.get("paper_id") or ""),
                "status": "failed",
                "run_dir": str(run_dir),
                "message": f"{type(exc).__name__}: {exc}",
                "data_source": PAPER_DIGITIZED_DATA_SOURCE,
                "engineering_validity": ENGINEERING_VALIDITY,
            }
            write_json(run_dir / "paper_eval_status.json", status)
            rows.append(status)
    summary = {
        "case_count": len(rows),
        "evaluated_count": sum(1 for row in rows if row.get("status") == "evaluated"),
        "failed_count": sum(1 for row in rows if row.get("status") == "failed"),
        "cases": rows,
        "data_source": PAPER_DIGITIZED_DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
    }
    write_json(index_path.parent / "paper_database_summary.json", summary)
    pd.DataFrame(rows).to_csv(output_root / "paper_eval_runs.csv", index=False, encoding="utf-8-sig")
    return rows


def _optional_int(value: Any) -> int | None:
    if value in (None, "") or pd.isna(value):
        return None
    return int(float(value))


def _optional_str(value: Any) -> str | None:
    if value in (None, "") or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate all paper digitized waveform cases.")
    parser.add_argument("--index", dest="index_path", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows = evaluate_paper_cases(index_path=args.index_path, output_root=args.output_root)
    print(f"evaluated={sum(1 for row in rows if row.get('status') == 'evaluated')} failed={sum(1 for row in rows if row.get('status') == 'failed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
