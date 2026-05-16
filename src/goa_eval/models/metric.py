from dataclasses import dataclass


@dataclass
class MetricSpec:
    level: str
    name: str
    symbol: str
    target: str
    meaning: str
    method: str
    criterion: str
    metric_type: str
    related_params: str


@dataclass
class MetricResult:
    version_name: str
    metric_name: str
    symbol: str
    object_name: str
    value: float | bool | str | None
    unit: str | None
    passed: bool | None
    metric_type: str
    data_source: str
    engineering_validity: str
    notes: str = ""
