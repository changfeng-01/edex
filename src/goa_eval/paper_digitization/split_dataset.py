from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any

import pandas as pd

from goa_eval.io_utils import write_json


def split_dataset(
    *,
    input_path: Path,
    output_path: Path,
    strategy: str = "group_by_paper_topology",
    seed: int = 42,
) -> pd.DataFrame:
    frame = pd.read_csv(input_path)
    rng = random.Random(seed)
    if frame.empty:
        output = pd.DataFrame(columns=["sample_id", "case_id", "split_group", "train_val_test", "warning"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output.to_csv(output_path, index=False, encoding="utf-8-sig")
        return output
    split_group = _split_group(frame, strategy)
    frame = frame.copy()
    frame["split_group"] = split_group
    unique_groups = sorted(split_group.dropna().astype(str).unique())
    rng.shuffle(unique_groups)
    warnings: list[str] = []
    group_split: dict[str, str] = {}
    if len(unique_groups) < 3 and strategy != "random":
        warnings.append("small_dataset_group_split_warning")
        for group in unique_groups:
            group_split[group] = "train"
    else:
        train_cut = max(1, int(len(unique_groups) * 0.70))
        val_cut = max(train_cut + 1, int(len(unique_groups) * 0.85)) if len(unique_groups) >= 3 else train_cut
        for index, group in enumerate(unique_groups):
            if index < train_cut:
                group_split[group] = "train"
            elif index < val_cut:
                group_split[group] = "val"
            else:
                group_split[group] = "test"
    if strategy == "random":
        assignments = []
        for index in range(len(frame)):
            ratio = index / max(len(frame), 1)
            assignments.append("train" if ratio < 0.70 else "val" if ratio < 0.85 else "test")
        rng.shuffle(assignments)
        frame["train_val_test"] = assignments
    else:
        frame["train_val_test"] = frame["split_group"].astype(str).map(group_split).fillna("train")
    output = frame[["sample_id", "case_id", "figure_id", "paper_id", "topology_id", "split_group", "train_val_test"]].copy()
    output["warning"] = ";".join(warnings)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False, encoding="utf-8-sig")
    write_json(output_path.with_suffix(".summary.json"), {"strategy": strategy, "seed": seed, "warnings": warnings, "group_count": len(unique_groups)})
    return output


def _split_group(frame: pd.DataFrame, strategy: str) -> pd.Series:
    if strategy == "random":
        return frame.get("sample_id", pd.Series(range(len(frame)))).astype(str)
    if strategy == "group_by_paper":
        return frame.get("paper_id", pd.Series(["unknown"] * len(frame))).astype(str)
    if strategy == "group_by_topology":
        return frame.get("topology_id", pd.Series(["unknown"] * len(frame))).astype(str)
    if strategy == "leave_one_paper_out":
        return frame.get("paper_id", pd.Series(["unknown"] * len(frame))).astype(str)
    if strategy == "leave_one_topology_out":
        return frame.get("topology_id", pd.Series(["unknown"] * len(frame))).astype(str)
    if strategy == "group_by_paper_topology":
        paper = frame.get("paper_id", pd.Series(["unknown"] * len(frame))).astype(str)
        topology = frame.get("topology_id", pd.Series(["unknown"] * len(frame))).astype(str)
        return paper + "_" + topology
    raise ValueError(f"Unsupported split strategy: {strategy}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create train/val/test split for GOA training samples.")
    parser.add_argument("--input", dest="input_path", type=Path, required=True)
    parser.add_argument("--output", dest="output_path", type=Path, required=True)
    parser.add_argument("--strategy", default="group_by_paper_topology")
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = split_dataset(input_path=args.input_path, output_path=args.output_path, strategy=args.strategy, seed=args.seed)
    print(args.output_path)
    print(f"samples={len(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
