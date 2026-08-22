from src.crawlers.booking import run_booking
from src.crawlers.almosafer import run_almosafer


def crawl_booking(
    city: str,
    checkin: str,
    checkout: str,
    adults: int = 2,
    rooms: int = 1,
    max_links: int = 20,
    headless: bool = True
):
    """
    Chroma re-indexing now happens inside run_booking() itself, right
    after hotels are saved — so it covers CLI-triggered crawls too, not
    just ones started through this API path. Nothing to do here beyond
    forwarding the call.
    """
    return run_booking(
        city=city,
        checkin=checkin,
        checkout=checkout,
        adults=adults,
        rooms=rooms,
        max_links=max_links,
        headless=headless
    )


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
    automatically from city via get_place_id(). Chroma re-indexing now
    happens inside run_almosafer() itself; see crawl_booking()'s docstring
    for why.
    """
    return run_almosafer(
        city=city,
        checkin=checkin,
        checkout=checkout,
        place_id=place_id,
        adults=adults,
        wait_ms=wait_ms,
        retries=retries,
        headless=headless
    )