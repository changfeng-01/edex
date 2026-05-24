from pathlib import Path


def test_real_deepseek_runner_reads_local_env_without_mock_response():
    script = Path("scripts/run_real_deepseek.ps1")
    text = script.read_text(encoding="utf-8")

    assert "$RepoRoot" in text
    assert ".env" in text
    assert "DEEPSEEK_API_KEY" in text
    assert "--mock-response" not in text
    assert "llm_parameter_analysis_real.md" in text
    assert "llm_parameter_analysis_real.json" in text
    assert "sk-" not in text


def test_env_example_documents_deepseek_key_placeholder_only():
    env_example = Path(".env.example")
    text = env_example.read_text(encoding="utf-8")

    assert "DEEPSEEK_API_KEY=" in text
    assert "your_deepseek_api_key_here" in text
    assert "sk-" not in text
