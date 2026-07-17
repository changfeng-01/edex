from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont, ImageStat
from pypdf import PdfReader


FULL_NAME = "芯智调参：基于仿真数据的电路参数智能推荐系统"
SHORT_NAME = "芯智调参"
VERSION = "V1.0"
BASELINE = "4ea050e47957a3d984ca9ea95f71c53be0e0f3cf"
BOUNDARIES = (
    "data_source = real_simulation_csv",
    "engineering_validity = simulation_only",
    "must_resimulate = true",
)
EXPECTED_DOCS = [
    "00_材料总目录与提交检查清单",
    "01_软件著作权登记申请表填报底稿",
    "02_业务理解与软件设计说明书",
    "03_软件操作手册暨文档鉴别材料",
    "04_源程序鉴别材料_前30页后30页",
    "05_技术开发（合作）合同",
    "05A_共同开发与著作权归属确认书",
    "06_第三方组件与权利边界说明",
]
FIXED_PAGES = {
    "00_材料总目录与提交检查清单": 3,
    "01_软件著作权登记申请表填报底稿": 6,
    "02_业务理解与软件设计说明书": 12,
    "03_软件操作手册暨文档鉴别材料": 18,
    "04_源程序鉴别材料_前30页后30页": 60,
    "05_技术开发（合作）合同": 16,
    "05A_共同开发与著作权归属确认书": 4,
    "06_第三方组件与权利边界说明": 3,
}
ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_SIGNATURES = {
    "00_材料总目录与提交检查清单": "提交前检查清单",
    "01_软件著作权登记申请表填报底稿": "附件与正式生成检查",
    "02_业务理解与软件设计说明书": "部署、验收、版本与限制",
    "03_软件操作手册暨文档鉴别材料": "停止、备份与验收",
    "05_技术开发（合作）合同": "第二十九条",
    "05A_共同开发与著作权归属确认书": "共同权属与申请授权",
    "06_第三方组件与权利边界说明": "原创范围、排除项与合规核对",
}

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
STATIC_SUPPORT_FILES = {
    "internal_support/design_traceability.csv",
    "internal_support/source_line_manifest.csv",
    "internal_support/template_alignment_audit.json",
    "internal_support/product_demo_test_only/deterministic_simulation_results.csv",
    "internal_support/product_demo_test_only/evidence_package.json",
    "internal_support/product_demo_test_only/product_demo_manifest.json",
    "internal_support/product_demo_test_only/product_report.md",
    "internal_support/qa/manual_visual_review.json",
    "internal_support/qa/material_validation_report.json",
    "internal_support/qa/material_validation_report.md",
    "internal_support/qa/test_results.json",
    "internal_support/screenshots_test_only/README.txt",
    *(f"internal_support/screenshots_test_only/{index:02d}_{name}.png" for index, name in enumerate((
        "public_demo",
        "project_list",
        "create_project",
        "project_overview",
        "baseline_design_version",
        "baseline_analysis",
        "candidate_approval",
        "simulation_job",
        "result_design_version",
        "result_analysis",
        "version_comparison",
        "upload_workspace",
    ), 1)),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_baseline_blob(relative_path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{BASELINE}:{relative_path}"], cwd=ROOT)


def tooling_hashes() -> dict[str, str]:
    return {relative: sha256(ROOT / relative) for relative in TOOLING_FILES}


def pdf_hashes(output: Path) -> dict[str, str]:
    return {f"{stem}.pdf": sha256(output / f"{stem}.pdf") for stem in EXPECTED_DOCS}


def mapping_digest(values: dict[str, str]) -> str:
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def package_inventory(output: Path) -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        relative = str(path.relative_to(output)).replace("\\", "/")
        if relative in INVENTORY_EXCLUDED:
            continue
        inventory.append({"path": relative, "sha256": sha256(path), "bytes": path.stat().st_size})
    return inventory


def extract_docx_text(path: Path) -> str:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    chunks: list[str] = []
    with zipfile.ZipFile(path) as zf:
        names = [
            name
            for name in zf.namelist()
            if name == "word/document.xml"
            or name.startswith("word/header")
            or name.startswith("word/footer")
        ]
        for name in names:
            root = ET.fromstring(zf.read(name))
            chunks.extend(node.text or "" for node in root.findall(".//w:t", ns))
    return "\n".join(chunks)


def extract_document_paragraphs(path: Path) -> list[str]:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    return [
        "".join(node.text or "" for node in paragraph.findall(".//w:t", ns))
        for paragraph in root.findall(".//w:p", ns)
    ]


def docx_pdf_text_coverage(docx: Path, pdf_text: str) -> float:
    pdf_normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", pdf_text)
    signatures = []
    for paragraph in extract_document_paragraphs(docx):
        normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", paragraph)
        if len(normalized) >= 10:
            signatures.append(normalized)
    if not signatures:
        return 0.0
    return sum(signature in pdf_normalized for signature in signatures) / len(signatures)


def allowed_placeholder(value: str) -> bool:
    allowed = (
        r"首次发表城市",
        r"申请代表(?:姓名(?:及授权依据)?)?",
        r"(?:共同申请人)?姓名",
        r"证件(?:类型及)?号码",
        r"地址",
        r"电话",
        r"邮箱",
        r"实际开发贡献",
        r"提交/评审/文档证据索引",
        r"签字",
        r"签章",
        r"年/月/日",
        r"合同编号",
        r"签订地点",
        r"约定有管辖权的人民法院或仲裁机构",
    )
    return any(re.fullmatch(pattern, value) for pattern in allowed)


def validate_source_traceability(output: Path) -> list[str]:
    errors: list[str] = []
    source_manifest = output / "source_manifest.csv"
    line_manifest = output / "internal_support" / "source_line_manifest.csv"
    source_docx = output / "04_源程序鉴别材料_前30页后30页.docx"
    if not source_manifest.is_file():
        return ["source_manifest.csv is missing"]
    if not line_manifest.is_file():
        return ["internal_support/source_line_manifest.csv is missing"]

    with source_manifest.open(encoding="utf-8-sig", newline="") as file:
        file_rows = list(csv.DictReader(file))
    if [int(row["order"]) for row in file_rows] != list(range(1, len(file_rows) + 1)):
        errors.append("source_manifest.csv order must be continuous from 1")

    stream: list[dict] = []
    global_line = 0
    for row in file_rows:
        rel = row["path"].replace("\\", "/")
        try:
            raw = read_baseline_blob(rel)
        except subprocess.CalledProcessError:
            errors.append(f"source manifest path is missing from baseline {BASELINE}: {rel}")
            continue
        digest = hashlib.sha256(raw).hexdigest()
        lines = raw.decode("utf-8", errors="replace").splitlines()
        if digest != row["sha256"]:
            errors.append(f"source manifest hash mismatch: {rel}")
        if len(lines) != int(row["line_count"]):
            errors.append(f"source manifest line count mismatch: {rel}")
        for file_line, text in enumerate(lines, 1):
            global_line += 1
            stream.append(
                {
                    "global_line": global_line,
                    "path": rel,
                    "file_line": file_line,
                    "text": text.expandtabs(4),
                    "file_sha256": digest,
                }
            )
    if len(stream) < 3000:
        errors.append("source stream is too short for front/back 30-page extraction")
        return errors
    expected = stream[:1500] + stream[-1500:]

    with line_manifest.open(encoding="utf-8-sig", newline="") as file:
        line_rows = list(csv.DictReader(file))
    if len(line_rows) != 3000:
        errors.append(f"source line manifest must contain 3000 rows, got {len(line_rows)}")
        return errors
    for submission_line, (row, source) in enumerate(zip(line_rows, expected), 1):
        expected_values = {
            "submission_line": str(submission_line),
            "display_page": str((submission_line - 1) // 50 + 1),
            "segment": "front" if submission_line <= 1500 else "back",
            "original_global_line": str(source["global_line"]),
            "path": source["path"],
            "file_line": str(source["file_line"]),
            "file_sha256": source["file_sha256"],
        }
        if any(row.get(key) != value for key, value in expected_values.items()):
            errors.append(f"source line manifest mismatch at submission line {submission_line}")
            break

    if source_docx.is_file():
        paragraphs = extract_document_paragraphs(source_docx)
        visible_lines = [paragraph for paragraph in paragraphs if re.match(r"^\d{4}  ", paragraph)]
        if len(visible_lines) != 3000:
            errors.append(f"source DOCX must contain exactly 3000 visible lines, got {len(visible_lines)}")
        else:
            for submission_line, (paragraph, source) in enumerate(zip(visible_lines, expected), 1):
                if paragraph[:6] != f"{submission_line:04d}  " or paragraph[6:] != source["text"]:
                    errors.append(f"source DOCX content mismatch at submission line {submission_line}")
                    break
    return errors


def image_metrics(path: Path) -> dict:
    with Image.open(path) as img:
        gray = img.convert("L")
        stat = ImageStat.Stat(gray)
        threshold = gray.point(lambda x: 0 if x < 245 else 255, "1")
        bbox = threshold.getbbox()
        width, height = gray.size
        nonwhite = sum(1 for value in gray.resize((max(1, width // 12), max(1, height // 12))).getdata() if value < 245)
        sample_pixels = max(1, (width // 12) * (height // 12))
        edge = max(3, min(width, height) // 200)
        edge_bands = [
            gray.crop((0, 0, width, edge)),
            gray.crop((0, height - edge, width, height)),
            gray.crop((0, 0, edge, height)),
            gray.crop((width - edge, 0, width, height)),
        ]
        edge_dark = max(255 - ImageStat.Stat(band).mean[0] for band in edge_bands)
        return {
            "width": width,
            "height": height,
            "mean_gray": round(stat.mean[0], 3),
            "ink_ratio_sample": round(nonwhite / sample_pixels, 5),
            "edge_darkness": round(edge_dark, 3),
            "content_bbox": list(bbox) if bbox else None,
        }


def make_contact_sheet(pages: list[Path], target: Path, title: str) -> None:
    thumb_w, thumb_h = 240, 340
    cols = 5
    rows = (len(pages) + cols - 1) // cols
    header_h = 50
    sheet = Image.new("RGB", (cols * thumb_w, header_h + rows * thumb_h), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 12), title, fill="black", font=ImageFont.load_default())
    for i, path in enumerate(pages):
        with Image.open(path) as img:
            preview = img.convert("RGB")
            preview.thumbnail((thumb_w - 14, thumb_h - 26))
            x = (i % cols) * thumb_w + (thumb_w - preview.width) // 2
            y = header_h + (i // cols) * thumb_h + 16
            sheet.paste(preview, (x, y))
            draw.text((i % cols * thumb_w + 6, header_h + (i // cols) * thumb_h + 2), str(i + 1), fill="black")
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, "PNG", optimize=True)


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: validate_materials.py OUTPUT_DIR RENDERED_PNG_DIR QA_OUTPUT_DIR", file=sys.stderr)
        return 2
    output = Path(sys.argv[1]).resolve()
    rendered = Path(sys.argv[2]).resolve()
    qa_output = Path(sys.argv[3]).resolve()
    qa_output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "snapshot_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []
    docs: list[dict] = []
    placeholders: dict[str, list[str]] = {}

    if manifest["git"]["baseline_commit"] != BASELINE:
        errors.append("snapshot_manifest baseline commit mismatch")
    if manifest.get("schema_version") != "1.1":
        errors.append("snapshot_manifest schema_version must be 1.1")
    source_pages = manifest["source"]["identification_material"]["pages"]
    if len(source_pages) != 60 or any(page["source_line_count"] != 50 for page in source_pages):
        errors.append("source page map must contain 60 pages with 50 source lines each")
    for page_index, page in enumerate(source_pages, 1):
        if page["display_start"] != (page_index - 1) * 50 + 1 or page["display_end"] != page_index * 50:
            errors.append(f"source page {page_index}: display line range is not continuous")
    if source_pages and (
        source_pages[29]["display_end"] != 1500
        or source_pages[30]["display_start"] != 1501
        or source_pages[-1]["display_end"] != 3000
    ):
        errors.append("source display line boundary must be 1500/1501 and end at 3000")
    document_material = manifest["document_identification_material"]
    if document_material.get("expected_pdf_pages") != 18 or not document_material.get("complete_document"):
        errors.append("document identification material must be the complete 18-page manual")

    errors.extend(validate_source_traceability(output))
    source_pdf = output / "04_源程序鉴别材料_前30页后30页.pdf"
    if source_pdf.is_file():
        extracted_numbers: list[int] = []
        extracted_code: list[str] = []
        for page_no, page in enumerate(PdfReader(str(source_pdf)).pages, 1):
            lines = (page.extract_text() or "").splitlines()
            numbered_indexes = [index for index, line in enumerate(lines) if re.match(r"^\d{4}\s", line)]
            if len(numbered_indexes) != 50:
                errors.append(f"source PDF page {page_no}: expected 50 numbered physical lines, got {len(numbered_indexes)}")
                continue
            first, last = numbered_indexes[0], numbered_indexes[-1]
            if any(not re.match(r"^\d{4}\s", line) for line in lines[first : last + 1]):
                errors.append(f"source PDF page {page_no}: detected a wrapped or unnumbered source line")
            extracted_numbers.extend(int(lines[index][:4]) for index in numbered_indexes)
            extracted_code.extend(lines[index][4:] for index in numbered_indexes)
        if extracted_numbers != list(range(1, 3001)):
            errors.append("source PDF visible line numbers must be continuous from 0001 to 3000")
        line_manifest = output / "internal_support" / "source_line_manifest.csv"
        with line_manifest.open(encoding="utf-8-sig", newline="") as file:
            line_rows = list(csv.DictReader(file))
        source_cache: dict[str, list[str]] = {}
        for row in line_rows:
            if row["path"] not in source_cache:
                source_cache[row["path"]] = read_baseline_blob(row["path"]).decode(
                    "utf-8", errors="replace"
                ).splitlines()
        expected_code = [
            source_cache[row["path"]][int(row["file_line"]) - 1].expandtabs(4)
            for row in line_rows
        ]
        if len(extracted_code) == len(expected_code):
            for submission_line, (actual, expected_text) in enumerate(zip(extracted_code, expected_code), 1):
                if re.sub(r"\s+", "", actual) != re.sub(r"\s+", "", expected_text):
                    errors.append(f"source PDF code content mismatch at submission line {submission_line}")
                    break

    for index, stem in enumerate(EXPECTED_DOCS, 1):
        docx = output / f"{stem}.docx"
        pdf = output / f"{stem}.pdf"
        if not docx.is_file():
            errors.append(f"missing DOCX: {docx.name}")
            continue
        if not pdf.is_file():
            errors.append(f"missing PDF: {pdf.name}")
            continue
        text = extract_docx_text(docx)
        if FULL_NAME not in text or VERSION not in text:
            errors.append(f"identity text missing in {docx.name}")
        found = sorted(set(re.findall(r"【([^】]+)】", text)))
        placeholders[docx.name] = found
        for value in found:
            if not allowed_placeholder(value):
                errors.append(f"unsupported placeholder in {docx.name}: 【{value}】")
        reader = PdfReader(str(pdf))
        page_count = len(reader.pages)
        pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if FULL_NAME not in pdf_text or VERSION not in pdf_text:
            errors.append(f"identity text missing in {pdf.name}")
        signature = DOCUMENT_SIGNATURES.get(stem)
        if signature and (signature not in text or signature not in pdf_text):
            errors.append(f"DOCX/PDF content signature mismatch for {stem}: {signature}")
        text_coverage = None
        if stem != "04_源程序鉴别材料_前30页后30页":
            text_coverage = docx_pdf_text_coverage(docx, pdf_text)
            if text_coverage < 0.9:
                errors.append(f"DOCX/PDF text coverage too low for {stem}: {text_coverage:.3f}")
        if stem in EXPECTED_DOCS[:3] and "2026年07月15日" not in text:
            errors.append(f"locked completion/publication date missing in {docx.name}")
        expected = FIXED_PAGES.get(stem)
        if expected and page_count != expected:
            errors.append(f"{pdf.name}: expected {expected} pages, got {page_count}")
        if stem == "03_软件操作手册暨文档鉴别材料":
            manual_headings = [
                "目录",
                "软件概述与证据边界",
                "创建项目",
                "上传仿真数据",
                "候选审批",
                "仿真任务导出",
                "外部仿真与结果回填",
                "版本比较",
                "异常处理",
                "安全与隐私说明",
                "停止、备份与验收",
            ]
            for heading in manual_headings:
                if heading not in text or heading not in pdf_text:
                    errors.append(f"manual chapter missing from DOCX/PDF: {heading}")
            for body_page, page in enumerate(reader.pages[1:], 1):
                if f"{body_page}/17" not in (page.extract_text() or ""):
                    errors.append(f"manual body page number missing or discontinuous: {body_page}/17")
            with zipfile.ZipFile(docx) as archive:
                media = [name for name in archive.namelist() if name.startswith("word/media/")]
            if len(media) < 10:
                errors.append(f"manual must contain at least 10 real interface screenshots, got {len(media)}")
        png_dir = rendered / f"{index:02d}"
        page_pngs = sorted(png_dir.glob("page-*.png"))
        if len(page_pngs) != page_count:
            errors.append(f"{pdf.name}: rendered {len(page_pngs)} PNG pages for {page_count}-page PDF")
        metrics = [image_metrics(page) for page in page_pngs]
        for page_no, item in enumerate(metrics, 1):
            if item["ink_ratio_sample"] < 0.002:
                errors.append(f"{pdf.name} page {page_no}: page appears blank")
            if item["edge_darkness"] > 35:
                warnings.append(f"{pdf.name} page {page_no}: dark content close to page edge")
        contact = qa_output / f"{index:02d}_{stem}_contact.png"
        make_contact_sheet(page_pngs, contact, f"{stem} | {page_count} pages")
        archived_render_dir = qa_output / "rendered_pages" / f"{index:02d}"
        archived_render_dir.mkdir(parents=True, exist_ok=True)
        archived_pages: list[Path] = []
        for page in page_pngs:
            archived = archived_render_dir / page.name
            shutil.copy2(page, archived)
            archived_pages.append(archived)
        docs.append(
            {
                "stem": stem,
                "docx": {"sha256": sha256(docx), "bytes": docx.stat().st_size},
                "pdf": {"sha256": sha256(pdf), "bytes": pdf.stat().st_size, "pages": page_count},
                "rendered_pages": len(page_pngs),
                "page_metrics": metrics,
                "docx_pdf_text_coverage": text_coverage,
                "render_provenance": {
                    "pdf_sha256": sha256(pdf),
                    "page_paths": [
                        str(page.relative_to(output)).replace("\\", "/") for page in archived_pages
                    ],
                    "page_sha256": [sha256(page) for page in archived_pages],
                },
                "contact_sheet_sha256": sha256(contact),
                "contact_sheet": str(contact.relative_to(output)).replace("\\", "/")
                if contact.is_relative_to(output)
                else str(contact),
            }
        )

    all_docx_text = "\n".join(extract_docx_text(output / f"{stem}.docx") for stem in EXPECTED_DOCS)
    required_values = [
        FULL_NAME,
        SHORT_NAME,
        VERSION,
        "2026年07月15日",
        "合作开发",
        "原始取得",
        "全部权利",
        *BOUNDARIES,
    ]
    for value in required_values:
        if value not in all_docx_text:
            errors.append(f"required application value not found: {value}")
    forbidden_claims = [
        "已完成流片验证",
        "已完成芯片实测",
        "大量实验验证证明",
        "本软件保证优化效果",
        "本系统保证性能提升",
        "确保候选参数优化成功",
    ]
    for value in forbidden_claims:
        if value in all_docx_text:
            errors.append(f"forbidden overclaim found: {value}")

    allowed_support = set(STATIC_SUPPORT_FILES)
    for item in docs:
        allowed_support.add(item["contact_sheet"])
        allowed_support.update(item["render_provenance"]["page_paths"])
    actual_support = {
        str(path.relative_to(output)).replace("\\", "/")
        for path in (output / "internal_support").rglob("*")
        if path.is_file()
    }
    unexpected_support = sorted(actual_support - allowed_support)
    if unexpected_support:
        errors.append("unexpected internal support files: " + ", ".join(unexpected_support))

    current_tooling = tooling_hashes()
    current_pdf_hashes = pdf_hashes(output)
    current_pdf_set_digest = mapping_digest(current_pdf_hashes)
    evidence_paths = {
        "tests": output / "internal_support" / "qa" / "test_results.json",
        "manual_visual_review": output / "internal_support" / "qa" / "manual_visual_review.json",
    }
    evidence: dict[str, dict] = {}
    for label, path in evidence_paths.items():
        try:
            evidence[label] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid {label} evidence: {exc}")
            evidence[label] = {}
    baseline_commit = manifest.get("git", {}).get("baseline_commit")
    test_binding = evidence["tests"].get("binding", {})
    if test_binding.get("source_snapshot_commit") != baseline_commit:
        errors.append("test evidence is not bound to the source snapshot commit")
    if test_binding.get("material_tooling_sha256") != current_tooling:
        errors.append("test evidence is not bound to the current material tooling")
    visual_binding = evidence["manual_visual_review"].get("binding", {})
    if visual_binding.get("source_snapshot_commit") != baseline_commit:
        errors.append("manual visual review is not bound to the source snapshot commit")
    if visual_binding.get("pdf_sha256") != current_pdf_hashes:
        errors.append("manual visual review is not bound to the current PDF set")
    if visual_binding.get("pdf_set_sha256") != current_pdf_set_digest:
        errors.append("manual visual review PDF-set digest is invalid")

    status = "passed" if not errors else "failed"
    report = {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "documents": docs,
        "source_traceability": {
            "source_manifest_sha256": sha256(output / "source_manifest.csv"),
            "source_line_manifest_sha256": sha256(output / "internal_support" / "source_line_manifest.csv"),
            "source_docx_sha256": sha256(output / "04_源程序鉴别材料_前30页后30页.docx"),
            "source_pdf_sha256": sha256(output / "04_源程序鉴别材料_前30页后30页.pdf"),
        },
        "allowed_placeholders": placeholders,
        "fixed_layout": {
            "source_pages": len(source_pages),
            "source_lines_per_page": sorted(set(p["source_line_count"] for p in source_pages)),
            "document_pages": document_material["expected_pdf_pages"],
            "document_complete": document_material["complete_document"],
        },
        "evidence_bindings": {
            "source_snapshot_commit": baseline_commit,
            "material_tooling_sha256": current_tooling,
            "pdf_sha256": current_pdf_hashes,
            "pdf_set_sha256": current_pdf_set_digest,
            "test_results_sha256": sha256(evidence_paths["tests"]),
            "manual_visual_review_sha256": sha256(evidence_paths["manual_visual_review"]),
        },
    }
    report_path = qa_output / "material_validation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = [
        "# 软著材料自动验收报告",
        "",
        f"- 状态：{status}",
        f"- DOCX/PDF 对数：{len(docs)}",
        f"- PDF 总页数：{sum(item['pdf']['pages'] for item in docs)}",
        f"- 源码鉴别材料：{len(source_pages)}页，每页50行",
        f"- 文档鉴别材料：完整操作手册{document_material['expected_pdf_pages']}页（不足60页提交全文）",
        f"- 错误：{len(errors)}",
        f"- 警告：{len(warnings)}",
        "",
        "## 允许保留的结构化匿名字段",
        "",
    ]
    for filename, values in placeholders.items():
        if values:
            summary.append(f"- {filename}: " + "、".join(f"【{v}】" for v in values))
    if errors:
        summary.extend(["", "## 错误", ""] + [f"- {e}" for e in errors])
    if warnings:
        summary.extend(["", "## 视觉检测提示", ""] + [f"- {w}" for w in warnings])
    (qa_output / "material_validation_report.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    manifest["generated_docx"] = [
        {"path": f"{stem}.docx", "sha256": sha256(output / f"{stem}.docx"), "bytes": (output / f"{stem}.docx").stat().st_size}
        for stem in EXPECTED_DOCS
    ]
    manifest["generated_pdf"] = [
        {"path": f"{stem}.pdf", "sha256": sha256(output / f"{stem}.pdf"), "bytes": (output / f"{stem}.pdf").stat().st_size,
         "pages": len(PdfReader(str(output / f"{stem}.pdf")).pages)}
        for stem in EXPECTED_DOCS
    ]
    manifest["validation"] = {
        "status": status,
        "report": str((qa_output / "material_validation_report.json").relative_to(output)).replace("\\", "/")
        if (qa_output / "material_validation_report.json").is_relative_to(output)
        else str(qa_output / "material_validation_report.json"),
        "pdf_total_pages": sum(item["pdf"]["pages"] for item in docs),
        "source_material_pages": len(source_pages),
        "source_lines_per_page": 50,
        "document_material_pages": document_material["expected_pdf_pages"],
        "document_material_complete": document_material["complete_document"],
        "rendered_png_pages": sum(item["rendered_pages"] for item in docs),
        "visual_warnings": len(warnings),
        "errors": errors,
        "evidence": {
            "test_results": {
                "path": "internal_support/qa/test_results.json",
                "sha256": sha256(evidence_paths["tests"]),
            },
            "manual_visual_review": {
                "path": "internal_support/qa/manual_visual_review.json",
                "sha256": sha256(evidence_paths["manual_visual_review"]),
            },
            "pdf_set_sha256": current_pdf_set_digest,
            "material_tooling_sha256": current_tooling,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report["validated_package_inventory"] = package_inventory(output)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "errors": errors, "warnings": len(warnings), "report": str(report_path)}, ensure_ascii=False))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
