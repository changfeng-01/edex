import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from goa_eval.product.artifact_store import LocalArtifactStore
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.experiment_service import ExperimentService
from goa_eval.product.job_runner import ExecutionCommand, JobExecutionDisabled, ProductJobRunner
from goa_eval.product.models import CandidateStatus, SimulationJobRecord, SimulationJobStatus, new_id
from goa_eval.product.project_service import ProjectService
from goa_eval.product.repositories import SqlAlchemyProductRepository
from goa_eval.product.settings import ProductSettings
from goa_eval.product.simulation_job_service import SimulationJobService


class Registry:
    def __init__(self, adapters):
        self.adapters = adapters

    def get(self, adapter_type):
        try:
            return self.adapters[adapter_type]
        except KeyError as exc:
            raise KeyError(f"unknown simulator adapter: {adapter_type}") from exc


class CommandAdapter:
    def __init__(self, argv, *, on_build=None, output_files=()):
        self.argv = tuple(argv)
        self.on_build = on_build
        self.output_files = tuple(output_files)

    def build_execution(self, job, artifact_store, work_dir):
        del artifact_store
        if self.on_build:
            self.on_build()
        return ExecutionCommand(
            argv=self.argv,
            cwd=work_dir,
            evidence={
                "simulator_mode": "local_fixture",
                "evidence_type": "mock_fixture",
                "physical_validation": False,
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            },
            output_files=self.output_files,
        )


@pytest.fixture
def runner_context(tmp_path):
    repository = SqlAlchemyProductRepository(make_engine(f"sqlite:///{tmp_path / 'product.db'}"))
    create_schema(repository._sessions.kw["bind"])
    store = LocalArtifactStore(tmp_path / "artifacts")
    projects = ProjectService(repository, store)
    workspace = projects.create_workspace("runner team")
    project = projects.create_project(workspace.workspace_id, "GOA", "goa_8k", "spec_v1").project

    def add_job(adapter_type="local_simulator"):
        job = SimulationJobRecord(
            simulation_job_id=new_id("job"),
            project_id=project.project_id,
            candidate_ids=(),
            adapter_type=adapter_type,
            status=SimulationJobStatus.QUEUED,
        )
        repository.add_simulation_job(job)
        return job

    add_job.project_id = project.project_id

    return repository, store, projects, add_job, tmp_path


def _settings(tmp_path, enabled):
    return ProductSettings(
        database_url="sqlite://",
        artifact_root=tmp_path / "artifacts",
        job_execution_enabled=enabled,
    )


def test_execution_is_refused_when_feature_flag_is_disabled(runner_context):
    repository, store, _, add_job, tmp_path = runner_context
    job = add_job()
    adapter = CommandAdapter([sys.executable, "-c", "print('should not run')"])
    runner = ProductJobRunner(repository, store, Registry({"local_simulator": adapter}), _settings(tmp_path, False))

    with pytest.raises(JobExecutionDisabled):
        runner.run_job(job.simulation_job_id)

    assert repository.get_simulation_job(job.simulation_job_id).status == SimulationJobStatus.QUEUED


def test_only_registered_adapters_can_execute(runner_context):
    repository, store, _, add_job, tmp_path = runner_context
    job = add_job("api_supplied_command")
    runner = ProductJobRunner(repository, store, Registry({}), _settings(tmp_path, True))

    with pytest.raises(KeyError, match="unknown simulator adapter"):
        runner.run_job(job.simulation_job_id)

    assert repository.get_simulation_job(job.simulation_job_id).status == SimulationJobStatus.QUEUED


def test_success_stores_stdout_stderr_exit_code_and_mock_evidence(runner_context):
    repository, store, _, add_job, tmp_path = runner_context
    job = add_job()
    fixture_command = (
        "import pandas as pd; "
        "from goa_eval.pia_ca_llso.local_simulator import run_local_fixture_simulator; "
        "batch=pd.DataFrame([{'candidate_id':'fixture','x':1.0}]); "
        "print(run_local_fixture_simulator(batch,{'parameter_columns':['x']},0).to_json(orient='records')); "
        "import sys; print('fixture warning', file=sys.stderr)"
    )
    adapter = CommandAdapter([sys.executable, "-c", fixture_command])
    runner = ProductJobRunner(repository, store, Registry({"local_simulator": adapter}), _settings(tmp_path, True))

    result = runner.run_job(job.simulation_job_id, timeout_seconds=10)

    completed = repository.get_simulation_job(job.simulation_job_id)
    log_ref = store.ref_from_uri(completed.logs_ref)
    log = json.loads(store.resolve(log_ref).read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert completed.status == SimulationJobStatus.WAITING_FOR_RESULTS
    assert completed.attempt == 1
    assert "local_fixture" in log["stdout"]
    assert log["stderr"].strip() == "fixture warning"
    assert log["exit_code"] == 0
    assert log["shell"] is False
    assert log["evidence"] == {
        "simulator_mode": "local_fixture",
        "evidence_type": "mock_fixture",
        "physical_validation": False,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }


def test_timeout_fails_with_dedicated_error_and_persisted_logs(runner_context):
    repository, store, _, add_job, tmp_path = runner_context
    job = add_job()
    adapter = CommandAdapter([sys.executable, "-c", "import time; print('started', flush=True); time.sleep(2)"])
    runner = ProductJobRunner(repository, store, Registry({"local_simulator": adapter}), _settings(tmp_path, True))

    result = runner.run_job(job.simulation_job_id, timeout_seconds=0.05)

    failed = repository.get_simulation_job(job.simulation_job_id)
    log = json.loads(store.resolve(store.ref_from_uri(failed.logs_ref)).read_text(encoding="utf-8"))
    assert result.timed_out is True
    assert failed.status == SimulationJobStatus.FAILED
    assert failed.error_code == "SIMULATION_TIMEOUT"
    assert failed.retryable is True
    assert log["status"] == "timeout"
    assert log["exit_code"] is None


def test_retry_increments_attempt_and_preserves_prior_log(runner_context):
    repository, store, projects, add_job, tmp_path = runner_context
    job = add_job()
    failing = CommandAdapter([sys.executable, "-c", "import sys; print('first failure'); sys.exit(3)"])
    registry = Registry({"local_simulator": failing})
    runner = ProductJobRunner(repository, store, registry, _settings(tmp_path, True))
    first = runner.run_job(job.simulation_job_id)
    first_log_uri = repository.get_simulation_job(job.simulation_job_id).logs_ref

    service = SimulationJobService(repository, store, projects)
    queued = service.retry_execution(job.simulation_job_id)
    registry.adapters["local_simulator"] = CommandAdapter([sys.executable, "-c", "print('second success')"])
    second = runner.run_job(job.simulation_job_id)

    completed = repository.get_simulation_job(job.simulation_job_id)
    assert first.exit_code == 3
    assert queued.status == SimulationJobStatus.QUEUED
    assert second.exit_code == 0
    assert completed.attempt == 2
    assert store.resolve(store.ref_from_uri(first_log_uri)).is_file()
    assert completed.logs_ref != first_log_uri
    assert [
        event.details["attempt"]
        for event in repository.list_audit_events("simulation_job", job.simulation_job_id)
        if event.action == "simulation_job.execution_finished"
    ] == [1, 2]


def test_concurrent_claims_cannot_execute_same_job_twice(runner_context):
    repository, store, _, add_job, tmp_path = runner_context
    job = add_job()
    builds = []
    adapter = CommandAdapter(
        [sys.executable, "-c", "import time; time.sleep(.2); print('done')"],
        on_build=lambda: builds.append(1),
    )
    runner = ProductJobRunner(repository, store, Registry({"local_simulator": adapter}), _settings(tmp_path, True))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: runner.run_job(job.simulation_job_id), range(2)))

    assert len(builds) == 1
    assert sum(result is not None for result in results) == 1
    assert repository.get_simulation_job(job.simulation_job_id).status == SimulationJobStatus.WAITING_FOR_RESULTS


def test_success_persists_declared_simulator_outputs_before_workspace_cleanup(runner_context):
    repository, store, _, add_job, tmp_path = runner_context
    job = add_job()
    command = "from pathlib import Path; Path('results.csv').write_text('candidate_id,score\\na,1\\n'); print('ok')"
    adapter = CommandAdapter(
        [sys.executable, "-c", command],
        output_files=("results.csv",),
    )
    runner = ProductJobRunner(repository, store, Registry({"local_simulator": adapter}), _settings(tmp_path, True))

    runner.run_job(job.simulation_job_id)

    waiting = repository.get_simulation_job(job.simulation_job_id)
    manifest_ref = store.ref_from_uri(waiting.result_manifest_ref)
    manifest = json.loads(store.resolve(manifest_ref).read_text(encoding="utf-8"))
    output_ref = store.ref_from_uri(manifest["outputs"][0]["uri"])
    assert waiting.status == SimulationJobStatus.WAITING_FOR_RESULTS
    assert store.resolve(output_ref).read_text(encoding="utf-8") == "candidate_id,score\na,1\n"
    assert manifest["evidence"]["evidence_type"] == "mock_fixture"


def test_missing_declared_output_fails_closed(runner_context):
    repository, store, _, add_job, tmp_path = runner_context
    job = add_job()
    adapter = CommandAdapter(
        [sys.executable, "-c", "print('no result')"],
        output_files=("missing.csv",),
    )
    runner = ProductJobRunner(repository, store, Registry({"local_simulator": adapter}), _settings(tmp_path, True))

    runner.run_job(job.simulation_job_id)

    failed = repository.get_simulation_job(job.simulation_job_id)
    assert failed.status == SimulationJobStatus.FAILED
    assert failed.error_code == "SIMULATION_OUTPUT_MISSING"


def test_execution_failure_and_retry_keep_candidate_state_in_sync(runner_context):
    repository, store, projects, add_job, tmp_path = runner_context
    baseline = projects.create_design_version(add_job.project_id, "baseline")

    def generator(_config, _maximum, _seed):
        return [{"parameter_changes": {"x": 1.0}}]

    experiments = ExperimentService(repository, generators={"rule": generator})
    experiment = experiments.create_experiment(add_job.project_id, baseline.design_version_id, {})
    candidate = experiments.generate_candidates(experiment.experiment_id, "rule", 1, 1)[0]
    candidate = experiments.approve_candidate(candidate.candidate_id, "reviewer")
    job = add_job()
    repository.update_simulation_job(replace(job, candidate_ids=(candidate.candidate_id,)))
    repository.update_candidate(
        replace(candidate, status=CandidateStatus.SIMULATION_PENDING, simulation_job_id=job.simulation_job_id)
    )
    adapter = CommandAdapter([sys.executable, "-c", "import sys; sys.exit(2)"])
    runner = ProductJobRunner(repository, store, Registry({"local_simulator": adapter}), _settings(tmp_path, True))

    runner.run_job(job.simulation_job_id)
    assert repository.get_candidate(candidate.candidate_id).status == CandidateStatus.SIMULATION_FAILED

    SimulationJobService(repository, store, projects).retry_execution(job.simulation_job_id)
    assert repository.get_candidate(candidate.candidate_id).status == CandidateStatus.SIMULATION_PENDING
