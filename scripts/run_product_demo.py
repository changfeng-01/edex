from __future__ import annotations

import argparse
from pathlib import Path

from goa_eval.product_demo.workflow import run_product_demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a CircuitPilot product demo package.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="outputs/product_demo")
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args(argv)
    case_dir = run_product_demo(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        case_id=args.case_id,
    )
    print(f"Product demo package written to {case_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
