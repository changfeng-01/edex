from dataclasses import dataclass, field
from pathlib import Path

from .device import Device


@dataclass
class SubcktDef:
    name: str
    ports: list[str]
    devices: list[Device] = field(default_factory=list)
    source_file: str | None = None
    line_no: int | None = None


@dataclass
class DesignVersion:
    name: str
    root_dir: Path
    netlist_path: Path | None = None
    mapping_path: Path | None = None
    design_path: Path | None = None
    image_path: Path | None = None
    devices: list[Device] = field(default_factory=list)
    subckts: dict[str, SubcktDef] = field(default_factory=dict)
    mapping: object | None = None
    cascade_chain: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
