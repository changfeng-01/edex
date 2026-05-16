from pathlib import Path
import re

from goa_eval.models.design import DesignVersion
from goa_eval.models.mapping import MappingTable
from goa_eval.parsers.netlist_parser import NetlistParseResult


def build_design_version(
    name: str,
    root_dir: Path,
    parsed: NetlistParseResult,
    mapping: MappingTable | None = None,
) -> DesignVersion:
    design = DesignVersion(
        name=name,
        root_dir=root_dir,
        netlist_path=_first_by_suffix(root_dir, [".netlist", ".sp", ".cir"]),
        mapping_path=_first_by_suffix(root_dir, [".mapping", ".map"]),
        design_path=_first_by_suffix(root_dir, [".design"]),
        image_path=_first_by_suffix(root_dir, [".png"]),
        devices=parsed.devices,
        subckts=parsed.subckts,
        mapping=mapping,
        warnings=parsed.warnings,
    )
    design.cascade_chain = _extract_cascade_chain(design)
    return design


def discover_design_roots(extracted_dir: Path) -> list[Path]:
    if _first_by_suffix(extracted_dir, [".netlist", ".sp", ".cir"]):
        return [extracted_dir]
    return sorted(
        [
            path
            for path in extracted_dir.iterdir()
            if path.is_dir() and (path.name.startswith("v") or _first_by_suffix(path, [".netlist", ".sp", ".cir"]))
        ]
    )


def _first_by_suffix(root: Path, suffixes: list[str]) -> Path | None:
    suffixes_lower = tuple(s.lower() for s in suffixes)
    for path in sorted(root.iterdir()):
        if path.is_file() and path.name.lower().endswith(suffixes_lower):
            return path
    return None


def _extract_cascade_chain(design: DesignVersion) -> list[str]:
    if design.mapping:
        output_nodes = []
        for logical, netlist in design.mapping.node_map.items():
            match = re.fullmatch(r"o(\d+)", logical)
            if match:
                output_nodes.append((int(match.group(1)), netlist))
        if output_nodes:
            return [node for _, node in sorted(output_nodes)]

    instances = [device for device in design.devices if device.kind == "subckt_instance"]
    numbered = []
    for device in instances:
        match = re.fullmatch(r"Xs(\d+)", device.name)
        if match and "output" in device.port_map:
            numbered.append((int(match.group(1)), device.port_map["output"]))
    return [node for _, node in sorted(numbered)]
