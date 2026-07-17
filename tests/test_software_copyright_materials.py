from __future__ import annotations

import hashlib
import zipfile

import pytest

from scripts.software_copyright import build_materials
from scripts.software_copyright import finalize_package
from scripts.software_copyright import validate_materials


def test_template_aligned_identity_and_publication_dates() -> None:
    assert build_materials.COMPLETION_DATE == "2026年07月15日"
    assert build_materials.FIRST_PUBLICATION_DATE == "2026年07月15日"
    assert build_materials.DEFAULT_OUTPUT.name == "CircuitPilot_V1.0_template_aligned"


def test_template_aligned_document_contract() -> None:
    specs = build_materials.DOCUMENT_SPECS

    assert specs["00_材料总目录与提交检查清单"]["pdf_pages"] == 3
    assert specs["01_软件著作权登记申请表填报底稿"]["pdf_pages"] == 6
    assert specs["02_业务理解与软件设计说明书"]["pdf_pages"] == 12
    assert specs["03_软件操作手册暨文档鉴别材料"]["pdf_pages"] == 18
    assert specs["03_软件操作手册暨文档鉴别材料"]["submission_role"] == "正式文档鉴别材料"
    assert specs["04_源程序鉴别材料_前30页后30页"]["pdf_pages"] == 60
    assert specs["05_技术开发（合作）合同"]["pdf_pages"] == 16
    assert specs["05A_共同开发与著作权归属确认书"]["pdf_pages"] == 4
    assert specs["06_第三方组件与权利边界说明"]["pdf_pages"] == 3

    assert list(validate_materials.EXPECTED_DOCS) == list(specs)
    assert "02A_文档鉴别材料_前30页后30页" not in validate_materials.EXPECTED_DOCS


def test_snapshot_manifest_contract_is_template_aligned() -> None:
    assert build_materials.MANIFEST_SCHEMA_VERSION == "1.1"
    assert build_materials.TEMPLATE_ALIGNMENT["application_form"] == "3.申请表模板.doc"
    assert build_materials.TEMPLATE_ALIGNMENT["source_code"] == "4.程序鉴别材料模板.doc"
    assert build_materials.TEMPLATE_ALIGNMENT["manual_primary"] == "5.3说明书-虚拟机管理系统（应用软件）.doc"
    assert build_materials.TEMPLATE_ALIGNMENT["manual_screenshots"] == "5.5说明书-网页截图软件（应用软件）.doc"
    assert build_materials.TEMPLATE_ALIGNMENT["cooperation_contract"] == "6.技术开发（合作）合同模板.doc"


def test_old_material_package_path_is_rejected(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="旧版材料目录"):
        build_materials.ensure_safe_output_path(tmp_path / "CircuitPilot_V1.0")


def test_nonempty_template_output_requires_explicit_rebuild_opt_in(tmp_path, monkeypatch) -> None:
    target = tmp_path / "CircuitPilot_V1.0_template_aligned"
    target.mkdir()
    (target / "existing.txt").write_text("keep", encoding="utf-8")
    monkeypatch.delenv("CIRCUITPILOT_ALLOW_MATERIAL_REBUILD", raising=False)
    with pytest.raises(RuntimeError, match="非空"):
        build_materials.ensure_safe_output_path(target)


def test_finalize_rejects_files_changed_after_validation(tmp_path) -> None:
    docx = tmp_path / "example.docx"
    pdf = tmp_path / "example.pdf"
    docx.write_bytes(b"docx-v1")
    pdf.write_bytes(b"pdf-v1")
    contact = tmp_path / "contact.png"
    contact.write_bytes(b"contact-v1")
    rendered = tmp_path / "rendered-page.png"
    rendered.write_bytes(b"rendered-page-v1")
    pdf_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    report = {
        "documents": [
            {
                "stem": "example",
                "docx": {"sha256": hashlib.sha256(docx.read_bytes()).hexdigest()},
                "pdf": {"sha256": pdf_hash},
                "rendered_pages": 1,
                "render_provenance": {
                    "pdf_sha256": pdf_hash,
                    "page_paths": [rendered.name],
                    "page_sha256": [hashlib.sha256(rendered.read_bytes()).hexdigest()],
                },
                "contact_sheet": contact.name,
                "contact_sheet_sha256": hashlib.sha256(contact.read_bytes()).hexdigest(),
            }
        ]
    }

    finalize_package.assert_validation_fresh(tmp_path, report, ["example"])
    pdf.write_bytes(b"pdf-v2")
    with pytest.raises(RuntimeError, match="changed after validation"):
        finalize_package.assert_validation_fresh(tmp_path, report, ["example"])


def test_finalize_inventory_rejects_stale_or_added_package_files(tmp_path) -> None:
    snapshot = tmp_path / "snapshot_manifest.json"
    snapshot.write_text('{"schema_version":"1.1"}', encoding="utf-8")
    expected = [
        {"path": path, **metadata}
        for path, metadata in finalize_package.package_inventory(tmp_path).items()
    ]
    report = {"validated_package_inventory": expected}

    finalize_package.assert_package_inventory(tmp_path, report)
    snapshot.write_text('{"schema_version":"tampered"}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="changed after validation"):
        finalize_package.assert_package_inventory(tmp_path, report)

    snapshot.write_text('{"schema_version":"1.1"}', encoding="utf-8")
    (tmp_path / "unexpected-private.txt").write_text("private", encoding="utf-8")
    with pytest.raises(RuntimeError, match="inventory changed"):
        finalize_package.assert_package_inventory(tmp_path, report)


def test_finalize_rejects_zip_inside_package_and_empty_evidence(tmp_path) -> None:
    package = tmp_path / "CircuitPilot_V1.0_template_aligned"
    package.mkdir()
    with pytest.raises(RuntimeError, match="outside"):
        finalize_package.assert_safe_package_paths(package, package / f"{package.name}.zip")

    evidence = package / "empty_evidence.json"
    evidence.write_text('{"status":"passed"}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="incomplete"):
        finalize_package.load_passed_evidence(evidence, "test", {"backend_pytest"})


def test_source_order_places_support_surfaces_between_product_and_evaluation_core() -> None:
    ordered_paths = [
        "src/goa_eval/product_api/app.py",
        "src/goa_eval/product/project_service.py",
        "src/goa_eval/web_api/app.py",
        "src/goa_eval/web/upload.py",
        "frontend/src/App.tsx",
        "scripts/run_upload_demo.py",
        "src/goa_eval/ca/metrics.py",
        "src/goa_eval/pia/recommendation.py",
        "src/goa_eval/llso/optimizer.py",
        "src/goa_eval/multi_agent/coordinator.py",
        "src/goa_eval/windowing.py",
    ]

    ranks = [build_materials.source_group(path)[0] for path in ordered_paths]
    assert ranks == sorted(ranks)


def test_source_blob_reader_is_pinned_to_declared_baseline(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_check_output(args, cwd):
        captured["args"] = args
        captured["cwd"] = cwd
        return b"baseline source\n"

    monkeypatch.setattr(build_materials.subprocess, "check_output", fake_check_output)
    assert build_materials.read_baseline_blob("src/goa_eval/example.py") == b"baseline source\n"
    assert captured["args"] == [
        "git",
        "show",
        f"{build_materials.BASELINE_COMMIT}:src/goa_eval/example.py",
    ]
    assert captured["cwd"] == build_materials.ROOT


def test_validator_source_blob_reader_is_pinned_to_declared_baseline(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_check_output(args, cwd):
        captured["args"] = args
        captured["cwd"] = cwd
        return b"validated baseline source\n"

    monkeypatch.setattr(validate_materials.subprocess, "check_output", fake_check_output)
    assert validate_materials.read_baseline_blob("src/goa_eval/example.py") == b"validated baseline source\n"
    assert captured["args"] == [
        "git",
        "show",
        f"{validate_materials.BASELINE}:src/goa_eval/example.py",
    ]
    assert captured["cwd"] == validate_materials.ROOT


def test_source_pages_use_continuous_submission_numbers_and_preserve_original_positions() -> None:
    stream = [
        {
            "global_line": line_no,
            "file_order": 1,
            "path": "src/goa_eval/example.py",
            "file_line": line_no,
            "text": f"value_{line_no} = {line_no}",
        }
        for line_no in range(1, 5001)
    ]

    pages = build_materials.select_source_pages(stream)

    assert len(pages) == 60
    assert all(len(page) == 50 for page in pages)
    selected = [line for page in pages for line in page]
    assert [line["display_line"] for line in selected] == list(range(1, 3001))
    assert selected[0]["global_line"] == 1
    assert selected[1499]["global_line"] == 1500
    assert selected[1500]["global_line"] == 3501
    assert selected[-1]["global_line"] == 5000


def test_source_line_scaling_keeps_long_physical_lines_single_line() -> None:
    assert build_materials.source_char_scale(80) == 81
    assert build_materials.source_char_scale(120) <= 55
    assert build_materials.source_char_scale(226) <= 30


def test_source_docx_contains_template_header_and_visible_submission_line_numbers(tmp_path) -> None:
    lines = [f"value_{line_no} = {line_no}" for line_no in range(1, 5001)]
    entries = [
        {
            "path": "src/goa_eval/example.py",
            "language": "Python",
            "line_count": len(lines),
            "sha256": "0" * 64,
            "source_group": "评估内核与命令行",
            "_rank": 10,
            "_lines": lines,
        }
    ]

    info = build_materials.build_source_doc(tmp_path, entries)
    path = tmp_path / info["path"]
    with zipfile.ZipFile(path) as archive:
        body = archive.read("word/document.xml").decode("utf-8")
        headers = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.startswith("word/header")
        )

    assert "0001" in body and "value_1 = 1" in body
    assert "1500" in body and "value_1500 = 1500" in body
    assert "1501" in body and "value_3501 = 3501" in body
    assert "3000" in body and "value_5000 = 5000" in body
    assert "源代码" in headers
    assert "第1页，共60页" in headers
    assert "文件路径：src/goa_eval/example.py" in headers
    assert info["pages"][30]["display_start"] == 1501
    assert info["pages"][30]["original_global_start"] == 3501
