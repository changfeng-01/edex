from __future__ import annotations


def run_empyrean_toolchain(*args, **kwargs):
    raise RuntimeError(
        "Empyrean tool execution is not supported in this environment. "
        "Use empyrean-import with exported files instead."
    )
