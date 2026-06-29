from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def load_figure_script():
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_pia_paper_figures.py"
    spec = importlib.util.spec_from_file_location("build_pia_paper_figures", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pia_paper_figure_package_generation(tmp_path: Path) -> None:
    module = load_figure_script()

    generated = module.build_figure_package(tmp_path)

    pngs = sorted((tmp_path / "figures").glob("*.png"))
    pdfs = sorted((tmp_path / "figures").glob("*.pdf"))
    assert len(pngs) == 7
    assert len(pdfs) == 7
    assert all(path.stat().st_size > 1_000 for path in pngs)

    prompts = json.loads((tmp_path / "prompts" / "image2_prompts.json").read_text(encoding="utf-8"))
    assert len(prompts) == 4
    assert {item["model"] for item in prompts} == {"gpt-image-2"}

    manifest = (tmp_path / "figure_manifest.md").read_text(encoding="utf-8")
    assert "data_source = real_simulation_csv" in manifest
    assert "engineering_validity = simulation_only" in manifest
    assert "must_resimulate = true" in manifest
    assert "Fig. 7" in manifest

    captions = (tmp_path / "figure_captions_zh.md").read_text(encoding="utf-8")
    assert "图 1" in captions
    assert "CAPM-Distance" in captions

    summary = json.loads((tmp_path / "figure_generation_summary.json").read_text(encoding="utf-8"))
    assert summary["boundary"]["data_source"] == "real_simulation_csv"
    assert summary["boundary"]["engineering_validity"] == "simulation_only"
    assert summary["boundary"]["must_resimulate"] is True
    assert len(generated) >= 19
