from pathlib import Path
import re

from bs4 import BeautifulSoup

from goa_eval.models.metric import MetricSpec


EXPECTED_HEADERS = ["层级", "指标", "符号", "观察对象", "物理意义", "提取方法", "初始判据", "类型", "关联参数"]


def parse_metric_table(path: Path) -> list[MetricSpec]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "lxml")
    table = soup.find("table")
    if table is None:
        return []
    rows = []
    for tr in table.find_all("tr"):
        cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    if not rows:
        return []
    header = rows[0]
    specs: list[MetricSpec] = []
    for row in rows[1:]:
        padded = (row + [""] * len(EXPECTED_HEADERS))[: len(EXPECTED_HEADERS)]
        data = dict(zip(header, padded))
        specs.append(
            MetricSpec(
                level=data.get("层级", ""),
                name=data.get("指标", ""),
                symbol=_normalize_symbol(data.get("符号", "")),
                target=data.get("观察对象", ""),
                meaning=data.get("物理意义", ""),
                method=data.get("提取方法", ""),
                criterion=data.get("初始判据", ""),
                metric_type=data.get("类型", ""),
                related_params=data.get("关联参数", ""),
            )
        )
    return specs


def _clean_text(text: str) -> str:
    text = text.replace("\u200b", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_symbol(text: str) -> str:
    return text.replace(" ", "")
