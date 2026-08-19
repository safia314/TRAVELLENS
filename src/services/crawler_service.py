from src.crawlers.booking import run_booking
from src.crawlers.almosafer import run_almosafer
from src.vector_store import index_hotels
from src.app.database import SessionLocal


def crawl_booking(
    city: str,
    checkin: str,
    checkout: str,
    adults: int = 2,
    rooms: int = 1,
    max_links: int = 20,
    headless: bool = True
):

    count = run_booking(
        city=city,
        checkin=checkin,
        checkout=checkout,
        adults=adults,
        rooms=rooms,
        max_links=max_links,
        headless=headless
    )

    # Index MySQL hotels into ChromaDB
    db = SessionLocal()

    try:
        indexed_count = index_hotels(db)
        print(f"[CHROMA] Indexed {indexed_count} hotels")
    finally:
        db.close()

    return count


def crawl_almosafer(
    city: str,
    checkin: str,
    checkout: str,
    place_id: str = None,
    adults: int = 2,
    wait_ms: int = 30000,
    retries: int = 2,
    headless: bool = True
):
    """
    place_id is optional — if omitted, run_almosafer resolves it
    automatically from city via get_place_id().
    """

    count = run_almosafer(
        city=city,
        checkin=checkin,
        checkout=checkout,
        place_id=place_id,
        adults=adults,
        wait_ms=wait_ms,
        retries=retries,
        headless=headless
    )

    db = SessionLocal()

    try:
        indexed_count = index_hotels(db)
        print(f"[CHROMA] Indexed {indexed_count} hotels")
    finally:
        db.close()

    return count