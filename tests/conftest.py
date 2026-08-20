
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.app.base import Base
from src.models.hotel import Hotel          # noqa: F401 — registers table on Base
from src.models.crawl_job import CrawlJob   # noqa: F401 — registers table on Base


@pytest.fixture()
def test_engine(tmp_path):
    """
    Use a temporary SQLite file so background worker threads can use
    separate database connections safely.
    """
    db_path = tmp_path / "test.db"

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(engine)

    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def TestSessionLocal(test_engine):
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )


@pytest.fixture()
def db_session(TestSessionLocal):
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()

