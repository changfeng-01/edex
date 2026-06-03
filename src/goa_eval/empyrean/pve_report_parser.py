from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from goa_eval.empyrean.schemas import (
    STATUS_FAILED,
    STATUS_NOT_PROVIDED,
    STATUS_PASSED,
    STATUS_UNKNOWN,
    STATUS_WARNING,
    VerificationReportStatus,
    base_versions,
)
from goa_eval.io_utils import write_json


CHECKS = ("drc", "lvs", "erc")


def parse_physical_verification_reports(report_paths: dict[str, Path | None], output_path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {**base_versions()}
    for check in CHECKS:
        summary[check] = parse_verification_report(check, report_paths.get(check)).__dict__
    pve_path = report_paths.get("pve")
    if pve_path is not None:
        summary["pve"] = parse_verification_report("pve", pve_path).__dict__
    write_json(output_path, summary)
    return summary


def parse_verification_report(check: str, path: Path | None) -> VerificationReportStatus:
    if path is None or not path.exists():
        return VerificationReportStatus(status=STATUS_NOT_PROVIDED, raw_report_path=str(path) if path else None)
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lower = text.lower()
    error_count = _count_for_words(lower, ["error", "errors", "violation", "violations", "mismatch", "mismatches"])
    warning_count = _count_for_words(lower, ["warning", "warnings"])
    evidence: list[str] = []
    error_types = _error_types(lower)
    status = STATUS_UNKNOWN

    if check == "lvs":
        if re.search(r"\b(correct|matched|match)\b", lower) and not re.search(r"\b(not\s+correct|incorrect|mismatch|failed)\b", lower):
            status = STATUS_PASSED
            evidence.append("lvs_correct_keyword")
        elif re.search(r"\b(incorrect|mismatch|mismatches|failed|not\s+correct)\b", lower) or (error_count or 0) > 0:
            status = STATUS_FAILED
            evidence.append("lvs_failure_keyword_or_errors")
    elif check == "erc":
        open_short_count = _count_for_words(lower, ["open circuits", "open", "short circuits", "short"])
        if open_short_count and open_short_count > 0:
            status = STATUS_FAILED
            evidence.append("erc_open_or_short")
        elif _has_explicit_pass(lower) or _has_zero_errors(lower):
            status = STATUS_PASSED
            evidence.append("erc_pass_or_zero_errors")
        elif re.search(r"\b(failed|fail)\b", lower) or (error_count or 0) > 0:
            status = STATUS_FAILED
            evidence.append("erc_failure_keyword_or_errors")
    else:
        if _has_explicit_pass(lower) or _has_zero_errors(lower):
            status = STATUS_PASSED
            evidence.append("pass_or_zero_errors")
        elif re.search(r"\b(failed|fail)\b", lower) or (error_count or 0) > 0:
            status = STATUS_FAILED
            evidence.append("failure_keyword_or_errors")

    if status == STATUS_PASSED and warning_count and warning_count > 0:
        status = STATUS_WARNING
        evidence.append("warnings_present")
    return VerificationReportStatus(
        status=status,
        error_count=error_count,
        warning_count=warning_count,
        raw_report_path=str(path),
        error_types=error_types,
        evidence=evidence,
    )


def _has_explicit_pass(text: str) -> bool:
    return bool(re.search(r"\b(passed|pass|clean|success|successful)\b", text)) and not bool(re.search(r"\b(failed|fail)\b", text))


def _has_zero_errors(text: str) -> bool:
    return bool(
        re.search(r"\b0\s+(error|errors|violation|violations|mismatch|mismatches)\b", text)
        or re.search(r"\b(error|errors|violation|violations|mismatch|mismatches)\b\s*[:=]\s*0\b", text)
    )


def _count_for_words(text: str, words: list[str]) -> int | None:
    counts: list[int] = []
    for word in words:
        escaped = re.escape(word)
        patterns = [
            rf"\b{escaped}\b\s*[:=]?\s*(\d+)",
            rf"\b(\d+)\s+{escaped}\b",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                counts.append(int(match.group(1)))
    if counts:
        return max(counts)
    return None


def _error_types(text: str) -> list[str]:
    types = []
    for word in ["width", "space", "overlap", "extension", "angle", "adjacent", "point_touch", "open", "short", "mismatch"]:
        if word in text:
            types.append(word)
    return types
