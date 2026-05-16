from dataclasses import dataclass


@dataclass
class MappingRecord:
    library: str
    cell: str
    record_kind: str
    logical_name: str
    netlist_name: str
    raw_line: str
    line_no: int


@dataclass
class MappingTable:
    records: list[MappingRecord]
    cell_map: dict[str, str]
    instance_map: dict[str, str]
    node_map: dict[str, str]
    port_map: dict[str, int]
