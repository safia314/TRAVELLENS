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
    place_id: str,
    checkin: str,
    checkout: str,
    adults: int = 2,
    wait_ms: int = 30000,
    retries: int = 2,
    headless: bool = True
):
    return run_almosafer(
        city=city,
        place_id=place_id,
        checkin=checkin,
        checkout=checkout,
        adults=adults,
        wait_ms=wait_ms,
        retries=retries,
        headless=headless
    )