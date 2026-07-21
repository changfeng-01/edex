from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .contracts import FidelityLevel


@dataclass(frozen=True)
class PhaseEdge:
    left: str
    right: str
    resistance_ohm: float


@dataclass(frozen=True)
class PhaseNetwork:
    nodes: tuple[str, ...]
    capacitance_f: Mapping[str, float]
    edges: tuple[PhaseEdge, ...]
    fixed_voltages_v: Mapping[str, float]
    initial_voltages_v: Mapping[str, float]


@dataclass(frozen=True)
class PhaseNetworkResult:
    threshold_delay_s: float
    final_voltages_v: dict[str, float]
    time_s: tuple[float, ...]
    trajectory_v: dict[str, tuple[float, ...]]
    fidelity: FidelityLevel


def solve_phase_network(
    network: PhaseNetwork,
    *,
    duration_s: float,
    time_step_s: float,
    threshold_fraction: float = 0.5,
    output_node: str | None = None,
) -> PhaseNetworkResult:
    """Integrate a linear G/C phase network with stable backward Euler."""

    nodes = tuple(network.nodes)
    if not nodes or time_step_s <= 0.0 or duration_s <= 0.0:
        raise ValueError("phase network requires nodes and positive time bounds")
    index = {node: position for position, node in enumerate(nodes)}
    conductance = np.zeros((len(nodes), len(nodes)), dtype=float)
    source = np.zeros(len(nodes), dtype=float)
    for edge in network.edges:
        g = 1.0 / max(float(edge.resistance_ohm), 1.0e-30)
        left_unknown = edge.left in index
        right_unknown = edge.right in index
        if left_unknown:
            i = index[edge.left]
            conductance[i, i] += g
            if right_unknown:
                j = index[edge.right]
                conductance[i, j] -= g
            elif edge.right in network.fixed_voltages_v:
                source[i] += g * float(network.fixed_voltages_v[edge.right])
        if right_unknown:
            j = index[edge.right]
            conductance[j, j] += g
            if left_unknown:
                i = index[edge.left]
                conductance[j, i] -= g
            elif edge.left in network.fixed_voltages_v:
                source[j] += g * float(network.fixed_voltages_v[edge.left])
    capacitance = np.diag([max(float(network.capacitance_f.get(node, 0.0)), 1.0e-30) for node in nodes])
    step_matrix = capacitance / time_step_s + conductance
    state = np.asarray([float(network.initial_voltages_v.get(node, 0.0)) for node in nodes], dtype=float)
    steps = int(np.ceil(duration_s / time_step_s))
    time = [0.0]
    trajectories = {node: [float(state[index[node]])] for node in nodes}
    target_node = output_node or nodes[-1]
    fixed_values = list(float(value) for value in network.fixed_voltages_v.values())
    target_voltage = max(fixed_values) if fixed_values else 1.0
    threshold = float(np.clip(threshold_fraction, 0.0, 1.0)) * target_voltage
    delay = float("inf")
    for step in range(1, steps + 1):
        rhs = capacitance @ state / time_step_s + source
        state = np.linalg.solve(step_matrix, rhs)
        current_time = min(step * time_step_s, duration_s)
        time.append(float(current_time))
        for node in nodes:
            trajectories[node].append(float(state[index[node]]))
        if not np.isfinite(delay) and state[index[target_node]] >= threshold:
            delay = float(current_time)
    return PhaseNetworkResult(
        threshold_delay_s=delay,
        final_voltages_v={node: float(state[index[node]]) for node in nodes},
        time_s=tuple(time),
        trajectory_v={node: tuple(values) for node, values in trajectories.items()},
        fidelity=FidelityLevel.F2_MODEL,
    )
