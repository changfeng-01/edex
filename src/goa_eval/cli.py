from __future__ import annotations

import argparse
from typing import Callable

from goa_eval.cli_commands import core_eval, demo_agents, pia_ca_llso, real_analysis, simulation


CommandHandler = Callable[[argparse.Namespace], int]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: CommandHandler | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="goa-eval")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for module in [core_eval, real_analysis, simulation, demo_agents, pia_ca_llso]:
        module.register(subparsers)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
