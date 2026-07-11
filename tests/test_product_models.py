from goa_eval.product.models import CandidateStatus, EvidenceBoundary, new_id


def test_default_candidate_boundary_requires_resimulation():
    boundary = EvidenceBoundary()

    assert boundary.data_source == "real_simulation_csv"
    assert boundary.engineering_validity == "simulation_only"
    assert boundary.must_resimulate is True


def test_new_ids_include_resource_prefix():
    identifier = new_id("project")

    assert identifier.startswith("project_")
    assert len(identifier) > len("project_")


def test_proposal_is_not_confirmed_improvement():
    assert CandidateStatus.PROPOSED != CandidateStatus.CONFIRMED_IMPROVEMENT
