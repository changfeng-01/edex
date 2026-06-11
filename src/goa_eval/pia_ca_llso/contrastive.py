from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def build_positive_negative_pairs(records: pd.DataFrame) -> pd.DataFrame:
    pairs: list[dict[str, Any]] = []
    rows = records.to_dict("records")
    for left_idx, left in enumerate(rows):
        for right in rows[left_idx + 1 :]:
            score_gap = abs(float(left.get("overall_score", 0.0)) - float(right.get("overall_score", 0.0)))
            same_level = left.get("level_label") == right.get("level_label")
            same_hard = bool(left.get("hard_constraint_passed", left.get("hard_pass", False))) == bool(
                right.get("hard_constraint_passed", right.get("hard_pass", False))
            )
            is_positive = same_level and same_hard and score_gap <= 10
            is_negative = (
                {left.get("level_label"), right.get("level_label")} == {"L1", "L4"}
                or not same_hard
                or score_gap >= 30
            )
            if is_positive or is_negative:
                pairs.append(
                    {
                        "left_id": left.get("sample_id"),
                        "right_id": right.get("sample_id"),
                        "pair_label": "positive" if is_positive else "negative",
                        "score_gap": score_gap,
                    }
                )
    return pd.DataFrame(pairs)


def summarize_pair_quality(pairs: pd.DataFrame) -> dict[str, int]:
    return {
        "pair_count": int(len(pairs)),
        "positive_count": int((pairs.get("pair_label") == "positive").sum()) if not pairs.empty else 0,
        "negative_count": int((pairs.get("pair_label") == "negative").sum()) if not pairs.empty else 0,
    }


def export_pairs_csv(path: str | Path, pairs: pd.DataFrame) -> None:
    pairs.to_csv(path, index=False)
