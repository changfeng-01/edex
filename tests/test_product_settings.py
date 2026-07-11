from pathlib import Path

from goa_eval.product.settings import ProductSettings


def test_product_settings_use_safe_local_defaults(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    settings = ProductSettings.from_env()

    assert settings.database_url == "sqlite:///outputs/product/circuitpilot.db"
    assert settings.artifact_root == Path("outputs/product/artifacts")
    assert settings.job_execution_enabled is False
