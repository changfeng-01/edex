from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


def main() -> int:
    src_dir = Path(__file__).resolve().parents[1] / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    pythonpath = os.environ.get("PYTHONPATH", "")
    if str(src_dir) not in pythonpath.split(os.pathsep):
        os.environ["PYTHONPATH"] = os.pathsep.join(part for part in [str(src_dir), pythonpath] if part)
    uvicorn.run("goa_eval.web_api.app:app", host="127.0.0.1", port=8000, reload=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
