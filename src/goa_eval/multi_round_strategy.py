from __future__ import annotations


CANDIDATE_REPLAY_STRATEGIES = {"hybrid", "genetic", "repair", "hybrid_goa", "physics_guided_hybrid"}
GENETIC_SEARCH_STRATEGIES = {"genetic", "hybrid"}
MODEL_RANKING_STRATEGIES = {"bayesian", "surrogate", "hybrid", "hybrid_goa", "physics_guided_hybrid"}
PHYSICS_PRIOR_STRATEGIES = {"physics_guided_hybrid"}


def uses_candidate_replay(strategy: str) -> bool:
    return strategy in CANDIDATE_REPLAY_STRATEGIES


def uses_genetic_search(strategy: str) -> bool:
    return strategy in GENETIC_SEARCH_STRATEGIES


def uses_model_ranking(strategy: str) -> bool:
    return strategy in MODEL_RANKING_STRATEGIES


def uses_physics_prior(strategy: str) -> bool:
    return strategy in PHYSICS_PRIOR_STRATEGIES
