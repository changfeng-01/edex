from dataclasses import dataclass, field


@dataclass
class Device:
    name: str
    kind: str
    nodes: list[str]
    model: str | None = None
    params_raw: dict[str, str] = field(default_factory=dict)
    params_si: dict[str, float] = field(default_factory=dict)
    raw_line: str = ""
    source_file: str | None = None
    line_no: int | None = None
    parent_subckt: str | None = None
    port_map: dict[str, str] = field(default_factory=dict)
