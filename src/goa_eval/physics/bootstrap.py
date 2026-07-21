from __future__ import annotations

from .contracts import BootstrapEvaluation, BootstrapNetwork, FidelityLevel


def conserve_bootstrap_charge(
    network: BootstrapNetwork,
    *,
    target_threshold_v: float,
    polarity: str,
) -> BootstrapEvaluation:
    """Solve the ideal charge-conservation bootstrap step.

    The loss term is charge, not an invented voltage penalty. The reported
    headroom belongs to the target device, rather than the bootstrap switch.
    """

    capacitances = (
        max(network.boot_capacitance_f, 0.0),
        max(network.target_gate_capacitance_f, 0.0),
        max(network.output_load_capacitance_f, 0.0),
        max(network.parasitic_loss_capacitance_f, 0.0),
    )
    total_capacitance = sum(capacitances)
    injected_charge = capacitances[0] * network.clock_step_v - max(network.leakage_charge_c, 0.0)
    boost = injected_charge / total_capacitance if total_capacitance > 0.0 else 0.0
    boosted_gate = network.initial_gate_v + boost
    sign = -1.0 if polarity.lower().startswith("p") else 1.0
    headroom = sign * boosted_gate - sign * target_threshold_v
    residual = injected_charge - total_capacitance * boost
    return BootstrapEvaluation(
        coupling_factor=capacitances[0] / total_capacitance if total_capacitance > 0.0 else 0.0,
        gate_boost_v=float(boost),
        boosted_gate_v=float(boosted_gate),
        target_headroom_v=float(headroom),
        charge_residual_c=float(residual),
        fidelity=FidelityLevel.F1_ANALYTIC,
    )
