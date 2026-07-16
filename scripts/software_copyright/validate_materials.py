from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont, ImageStat
from pypdf import PdfReader


FULL_NAME = "芯智调参：基于仿真数据的电路参数智能推荐系统"
SHORT_NAME = "芯智调参"
VERSION = "V1.0"
BASELINE = "b97915fa600b31213c208b90b6b2278a4bbaf4ad"
BOUNDARIES = (
    "data_source = real_simulation_csv",
    "engineering_validity = simulation_only",
    "must_resimulate = true",
)
EXPECTED_DOCS = [
    "00_材料总目录与提交检查清单",
    "01_软件著作权登记申请表填报底稿",
    "02_业务理解与软件设计说明书",
    "02A_文档鉴别材料_前30页后30页",
    "03_软件操作手册",
    "04_源程序鉴别材料_前30页后30页",
    "05_合作开发与著作权归属确认书",
    "06_第三方组件与权利边界说明",
]
FIXED_PAGES = {
    "02A_文档鉴别材料_前30页后30页": 60,
    "04_源程序鉴别材料_前30页后30页": 60,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


def allowed_placeholder(value: str) -> bool:
    allowed = (
        r"首次发表城市",
        r"申请代表(?:姓名|电话|邮箱)?",
        r"共同著作权人\d+(?:姓名)?",
        r"证件类型/号码\d+",
        r"地址/电话/邮箱\d+",
        r"实际开发贡献\d+",
        r"成员\d+(?:姓名|实际开发贡献|证据索引|签字)?",
        r"姓名",
        r"签字",
        r"签字日期",
        r"证件号码",
        r"联系电话",
    )
    return any(re.fullmatch(pattern, value) for pattern in allowed)


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
    source_pages = manifest["source"]["identification_material"]["pages"]
    if len(source_pages) != 60 or any(page["source_line_count"] != 50 for page in source_pages):
        errors.append("source page map must contain 60 pages with 50 source lines each")
    doc_pages = manifest["document_identification_material"]["pages"]
    if len(doc_pages) != 60 or any(page["line_count"] != 30 for page in doc_pages):
        errors.append("document page map must contain 60 pages with 30 lines each")

    source_manifest = output / "source_manifest.csv"
    if not source_manifest.is_file() or source_manifest.stat().st_size < 1000:
        errors.append("source_manifest.csv is missing or unexpectedly small")

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
        expected = FIXED_PAGES.get(stem)
        if expected and page_count != expected:
            errors.append(f"{pdf.name}: expected {expected} pages, got {page_count}")
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
        docs.append(
            {
                "stem": stem,
                "docx": {"sha256": sha256(docx), "bytes": docx.stat().st_size},
                "pdf": {"sha256": sha256(pdf), "bytes": pdf.stat().st_size, "pages": page_count},
                "rendered_pages": len(page_pngs),
                "page_metrics": metrics,
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
        "2026年05月16日",
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

    status = "passed" if not errors else "failed"
    report = {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "documents": docs,
        "allowed_placeholders": placeholders,
        "fixed_layout": {
            "source_pages": len(source_pages),
            "source_lines_per_page": sorted(set(p["source_line_count"] for p in source_pages)),
            "document_pages": len(doc_pages),
            "document_lines_per_page": sorted(set(p["line_count"] for p in doc_pages)),
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
        f"- 文档鉴别材料：{len(doc_pages)}页，每页30行",
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
        "document_material_pages": len(doc_pages),
        "document_lines_per_page": 30,
        "rendered_png_pages": sum(item["rendered_pages"] for item in docs),
        "visual_warnings": len(warnings),
        "errors": errors,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "errors": errors, "warnings": len(warnings), "report": str(report_path)}, ensure_ascii=False))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
