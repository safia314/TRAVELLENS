from typing import Optional

from pydantic import BaseModel


class BookingCrawlRequest(BaseModel):
    city: str
    checkin: str
    checkout: str
    adults: int = 2
    rooms: int = 1
    max_links: int = 20
    headless: bool = True


class AlmosaferCrawlRequest(BaseModel):
    city: str
    checkin: str
    checkout: str
    place_id: Optional[str] = None  # resolved automatically from city if omitted
    adults: int = 2
    wait_ms: int = 30000
    retries: int = 2
    headless: bool = True