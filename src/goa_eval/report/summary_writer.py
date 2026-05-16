from pathlib import Path

import pandas as pd

from goa_eval.evaluation.hard_checks import summarize_hard_checks
from goa_eval.io_utils import write_json


MOCK_WARNING = "Mock waveform results are workflow tests only and do not represent real circuit performance."
MOCK_WARNING_CN = "本结果基于 mock waveform，仅用于验证软件流程和指标计算逻辑，不代表真实电路性能。"


def write_metrics_csv(path: Path, run_id: str, results) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for result in results:
        rows.append(
            {
                "run_id": run_id,
                "version_name": result.version_name,
                "metric_name": result.metric_name,
                "symbol": result.symbol,
                "object_name": result.object_name,
                "value": result.value,
                "unit": result.unit,
                "passed": result.passed,
                "metric_type": result.metric_type,
                "data_source": result.data_source,
                "engineering_validity": result.engineering_validity,
                "notes": result.notes,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def write_metric_table(out_dir: Path, specs) -> None:
    rows = [
        {
            "层级": spec.level,
            "指标": spec.name,
            "符号": spec.symbol,
            "观察对象": spec.target,
            "物理意义": spec.meaning,
            "提取方法": spec.method,
            "初始判据": spec.criterion,
            "类型": spec.metric_type,
            "关联参数": spec.related_params,
        }
        for spec in specs
    ]
    pd.DataFrame(rows).to_csv(out_dir / "metrics" / "metric_table.csv", index=False, encoding="utf-8-sig")
    write_json(out_dir / "metrics" / "metric_table.json", rows)


def write_summary_json(out_dir: Path, run_id: str, data_source: str, validity: str, versions: list[str], results) -> dict:
    summary = {
        "run_id": run_id,
        "data_source": data_source,
        "engineering_validity": validity,
        "versions": versions,
        "hard_checks": summarize_hard_checks(results),
        "warning": MOCK_WARNING if data_source == "mock" else "",
    }
    write_json(out_dir / "summary.json", summary)
    return summary
