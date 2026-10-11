from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

import pytest

from jk.errors import StateAccessError
from jk.store.models import StepState
from jk.store.store import RunStore
from tests.seed import SeedStep, seed_run, step


def make_step(job_id: str, *, password: bool = False, destructive: bool = False) -> SeedStep:
    body = {"BRANCH": "snapshot"}
    if password:
        body = {"BRANCH": "snapshot", "ADMIN_PASSWORD": "swordfish"}
    if destructive:
        body = {"CLUSTER": "example-cluster", "NAMESPACE": "example-ns"}
    return step(job_id, body, destructive=destructive)


def make_two_step_run(store: RunStore) -> str:
    return seed_run(store, make_step("create"), make_step("cypress", password=True))


def make_job_run(store: RunStore, job_id: str = "create", *, destructive: bool = False) -> str:
    return seed_run(store, make_step(job_id, destructive=destructive))


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "runs.db"


def test_database_uses_wal(store, db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    mode = connection.execute("pragma journal_mode").fetchone()[0]
    connection.close()

    assert mode == "wal"


def test_database_and_sqlite_sidecars_are_private_with_a_permissive_umask(tmp_path):
    state = tmp_path / ".jk"
    path = state / "runs.db"
    previous_umask = os.umask(0)
    opened = None
    try:
        opened = RunStore.open(path)
        make_two_step_run(opened)
        assert stat.S_IMODE(state.stat().st_mode) == 0o700
        for suffix in ("", "-wal", "-shm"):
            assert stat.S_IMODE(Path(f"{path}{suffix}").stat().st_mode) == 0o600
    finally:
        if opened is not None:
            opened.close()
        os.umask(previous_umask)


def test_open_hardens_existing_files_keeps_data_and_does_not_chmod_the_parent(tmp_path):
    parent = tmp_path / "shared"
    parent.mkdir()
    parent.chmod(0o777)
    path = parent / "runs.db"
    first = RunStore.open(path)
    second = None
    try:
        run_id = make_two_step_run(first)
        for suffix in ("", "-wal", "-shm"):
            Path(f"{path}{suffix}").chmod(0o666)
        second = RunStore.open(path)
        assert second.get_run(run_id).steps[1].job_name == "cypress job"
        assert second.get_step_inputs(run_id, 1)["ADMIN_PASSWORD"] == "swordfish"
        assert stat.S_IMODE(parent.stat().st_mode) == 0o777
        for suffix in ("", "-wal", "-shm"):
            assert stat.S_IMODE(Path(f"{path}{suffix}").stat().st_mode) == 0o600
    finally:
        if second is not None:
            second.close()
        first.close()


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm"])
def test_database_symlinks_are_refused_without_changing_the_target(tmp_path, suffix):
    target = tmp_path / "target"
    target.write_text("keep")
    target.chmod(0o644)
    path = tmp_path / "runs.db"
    Path(f"{path}{suffix}").symlink_to(target)

    with pytest.raises(StateAccessError):
        RunStore.open(path)

    assert target.read_text() == "keep"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_claim_submit_pending_is_atomic_between_connections(tmp_path: Path) -> None:
    path = tmp_path / "runs.db"
    first = RunStore.open(path)
    run_id = make_two_step_run(first)
    second = RunStore.open(path)

    assert first.claim_submit_pending(run_id, 0, next_build_number=10, now=1)
    assert not second.claim_submit_pending(run_id, 0, next_build_number=11, now=2)
    assert first.get_run(run_id).steps[0].state is StepState.SUBMIT_PENDING

    second.close()
    first.close()


def test_claim_stores_the_reconciliation_window_with_the_state(store) -> None:
    run_id = make_job_run(store, "delete", destructive=True)

    assert store.claim_submit_pending(run_id, 0, next_build_number=10, now=123)

    step = store.get_run(run_id).steps[0]
    assert step.state is StepState.SUBMIT_PENDING
    assert step.submitted_at == 123
    assert step.search_from_build_number == 10
    assert step.search_from_timestamp == 123
    assert not store.claim_submit_pending(run_id, 0, next_build_number=11, now=124)


def test_a_pending_submission_is_recovered_without_being_claimed_again(tmp_path: Path) -> None:
    path = tmp_path / "runs.db"
    first = RunStore.open(path)
    run_id = make_job_run(first, "delete", destructive=True)
    assert first.claim_submit_pending(run_id, 0, next_build_number=10, now=123)
    first.close()

    second = RunStore.open(path)
    assert second.recover_pending_submissions() == [run_id]
    assert second.get_run(run_id).steps[0].state is StepState.NEEDS_ATTENTION
    assert not second.claim_submit_pending(run_id, 0, next_build_number=11, now=124)
    second.close()


def test_a_step_saved_as_awaiting_confirmation_opens_as_prepared(db_path: Path) -> None:
    first = RunStore.open(db_path)
    run_id = make_job_run(first, "delete", destructive=True)
    first.connection.execute(
        "UPDATE steps SET state = 'awaiting_confirmation' WHERE run_id = ?", (run_id,)
    )
    first.close()

    reopened = RunStore.open(db_path)
    step = reopened.get_run(run_id).steps[0]
    reopened.close()

    assert step.state is StepState.PREPARED


def test_final_success_marks_the_step_successful(store) -> None:
    run_id = make_job_run(store)
    assert store.claim_submit_pending(run_id, 0, next_build_number=1, now=1)
    store.mark_queued(run_id, 0, queue_url="https://jenkins.invalid/queue/item/1/", note=None)
    store.mark_final(run_id, 0, result="SUCCESS", now=2)

    assert store.get_run(run_id).steps[0].state is StepState.SUCCESS


def test_build_timing_survives_reopen(store, db_path: Path) -> None:
    run_id = make_job_run(store)
    assert store.claim_submit_pending(run_id, 0, next_build_number=1)
    store.mark_queued(run_id, 0, queue_url="https://jenkins.invalid/queue/item/1/", note=None)
    store.mark_running(
        run_id,
        0,
        build_number=1,
        build_url="https://jenkins.invalid/job/1/1/",
        queue_id=1,
    )
    assert store.update_build_timing(
        run_id, 0, started_at_ms=1_000, duration_ms=500, estimated_duration_ms=4_000
    )
    store.close()

    reopened = RunStore.open(db_path)
    step = reopened.get_run(run_id).steps[0]
    reopened.close()

    assert step.build_started_at_ms == 1_000
    assert step.build_duration_ms == 500
    assert step.estimated_duration_ms == 4_000


def _in_flight_first_step(store: RunStore, run_id: str) -> None:
    assert store.claim_submit_pending(run_id, 0, next_build_number=1, now=1)
    store.mark_queued(run_id, 0, queue_url="https://jenkins.invalid/queue/item/1/", note=None)
    store.mark_running(
        run_id,
        0,
        build_number=1,
        build_url="https://jenkins.invalid/job/1/1/",
        queue_id=1,
    )


def test_a_step_finishing_after_a_rejection_keeps_the_rejection(store) -> None:
    """A rejection while an earlier build is still live must stay final.

    The run carries the rejection the moment the later step is rejected; the
    in-flight earlier step may still record its result, but it can never erase
    the rejection.
    """
    run_id = seed_run(store, make_step("create"), make_step("delete", destructive=True))
    _in_flight_first_step(store, run_id)

    assert store.mark_rejected(run_id, 1, message="the job could not be reached")
    assert store.mark_final(run_id, 0, result="SUCCESS", now=5)

    run = store.get_run(run_id)
    assert run.steps[0].state is StepState.SUCCESS
    assert run.steps[1].state is StepState.REJECTED
    assert run.error_kind == "rejected"
    assert run.error_message == "the job could not be reached"


def test_a_later_failure_does_not_rewrite_a_rejected_run_error(store) -> None:
    run_id = seed_run(store, make_step("create"), make_step("delete", destructive=True))
    _in_flight_first_step(store, run_id)
    store.mark_rejected(run_id, 1, message="the job could not be reached")

    assert store.mark_final(run_id, 0, result="FAILURE", now=5)

    run = store.get_run(run_id)
    assert run.error_kind == "rejected"
    assert run.error_message == "the job could not be reached"


def test_late_transition_cannot_overwrite_a_final_state(store) -> None:
    run_id = make_job_run(store)
    assert store.claim_submit_pending(run_id, 0, next_build_number=1)
    assert store.mark_queued(
        run_id, 0, queue_url="https://jenkins.invalid/queue/item/1/", note=None
    )
    assert store.mark_running(
        run_id,
        0,
        build_number=1,
        build_url="https://jenkins.invalid/job/1/1/",
        queue_id=1,
    )
    assert store.mark_final(run_id, 0, result="SUCCESS")

    assert not store.mark_running(
        run_id,
        0,
        build_number=2,
        build_url="https://jenkins.invalid/job/1/2/",
        queue_id=2,
    )
    assert not store.mark_needs_attention(run_id, 0, kind="late", message="late poll")
    assert store.get_run(run_id).steps[0].state is StepState.SUCCESS


def test_state_for_result_maps_known_and_rejects_unknown():
    from jk.store.models import state_for_result

    assert state_for_result("SUCCESS") is StepState.SUCCESS
    assert state_for_result("FAILURE") is StepState.FAILURE
    assert state_for_result("UNSTABLE") is StepState.UNSTABLE
    assert state_for_result("ABORTED") is StepState.ABORTED
    assert state_for_result("NOT_BUILT") is None
