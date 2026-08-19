

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime

# Reuse the project's existing declarative Base (defined in src/app/base.py,
# the same one Hotel uses) so this table is created alongside the others.
from src.app.base import Base


def _new_job_id() -> str:
    return str(uuid.uuid4())


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id = Column(String(36), primary_key=True, default=_new_job_id)

    # "booking" | "almosafer" | "both" | "compare"
    job_type = Column(String(32), nullable=False)

    # "pending" | "running" | "completed" | "failed"
    status = Column(String(16), nullable=False, default="pending")

    # JSON-encoded input params and output result/error, kept as text so no
    # DB-specific JSON column type is required.
    params_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)