"""PIA-CA-LLSO experimental optimizer module.

This package emits next-run simulation suggestions only. Benchmark claims must
come from externally evaluated simulation records, not model self-scores.
"""

DATA_SOURCE = "real_simulation_csv"
ENGINEERING_VALIDITY = "simulation_only"

__all__ = ["DATA_SOURCE", "ENGINEERING_VALIDITY"]
