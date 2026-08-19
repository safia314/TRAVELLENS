from datetime import date, datetime
from typing import List, Optional, Literal, Any

from pydantic import BaseModel


# Job status
class JobResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    params: Optional[dict] = None
    # Job targets can return anything JSON-serializable — crawl_booking and
    # crawl_almosafer currently return a plain int (hotel count), not a
    # dict — so this stays permissive rather than assuming a shape.
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class JobSubmittedResponse(BaseModel):
    job_id: str
    status: Literal["pending"] = "pending"
    message: str = "Job submitted. Poll GET /jobs/{job_id} for status."


# Cross-site comparison
class HotelListingOut(BaseModel):
    hotel_id: int
    name: str
    website: str
    hotel_url: str
    price: Optional[float] = None
    original_price: Optional[float] = None
    currency: Optional[str] = None
    rating: Optional[float] = None


class HotelMatchOut(BaseModel):
    canonical_name: str
    city: Optional[str] = None
    match_confidence: float
    low_confidence: bool
    listings: List[HotelListingOut]
    cheapest_website: Optional[str] = None
    cheapest_price: Optional[float] = None
    price_spread: Optional[float] = None


class CompareResponse(BaseModel):
    city: str
    check_in: date
    check_out: date
    total_matches: int
    matched_across_sites: int  # matches with 2+ listings
    single_site_only: int      # matches with exactly 1 listing (no cross-site match found)
    results: List[HotelMatchOut]