import json
import subprocess
import sys
from pathlib import Path

import yaml

from goa_eval.ai_profile_assistant import build_profile_assistant_payload, run_ai_profile_assistant


def test_build_profile_assistant_payload_keeps_simulation_boundary(tmp_path):
    description = tmp_path / "description.md"
    description.write_text("Two-stage OTA, prioritize gain and power.", encoding="utf-8")

    payload = build_profile_assistant_payload(
        description_path=description,
        profile_file=Path("config/circuit_profiles.yaml"),
        params_file=Path("config/parameter_semantics.yaml"),
        metrics_file=None,
        score_file=None,
    )

    assert payload["boundary"] == {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }
    assert "ota_general" in payload["existing_profiles"]["profiles"]
    assert "m1_width" in payload["parameter_semantics"]["parameters"]


def test_ai_profile_assistant_mock_writes_draft_files(tmp_path):
    description = tmp_path / "description.md"
    description.write_text("Draft an OTA profile.", encoding="utf-8")
    output_dir = tmp_path / "assistant"
    mock_response = json.dumps(
        {
            "analysis": "Keep the result simulation_only and validate before use.",
            "profile_draft": {
                "schema_version": "1.0",
                "profiles": {
                    "draft_ota": {
                        "aliases": ["draft_ota"],
                        "boundary": {"data_source": "real_simulation_csv", "engineering_validity": "simulation_only"},
                        "metrics": {},
                        "candidate_rules": {},
                    }
                },
            },
            "parameter_semantics_draft": {
                "schema_version": "1.0",
                "parameters": {},
                "parameter_groups": {},
            },
        }
    )

    result = run_ai_profile_assistant(
        description_path=description,
        output_dir=output_dir,
        profile_file=Path("config/circuit_profiles.yaml"),
        params_file=Path("config/parameter_semantics.yaml"),
        mock_response=mock_response,
    )

    profile = yaml.safe_load((output_dir / "profile_draft.yaml").read_text(encoding="utf-8"))
    semantics = yaml.safe_load((output_dir / "parameter_semantics_draft.yaml").read_text(encoding="utf-8"))
    machine = json.loads((output_dir / "ai_profile_assistant.json").read_text(encoding="utf-8"))
    markdown = (output_dir / "ai_profile_assistant.md").read_text(encoding="utf-8")

    assert result["metadata"]["mock_response"] is True
    assert profile["profiles"]["draft_ota"]["boundary"]["engineering_validity"] == "simulation_only"
    assert semantics["parameters"] == {}
    assert machine["boundary"]["engineering_validity"] == "simulation_only"
    assert "simulation_only" in markdown


def test_ai_profile_assistant_cli_output_validates(tmp_path):
    description = tmp_path / "description.md"
    description.write_text("Draft a simple profile.", encoding="utf-8")
    output_dir = tmp_path / "assistant"
    mock_response = json.dumps(
        {
            "analysis": "Draft only.",
            "profile_draft": {
                "schema_version": "1.0",
                "profiles": {
                    "draft_default": {
                        "aliases": [],
                        "boundary": {"data_source": "real_simulation_csv", "engineering_validity": "simulation_only"},
                        "metrics": {},
                        "candidate_rules": {},
                    }
                },
            },
            "parameter_semantics_draft": {"schema_version": "1.0", "parameters": {}, "parameter_groups": {}},
        }
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "ai-profile-assistant",
            "--description",
            str(description),
            "--profile-file",
            "config/circuit_profiles.yaml",
            "--params",
            "config/parameter_semantics.yaml",
            "--mock-response",
            mock_response,
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    validate = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "validate-config",
            "--profile-file",
            str(output_dir / "profile_draft.yaml"),
            "--params",
            str(output_dir / "parameter_semantics_draft.yaml"),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stderr
