import time

import pytest

from src.app import job_queue as job_queue_module


@pytest.fixture(autouse=True)
def patch_session_local(monkeypatch, TestSessionLocal):
    """Point job_queue's module-level SessionLocal at the in-memory test DB
    instead of the real MySQL connection, for every test in this file."""
    monkeypatch.setattr(job_queue_module, "SessionLocal", TestSessionLocal)


def _wait_for_terminal(job_id, timeout=5):
    """Jobs run in a background thread — poll instead of assuming
    synchronous completion."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = job_queue_module.get_job(job_id)
        if job is not None and job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.05)
    raise TimeoutError(f"Job {job_id} did not reach a terminal state within {timeout}s")


def test_submit_job_dict_result_completes():
    def target(a):
        return {"value": a * 2}

    job_id = job_queue_module.submit_job("test", {"a": 4}, target)
    job = _wait_for_terminal(job_id)

    assert job["status"] == "completed"
    assert job["result"] == {"value": 8}
    assert job["error"] is None
    assert job["started_at"] is not None
    assert job["finished_at"] is not None


def test_submit_job_nondict_result_gets_wrapped():
    # crawl_booking/crawl_almosafer return a plain int (hotel count) — the
    # queue should normalize that into a labeled dict rather than storing
    # a bare number.
    def target():
        return 703

    job_id = job_queue_module.submit_job("test", {}, target)
    job = _wait_for_terminal(job_id)

    assert job["status"] == "completed"
    assert job["result"] == {"hotels_saved": 703}


def test_submit_job_failure_is_captured_not_raised():
    def target():
        raise ValueError("boom")

    job_id = job_queue_module.submit_job("test", {}, target)
    job = _wait_for_terminal(job_id)

    assert job["status"] == "failed"
    assert job["result"] is None
    assert "boom" in job["error"]


def test_get_job_returns_none_for_unknown_id():
    assert job_queue_module.get_job("does-not-exist") is None


def test_job_params_round_trip_through_json():
    def target(city, adults):
        return {"city": city, "adults": adults}

    job_id = job_queue_module.submit_job("test", {"city": "Riyadh", "adults": 2}, target)
    job = _wait_for_terminal(job_id)

    assert job["params"] == {"city": "Riyadh", "adults": 2}
    assert job["result"] == {"city": "Riyadh", "adults": 2}
