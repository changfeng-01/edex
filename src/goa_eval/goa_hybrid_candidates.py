from __future__ import annotations

import math


def candidate_counts(max_candidates: int, mix: dict[str, float]) -> dict[str, int]:
    max_candidates = max(0, int(max_candidates))
    if max_candidates == 0:
        return {"surrogate": 0, "repair": 0, "exploration": 0}
    keys = ["surrogate", "repair", "exploration"]
    counts = {key: int(math.floor(max_candidates * float(mix.get(key, 0.0)))) for key in keys}
    for key in keys:
        if max_candidates >= 3 and counts[key] == 0:
            counts[key] = 1
    while sum(counts.values()) < max_candidates:
        counts["surrogate"] += 1
    while sum(counts.values()) > max_candidates:
        for key in ["exploration", "repair", "surrogate"]:
            if counts[key] > 1:
                counts[key] -= 1
                break
    return counts
