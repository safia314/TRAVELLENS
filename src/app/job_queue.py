

import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy.orm import Session

from src.app.database import SessionLocal
from src.models.crawl_job import CrawlJob

# Crawls are Playwright/browser-bound, not CPU-bound — a small pool avoids
# hammering the host with many concurrent Chromium instances. Tune as needed.
MAX_CONCURRENT_JOBS = 2

_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS, thread_name_prefix="crawl-job")

# A job stuck in "running" longer than this is assumed to have died with its
# worker (e.g. process crash) rather than still be legitimately in progress.
STALE_RUNNING_THRESHOLD = timedelta(minutes=30)


def submit_job(job_type: str, params: dict, target: Callable[..., dict]) -> str:
    """
    Create a CrawlJob row (status=pending) and schedule `target(**params)`
    to run in a background thread. Returns the new job id immediately.

    `target` must return a JSON-serializable dict on success and raise on
    failure — the wrapper below handles status transitions either way.
    """
    db = SessionLocal()
    try:
        job = CrawlJob(
            job_type=job_type,
            status="pending",
            params_json=json.dumps(params),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    _executor.submit(_run_job, job_id, target, params)
    return job_id


def _run_job(job_id: str, target: Callable[..., dict], params: dict) -> None:
    db = SessionLocal()
    try:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        if job is None:
            return
        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

    try:
        raw_result = target(**params)
        # crawl_booking/crawl_almosafer currently return a plain int (hotel
        # count); wrap non-dict results so the stored/returned JSON is
        # self-describing (e.g. {"hotels_saved": 703}) instead of a bare
        # number with no label.
        if isinstance(raw_result, dict):
            result = raw_result
        else:
            result = {"hotels_saved": raw_result}
        status = "completed"
        result_json = json.dumps(result)
        error = None
    except Exception as e:
        status = "failed"
        result_json = None
        error = f"{e}\n{traceback.format_exc()}"

    db = SessionLocal()
    try:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        if job is None:
            return
        job.status = status
        job.result_json = result_json
        job.error = error
        job.finished_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def get_job(job_id: str) -> dict:
    """Fetch a job's current state as a plain dict, ready for an API response."""
    db = SessionLocal()
    try:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        if job is None:
            return None

        status = job.status
        # Detect a job that's been "running" long enough it likely died with
        # its worker process, rather than reporting it as still in-progress
        # forever.
        if status == "running" and job.started_at is not None:
            if datetime.utcnow() - job.started_at > STALE_RUNNING_THRESHOLD:
                status = "unknown (possibly stalled — no update in over "
                status += f"{int(STALE_RUNNING_THRESHOLD.total_seconds() // 60)} minutes)"

        return {
            "job_id": job.id,
            "job_type": job.job_type,
            "status": status,
            "params": json.loads(job.params_json) if job.params_json else None,
            "result": json.loads(job.result_json) if job.result_json else None,
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }
    finally:
        db.close()