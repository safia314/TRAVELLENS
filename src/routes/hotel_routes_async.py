from datetime import datetime, date as date_cls

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.app.database import get_db
from src.app.job_queue import submit_job, get_job
from src.services.crawler_service import crawl_booking, crawl_almosafer
from src.services.hotel_matcher import match_hotels
from src.services.city_normalizer import normalize_city
from src.schemas.crawl_requests import (
    BookingCrawlRequest,
    AlmosaferCrawlRequest,
)
from src.schemas.hotel_compare_schema import (
    JobResponse,
    JobSubmittedResponse,
    CompareResponse,
    HotelMatchOut,
    HotelListingOut,
)
from src.services.hotel_matcher import LOW_CONFIDENCE_THRESHOLD

router = APIRouter(prefix="/hotels", tags=["hotels-async"])



# Async crawl submission

@router.post("/crawl/booking/async", response_model=JobSubmittedResponse)
def crawl_booking_async(request: BookingCrawlRequest):
    """Submit a Booking.com crawl as a background job. Returns immediately
    with a job_id — poll GET /jobs/{job_id} for progress/result."""
    job_id = submit_job(
        job_type="booking",
        params=request.dict(),
        target=crawl_booking,
    )
    return JobSubmittedResponse(job_id=job_id)


@router.post("/crawl/almosafer/async", response_model=JobSubmittedResponse)
def crawl_almosafer_async(request: AlmosaferCrawlRequest):
    """Submit an Almosafer crawl as a background job. Returns immediately
    with a job_id — poll GET /jobs/{job_id} for progress/result."""
    job_id = submit_job(
        job_type="almosafer",
        params=request.dict(),
        target=crawl_almosafer,
    )
    return JobSubmittedResponse(job_id=job_id)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job



# Cross-site comparison

@router.get("/compare", response_model=CompareResponse)
def compare_hotels(
    city: str = Query(..., description="City name — either spelling/language works (e.g. 'Jeddah' or 'جدة') as long as it's a known alias in city_normalizer.py"),
    check_in: date_cls = Query(...),
    check_out: date_cls = Query(...),
    db: Session = Depends(get_db),
):
    """
    Cross-site price comparison for already-crawled hotels. Groups hotels
    by fuzzy name match across sites (booking.com vs almosafer) for the
    given city/dates and returns each group with a per-site price listing.

    The `city` value is normalized the same way the crawlers normalize it
    before storing, so passing "Jeddah" or "جدة" here both resolve to
    whatever canonical form got stored — see
    src/services/city_normalizer.py for the alias table.

    This reads from already-crawled data — it doesn't trigger a crawl.
    Run /crawl/booking/async and /crawl/almosafer/async first (or wait for
    both jobs to complete) so there's something to compare.
    """
    canonical_city = normalize_city(city)

    matches = match_hotels(db, city=canonical_city, check_in=check_in, check_out=check_out)

    results = []
    matched_across_sites = 0
    single_site_only = 0

    for m in matches:
        if len(m.listings) >= 2:
            matched_across_sites += 1
        else:
            single_site_only += 1

        cheapest = m.cheapest_listing
        results.append(HotelMatchOut(
            canonical_name=m.canonical_name,
            city=m.city,
            match_confidence=round(m.match_confidence, 3),
            low_confidence=m.match_confidence < LOW_CONFIDENCE_THRESHOLD,
            listings=[HotelListingOut(**l.__dict__) for l in m.listings],
            cheapest_website=cheapest.website if cheapest else None,
            cheapest_price=cheapest.price if cheapest else None,
            price_spread=m.price_spread,
        ))

    return CompareResponse(
        city=canonical_city,
        check_in=check_in,
        check_out=check_out,
        total_matches=len(results),
        matched_across_sites=matched_across_sites,
        single_site_only=single_site_only,
        results=results,
    )