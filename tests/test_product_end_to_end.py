import json
import subprocess
import sys
from pathlib import Path


BOUNDARY = {
    "data_source": "real_simulation_csv",
    "engineering_validity": "simulation_only",
    "must_resimulate": True,
}


def test_product_demo_builder_completes_evaluated_closed_loop(tmp_path):
    output_dir = tmp_path / "product_demo_v1"
    database_path = tmp_path / "product_demo_v1.db"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_product_demo.py",
            "--output-dir",
            str(output_dir),
            "--database-url",
            f"sqlite:///{database_path.as_posix()}",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((output_dir / "product_demo_manifest.json").read_text(encoding="utf-8"))
    evidence = json.loads((output_dir / "evidence_package.json").read_text(encoding="utf-8"))
    report = (output_dir / "product_report.md").read_text(encoding="utf-8")

    assert manifest["schema_version"] == "circuitpilot.product-demo.v1"
    assert manifest["boundary"] == BOUNDARY
    assert manifest["workflow"]["workspace_created"] is True
    assert manifest["workflow"]["baseline_analysis_status"] == "completed"
    assert manifest["workflow"]["issue_count"] > 0
    assert manifest["workflow"]["candidate_must_resimulate"] is True
    assert manifest["workflow"]["confirmation_before_import_rejected"] is True
    assert manifest["workflow"]["confirmation_before_evaluation_rejected"] is True
    assert manifest["workflow"]["manual_job_status"] == "completed"
    assert manifest["workflow"]["result_analysis_status"] == "completed"
    assert manifest["workflow"]["comparison_verdict"] == "neutral"
    assert manifest["workflow"]["candidate_final_status"] == "evaluated"
    assert manifest["workflow"]["confirmation_after_evaluation_rejected"] is True
    assert manifest["workflow"]["confirmed_improvement"] is False
    assert len(manifest["design_version_ids"]) == 2
    assert evidence["boundary"] == BOUNDARY
    assert evidence["records"]
    for line in (
        "data_source = real_simulation_csv",
        "engineering_validity = simulation_only",
        "must_resimulate = true",
    ):
        assert line in report
    assert database_path.is_file()


def test_phase4_docs_cover_api_roles_boundaries_and_recovery():
    quickstart = Path("docs/product_quickstart.md").read_text(encoding="utf-8")
    architecture = Path("docs/product_architecture.md").read_text(encoding="utf-8")
    migration = Path("docs/product_migration.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    for text in (quickstart, architecture, migration):
        assert "data_source = real_simulation_csv" in text
        assert "engineering_validity = simulation_only" in text
        assert "must_resimulate = true" in text
    assert "src/goa_eval/web/" in architecture
    assert "src/goa_eval/web_api/" in architecture
    assert "src/goa_eval/product_api/" in architecture
    assert "failure recovery" in migration.lower()
    assert "docs/product_quickstart.md" in readme


def test_windows_ci_includes_phase4_product_profile_gate():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert 'pia or web or waveform or product or circuit_profile or generalized' in workflow


def test_vercel_build_targets_the_vite_frontend():
    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))

    assert config["framework"] == "vite"
    assert config["installCommand"] == "npm ci --prefix frontend"
    assert config["buildCommand"] == "npm run build --prefix frontend"
    assert config["outputDirectory"] == "frontend/dist"
    assert {"source": "/(.*)", "destination": "/index.html"} in config["rewrites"]
    quickstart = Path("docs/product_quickstart.md").read_text(encoding="utf-8")
    assert "VITE_PRODUCT_API_BASE_URL" in quickstart
