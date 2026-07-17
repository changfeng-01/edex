from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

EXPECTED_STEMS = [
    "00_材料总目录与提交检查清单",
    "01_软件著作权登记申请表填报底稿",
    "02_业务理解与软件设计说明书",
    "03_软件操作手册暨文档鉴别材料",
    "04_源程序鉴别材料_前30页后30页",
    "05_技术开发（合作）合同",
    "05A_共同开发与著作权归属确认书",
    "06_第三方组件与权利边界说明",
]
ROOT = Path(__file__).resolve().parents[2]
TOOLING_FILES = (
    "scripts/software_copyright/build_materials.py",
    "scripts/software_copyright/validate_materials.py",
    "scripts/software_copyright/finalize_package.py",
    "tests/test_software_copyright_materials.py",
)
INVENTORY_EXCLUDED = {
    "internal_support/qa/material_validation_report.json",
    "材料文件SHA256清单.csv",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tooling_hashes() -> dict[str, str]:
    return {relative: sha256(ROOT / relative) for relative in TOOLING_FILES}


def pdf_hashes(package: Path) -> dict[str, str]:
    return {f"{stem}.pdf": sha256(package / f"{stem}.pdf") for stem in EXPECTED_STEMS}


def mapping_digest(values: dict[str, str]) -> str:
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def package_inventory(package: Path) -> dict[str, dict[str, object]]:
    inventory: dict[str, dict[str, object]] = {}
    for path in sorted(item for item in package.rglob("*") if item.is_file()):
        relative = str(path.relative_to(package)).replace("\\", "/")
        if relative in INVENTORY_EXCLUDED:
            continue
        inventory[relative] = {"sha256": sha256(path), "bytes": path.stat().st_size}
    return inventory


def assert_package_inventory(package: Path, report: dict) -> None:
    expected_rows = report.get("validated_package_inventory")
    if not isinstance(expected_rows, list) or not expected_rows:
        raise RuntimeError("validation report has no package inventory")
    expected: dict[str, dict[str, object]] = {}
    for row in expected_rows:
        relative = row.get("path") if isinstance(row, dict) else None
        if not relative or relative in expected:
            raise RuntimeError("validation report package inventory is invalid")
        expected[relative] = {"sha256": row.get("sha256"), "bytes": row.get("bytes")}
    actual = package_inventory(package)
    if set(actual) != set(expected):
        added = sorted(set(actual) - set(expected))
        missing = sorted(set(expected) - set(actual))
        raise RuntimeError(f"package inventory changed after validation; added={added}, missing={missing}")
    for relative, metadata in actual.items():
        if metadata != expected[relative]:
            raise RuntimeError(f"package file changed after validation: {relative}")


def assert_validation_fresh(package: Path, report: dict, expected_stems: list[str]) -> None:
    documents = report.get("documents", [])
    by_stem = {item.get("stem"): item for item in documents}
    if set(by_stem) != set(expected_stems):
        raise RuntimeError("validation report document set does not match the package contract")
    for stem in expected_stems:
        item = by_stem[stem]
        for suffix in ("docx", "pdf"):
            path = package / f"{stem}.{suffix}"
            expected = item.get(suffix, {}).get("sha256")
            if not path.is_file() or not expected or sha256(path) != expected:
                raise RuntimeError(f"{path.name} changed after validation")
        provenance = item.get("render_provenance", {})
        if provenance.get("pdf_sha256") != item["pdf"]["sha256"]:
            raise RuntimeError(f"render provenance does not match validated PDF: {stem}")
        page_paths = provenance.get("page_paths", [])
        page_hashes = provenance.get("page_sha256", [])
        if len(page_paths) != item.get("rendered_pages") or len(page_hashes) != item.get("rendered_pages"):
            raise RuntimeError(f"rendered page provenance is incomplete: {stem}")
        for relative, expected_hash in zip(page_paths, page_hashes):
            rendered_page = package / relative
            if not rendered_page.is_file() or sha256(rendered_page) != expected_hash:
                raise RuntimeError(f"rendered page changed after validation: {relative}")
        contact = package / item.get("contact_sheet", "")
        if not contact.is_file() or sha256(contact) != item.get("contact_sheet_sha256"):
            raise RuntimeError(f"contact sheet changed after validation: {stem}")
    if "04_源程序鉴别材料_前30页后30页" in expected_stems:
        traceability = report.get("source_traceability", {})
        traced_files = {
            "source_manifest_sha256": package / "source_manifest.csv",
            "source_line_manifest_sha256": package / "internal_support" / "source_line_manifest.csv",
            "source_docx_sha256": package / "04_源程序鉴别材料_前30页后30页.docx",
            "source_pdf_sha256": package / "04_源程序鉴别材料_前30页后30页.pdf",
        }
        for key, path in traced_files.items():
            if not path.is_file() or traceability.get(key) != sha256(path):
                raise RuntimeError(f"source traceability file changed after validation: {path.name}")


def assert_safe_package_paths(package: Path, zip_path: Path) -> None:
    if package.name.casefold() == "circuitpilot_v1.0" or zip_path.stem.casefold() == "circuitpilot_v1.0":
        raise RuntimeError("refusing to overwrite the legacy CircuitPilot_V1.0 package")
    if zip_path.stem != package.name:
        raise RuntimeError("ZIP filename must match the package directory name")
    if zip_path.is_relative_to(package):
        raise RuntimeError("ZIP output must be outside the package directory")
    if zip_path.exists() and os.environ.get("CIRCUITPILOT_ALLOW_MATERIAL_REBUILD") != "1":
        raise RuntimeError("ZIP output already exists; refusing to overwrite without explicit rebuild opt-in")


def assert_expected_top_level(package: Path) -> None:
    expected_files = {
        *(f"{stem}.docx" for stem in EXPECTED_STEMS),
        *(f"{stem}.pdf" for stem in EXPECTED_STEMS),
        "snapshot_manifest.json",
        "source_manifest.csv",
        "材料文件SHA256清单.csv",
    }
    actual_files = {path.name for path in package.iterdir() if path.is_file()}
    unexpected = sorted(actual_files - expected_files)
    if unexpected:
        raise RuntimeError("unexpected top-level package files: " + ", ".join(unexpected))
    actual_dirs = {path.name for path in package.iterdir() if path.is_dir()}
    if actual_dirs != {"internal_support"}:
        raise RuntimeError("unexpected top-level package directories: " + ", ".join(sorted(actual_dirs)))


def load_passed_evidence(path: Path, label: str, required_keys: set[str] | None = None) -> dict:
    if not path.is_file():
        raise RuntimeError(f"missing {label} evidence: {path}")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    if evidence.get("status") != "passed":
        raise RuntimeError(f"{label} evidence is not passed")
    missing = (required_keys or set()) - set(evidence)
    if missing:
        raise RuntimeError(f"{label} evidence is incomplete: " + ", ".join(sorted(missing)))
    return evidence


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: finalize_package.py PACKAGE_DIR ZIP_PATH", file=sys.stderr)
        return 2
    package = Path(sys.argv[1]).resolve()
    zip_path = Path(sys.argv[2]).resolve()
    assert_safe_package_paths(package, zip_path)
    assert_expected_top_level(package)
    manifest_path = package / "snapshot_manifest.json"
    report_path = package / "internal_support" / "qa" / "material_validation_report.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "passed":
        raise RuntimeError("material validation report is not passed")
    assert_validation_fresh(package, report, EXPECTED_STEMS)
    assert_package_inventory(package, report)
    tests = load_passed_evidence(
        package / "internal_support" / "qa" / "test_results.json",
        "test",
        {
            "backend_pytest",
            "material_tooling_pytest_after_review",
            "frontend_vitest",
            "frontend_production_build",
            "deterministic_product_demo",
        },
    )
    for key, value in tests.items():
        if key not in {"status", "binding"} and (not isinstance(value, dict) or value.get("status") != "passed"):
            raise RuntimeError(f"test evidence item is not passed: {key}")
    if tests["backend_pytest"].get("passed", 0) < 1 or tests["frontend_vitest"].get("passed", 0) < 1:
        raise RuntimeError("test evidence pass counts are invalid")
    demo_boundary = tests["deterministic_product_demo"].get("evidence_boundary", {})
    if demo_boundary != {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }:
        raise RuntimeError("deterministic demo evidence boundary is invalid")
    visual_review = load_passed_evidence(
        package / "internal_support" / "qa" / "manual_visual_review.json",
        "manual visual review",
        {"scope", "docx_render_path", "pdf_rerender_path", "boundary_pages", "findings"},
    )
    if visual_review.get("boundary_pages", {}).get("source_identification") != [1, 30, 31, 60]:
        raise RuntimeError("manual visual review is missing source boundary pages")
    bindings = report.get("evidence_bindings", {})
    baseline_commit = manifest.get("git", {}).get("baseline_commit")
    current_tooling = tooling_hashes()
    current_pdf_hashes = pdf_hashes(package)
    if bindings.get("source_snapshot_commit") != baseline_commit:
        raise RuntimeError("validation report source snapshot binding is invalid")
    if bindings.get("material_tooling_sha256") != current_tooling:
        raise RuntimeError("material tooling changed after validation")
    if bindings.get("pdf_sha256") != current_pdf_hashes:
        raise RuntimeError("validated PDF-set binding is invalid")
    if bindings.get("pdf_set_sha256") != mapping_digest(current_pdf_hashes):
        raise RuntimeError("validated PDF-set digest is invalid")
    if bindings.get("test_results_sha256") != sha256(package / "internal_support" / "qa" / "test_results.json"):
        raise RuntimeError("test evidence changed after validation")
    if bindings.get("manual_visual_review_sha256") != sha256(package / "internal_support" / "qa" / "manual_visual_review.json"):
        raise RuntimeError("manual visual-review evidence changed after validation")
    if tests.get("binding", {}).get("source_snapshot_commit") != baseline_commit:
        raise RuntimeError("test evidence source snapshot binding is invalid")
    if tests.get("binding", {}).get("material_tooling_sha256") != current_tooling:
        raise RuntimeError("test evidence material-tooling binding is invalid")
    visual_binding = visual_review.get("binding", {})
    if visual_binding.get("source_snapshot_commit") != baseline_commit:
        raise RuntimeError("manual visual-review source snapshot binding is invalid")
    if visual_binding.get("pdf_sha256") != current_pdf_hashes:
        raise RuntimeError("manual visual-review PDF binding is invalid")
    if visual_binding.get("pdf_set_sha256") != mapping_digest(current_pdf_hashes):
        raise RuntimeError("manual visual-review PDF-set digest is invalid")

    package_files = sorted(
        path for path in package.rglob("*")
        if path.is_file() and path.name != "材料文件SHA256清单.csv"
    )
    checksum_path = package / "材料文件SHA256清单.csv"
    with checksum_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=["文件名", "SHA-256", "字节数"])
        writer.writeheader()
        for path in package_files:
            writer.writerow(
                {
                    "文件名": str(path.relative_to(package)).replace("\\", "/"),
                    "SHA-256": sha256(path),
                    "字节数": path.stat().st_size,
                }
            )

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                zf.write(path, Path(package.name) / path.relative_to(package))
    print(
        json.dumps(
            {
                "package": str(package),
                "zip": str(zip_path),
                "zip_bytes": zip_path.stat().st_size,
                "zip_sha256": sha256(zip_path),
                "package_files": len(package_files) + 1,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
