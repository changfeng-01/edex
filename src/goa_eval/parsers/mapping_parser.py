from pathlib import Path

from goa_eval.models.mapping import MappingRecord, MappingTable


def parse_mapping(path: Path) -> MappingTable:
    records: list[MappingRecord] = []
    cell_map: dict[str, str] = {}
    instance_map: dict[str, str] = {}
    node_map: dict[str, str] = {}
    port_map: dict[str, int] = {}

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        tokens = stripped.split()
        if len(tokens) < 5:
            continue
        record = MappingRecord(tokens[0], tokens[1], tokens[2], tokens[3], tokens[4], raw_line, line_no)
        records.append(record)
        kind = record.record_kind.upper()
        if kind == "C":
            cell_map[record.cell] = record.netlist_name
        elif kind == "I":
            instance_map[record.logical_name] = record.netlist_name
        elif kind == "N":
            node_map[record.logical_name] = record.netlist_name
        elif kind == "P":
            try:
                port_map[record.logical_name] = int(record.netlist_name)
            except ValueError:
                pass

    return MappingTable(records, cell_map, instance_map, node_map, port_map)
