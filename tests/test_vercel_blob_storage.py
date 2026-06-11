from pathlib import Path

from goa_eval.product_demo.workflow import run_product_demo
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.web.vercel_blob import BlobUpload, persist_case_dir_to_blob


class FakeBlobStore:
    enabled = True
    prefix = "web_cases"

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.json_payloads: dict[str, dict] = {}

    def case_path(self, case_id: str, relative_path: str) -> str:
        return f"{self.prefix}/{case_id}/{relative_path}"

    def put_file(self, pathname: str, source_path: Path, *, content_type: str | None = None) -> BlobUpload:
        self.files[pathname] = source_path.read_bytes()
        return BlobUpload(pathname=pathname, url=f"https://blob.example/{pathname}", content_type=content_type or "")

    def put_json(self, pathname: str, payload: dict) -> BlobUpload:
        self.json_payloads[pathname] = payload
        return BlobUpload(pathname=pathname, url=f"https://blob.example/{pathname}", content_type="application/json")


def test_persist_case_dir_to_blob_writes_bundle_with_blob_urls_and_report_content(tmp_path: Path) -> None:
    case_id = "blob_case"
    case_dir = tmp_path / case_id
    input_dir = case_dir / "input"
    analysis_dir = case_dir / "analysis"
    input_dir.mkdir(parents=True)

    waveform = input_dir / "waveform.csv"
    waveform.write_text(Path("examples/sample_waveform.csv").read_text(encoding="utf-8"), encoding="utf-8")
    run_real_waveform_evaluation(waveform_path=waveform, internal_waveform_path=None, output_dir=analysis_dir)
    run_product_demo(input_dir=analysis_dir, output_dir=case_dir / "product_demo", case_id=case_id)

    store = FakeBlobStore()
    persist_case_dir_to_blob(store, case_dir, case_id)

    bundle = store.json_payloads[f"web_cases/{case_id}/dashboard_bundle.json"]
    assert bundle["case_id"] == case_id
    assert bundle["summary"]["evidence"]["data_source"] == "real_simulation_csv"
    assert bundle["summary"]["evidence"]["engineering_validity"] == "simulation_only"
    assert bundle["summary"]["evidence"]["must_resimulate"] is True
    assert bundle["figures"][0]["url"].startswith("https://blob.example/web_cases/blob_case/")
    assert bundle["reports"][0]["url"].startswith("https://blob.example/web_cases/blob_case/")
    assert "data_source = real_simulation_csv" in bundle["reports"][0]["content"]

    url_index = store.json_payloads[f"web_cases/{case_id}/blob_urls.json"]
    assert "product_demo/blob_case/06_dashboard_data/dashboard_summary.json" in url_index["urls"]
