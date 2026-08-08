import argparse
import sys
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.app.database import SessionLocal
from src.models.hotel import Hotel


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
def save_hotel_to_db(data: dict):
    """Save or update hotel data."""
    db = SessionLocal()
    try:
        existing_hotel = db.query(Hotel).filter(
            Hotel.name == data["name"],
            Hotel.website == data["website"],
            Hotel.check_in == data["check_in"],
            Hotel.check_out == data["check_out"]
        ).first()

        if existing_hotel:
            for key, value in data.items():
                setattr(existing_hotel, key, value)
            print(f"[DB UPDATE] {data['name']}")
        else:
            hotel = Hotel(**data)
            db.add(hotel)
            print(f"[DB INSERT] {data['name']}")

        db.commit()
    except Exception as e:
        db.rollback()
        print("[DB ERROR]", e)
    finally:
        db.close()


# --------------------------------------------------------------------------
# Merge API responses into hotel rows
# --------------------------------------------------------------------------
def merge_hotels(
    price_data: dict,
    summary_data: dict,
    city: str,
    checkin: date,
    checkout: date,
    adults: int
) -> list:
    hotels = []
    summaries = summary_data["hotels"]
    currency = price_data.get("currency", "SAR")

    for result in price_data["searchResults"]:
        hotel_id = str(result["hotelId"])

        if hotel_id not in summaries:
            continue

        info = summaries[hotel_id]
        review = info.get("review") or {}
        facility_ids = info.get("facilityIds") or []
        hotel_name = info["name"]["en"]

        slug = (
            hotel_name.lower()
            .replace("&", "and")
            .replace("'", "")
            .replace(",", "")
            .replace("/", "-")
            .replace(" ", "-")
        )

        hotels.append({
            "name": hotel_name,
            "website": "almosafer",

            "hotel_url": f"https://sa.almosafer.com/en/hotel/details/atg/{slug}-{hotel_id}",
            "image_url": info.get("thumbnailUrl"),
            "city": city,
            "check_in": checkin,
            "check_out": checkout,
            "adults": adults,

            "currency": currency,
            "rating": review.get("score"),
            "reviews": review.get("count"),
            "price": result.get("basePrice"),
            "original_price": result.get("firstPrice"),
            "discount_percentage": result.get("discountPercentage"),

            "is_tax_included": True,
            "tax_amount": result.get("vat", {}).get("outputVat"),
            "amenities": ",".join(map(str, facility_ids)),
        })

    return hotels


# --------------------------------------------------------------------------
# Search URL / date handling
# --------------------------------------------------------------------------
def validate_date_range(checkin: str, checkout: str) -> tuple:
    """Parse and sanity-check YYYY-MM-DD dates from the caller. Raises ValueError on bad input."""
    fmt = "%Y-%m-%d"
    try:
        checkin_d = datetime.strptime(checkin, fmt).date()
        checkout_d = datetime.strptime(checkout, fmt).date()
    except ValueError:
        raise ValueError("Dates must be in YYYY-MM-DD format, e.g. 2026-08-14")

    if checkin_d < date.today():
        raise ValueError(f"checkin ({checkin}) is in the past")
    if checkout_d <= checkin_d:
        raise ValueError(f"checkout ({checkout}) must be after checkin ({checkin})")

    return checkin_d, checkout_d


def build_search_url(city: str, place_id: str, checkin: date, checkout: date, adults: int) -> str:
    """
    Build an Almosafer search URL for the given city/dates/occupancy.
    `city` should be the Arabic (or local) display name Almosafer expects in
    the path, e.g. "جدة" for Jeddah — the same value shown in their own
    search bar. `place_id` comes from Almosafer's place-autocomplete API.
    """
    checkin_str = checkin.strftime("%d-%m-%Y")
    checkout_str = checkout.strftime("%d-%m-%Y")
    query = urlencode({"placeId": place_id, "city": city})

    return (
        f"https://www.almosafer.com/en/hotels/"
        f"{city}/{checkin_str}/{checkout_str}/{adults}_adult"
        f"?{query}"
    )


# --------------------------------------------------------------------------
# Response/request capture
# --------------------------------------------------------------------------
class SearchCapture:
    """Holds the API responses we care about as Playwright intercepts them."""

    def __init__(self):
        self.poll_data = None
        self.summary_data = None
        self.hotel_request = None
        self.saw_any_poll_response = False
        self.failed_status = None

    def reset(self):
        self.poll_data = None
        self.summary_data = None
        self.saw_any_poll_response = False
        self.failed_status = None

    def capture_response(self, response):
        try:
            if "application/json" not in response.headers.get("content-type", ""):
                return

            if "/api/enigma/search/poll/" in response.url:
                data = response.json()
                self.saw_any_poll_response = True
                status = data.get("searchStatus")
                print(f"[POLL] status={status} url={response.url}")
                if status == "COMPLETED_SUCCESSFULLY":
                    self.poll_data = data
                    print("[FOUND] Search Results")
                elif status is not None and status.startswith("COMPLETED_"):
                    # A definitive failure (e.g. COMPLETED_WITH_FAILURE) —
                    # no point continuing to poll this attempt.
                    self.failed_status = status
                return

            if "/api/enigma/v2/content/hotels/summaries" in response.url:
                self.summary_data = response.json()
                print("[FOUND] Hotel Summaries")

        except Exception as e:
            print(f"[DEBUG] capture_response error on {response.url}: {e}")

    def capture_request(self, request):
        if "/api/enigma/v6/packages" in request.url:
            self.hotel_request = {
                "url": request.url,
                "method": request.method,
                "headers": dict(request.headers),
                "body": request.post_data,
            }
            print("\n========== HOTEL REQUEST ==========")
            print(request.post_data)
            print("===================================\n")


# --------------------------------------------------------------------------
# CLI / main
# --------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Scrape Almosafer hotel listings for chosen city/dates.")
    parser.add_argument("--city", required=True, help='City display name as Almosafer expects it, e.g. "جدة"')
    parser.add_argument("--place-id", required=True, help="Almosafer placeId for the city (from their autocomplete API)")
    parser.add_argument("--checkin", required=True, help="Check-in date, YYYY-MM-DD")
    parser.add_argument("--checkout", required=True, help="Check-out date, YYYY-MM-DD")
    parser.add_argument("--adults", type=int, default=2, help="Number of adults (default: 2)")
    parser.add_argument("--wait-ms", type=int, default=30000, help="Max time to wait for search/summary API responses per attempt (default: 30000)")
    parser.add_argument("--retries", type=int, default=2, help="Number of extra attempts if the search fails or times out (default: 2)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser headless (default: True)")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run with a visible browser window (requires a display)")
    return parser.parse_args()


def run_search_attempt(page, capture: SearchCapture, search_url: str, wait_ms: int, reload: bool) -> bool:
    """Run one attempt at loading the search page and waiting for both API
    responses. Returns True on success. Resets capture state on entry so
    retries don't see stale data from a previous attempt."""
    capture.reset()

    if reload:
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
    else:
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

    waited_ms = 0
    step_ms = 1000
    while waited_ms < wait_ms:
        if capture.poll_data is not None and capture.summary_data is not None:
            return True
        if capture.failed_status is not None:
            print(f"[ATTEMPT FAILED] Almosafer's search backend returned {capture.failed_status} "
                  f"after {waited_ms}ms.")
            return False
        page.wait_for_timeout(step_ms)
        waited_ms += step_ms

    if capture.poll_data is None:
        if capture.saw_any_poll_response:
            print(f"[ATTEMPT FAILED] Poll requests were seen but never reached COMPLETED_SUCCESSFULLY "
                  f"within {waited_ms}ms.")
        else:
            print(f"[ATTEMPT FAILED] No search-poll requests were observed at all within {waited_ms}ms — "
                  f"check the URL/placeId/city are valid.")
        return False

    if capture.summary_data is None:
        print(f"[ATTEMPT FAILED] Hotel summaries not found after waiting {waited_ms}ms.")
        return False

    return True


def main():
    args = parse_args()

    try:
        checkin_d, checkout_d = validate_date_range(args.checkin, args.checkout)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    search_url = build_search_url(args.city, args.place_id, checkin_d, checkout_d, args.adults)
    capture = SearchCapture()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        page.on("response", capture.capture_response)
        page.on("request", capture.capture_request)

        print("[OPENING SEARCH PAGE]")
        print(f"[URL] {search_url}")

        try:
            success = False
            total_attempts = args.retries + 1
            for attempt in range(1, total_attempts + 1):
                print(f"\n[ATTEMPT {attempt}/{total_attempts}]")
                success = run_search_attempt(page, capture, search_url, args.wait_ms, reload=(attempt > 1))
                if success:
                    break
                if attempt < total_attempts:
                    print("[RETRYING] Reloading search page...")

            if not success:
                print(f"\n[ERROR] Search failed after {total_attempts} attempt(s). "
                      f"Try opening the URL above manually in a browser to check if it "
                      f"reproduces there, or increase --wait-ms / --retries.")
                sys.exit(1)

            hotels = merge_hotels(
                capture.poll_data,
                capture.summary_data,
                args.city,
                checkin_d,
                checkout_d,
                args.adults
            )
            print(f"\nFound {len(hotels)} hotels\n")

            for i, hotel in enumerate(hotels, start=1):
                save_hotel_to_db(hotel)
                if i % 25 == 0:
                    print(f"Saved {i}/{len(hotels)} hotels...")

            print(f"\nFinished. Total hotels: {len(hotels)}")
        finally:
            browser.close()

def run_almosafer(
    city: str,
    place_id: str,
    checkin: str,
    checkout: str,
    adults: int = 2,
    wait_ms: int = 30000,
    retries: int = 2,
    headless: bool = True
):
    
    """
    Run Almosafer crawler from the API/service layer.
    Returns the number of hotels saved.
    """

    # Validate dates
    checkin_d, checkout_d = validate_date_range(
        checkin,
        checkout
    )

    # Build search URL
    search_url = build_search_url(
        city,
        place_id,
        checkin_d,
        checkout_d,
        adults
    )

    capture = SearchCapture()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        context = browser.new_context(
            viewport={
                "width": 1280,
                "height": 800
            }
        )

        page = context.new_page()

        page.on(
            "response",
            capture.capture_response
        )

        page.on(
            "request",
            capture.capture_request
        )

        try:
            print("[OPENING SEARCH PAGE]")
            print(f"[URL] {search_url}")

            success = False
            total_attempts = retries + 1

            for attempt in range(1, total_attempts + 1):

                print(
                    f"\n[ATTEMPT {attempt}/{total_attempts}]"
                )

                success = run_search_attempt(
                    page,
                    capture,
                    search_url,
                    wait_ms,
                    reload=(attempt > 1)
                )

                if success:
                    break

                if attempt < total_attempts:
                    print(
                        "[RETRYING] Reloading search page..."
                    )

            if not success:
                raise RuntimeError(
                    f"Almosafer search failed after "
                    f"{total_attempts} attempt(s)."
                )

            # Merge API responses into hotel records
            hotels = merge_hotels(
                capture.poll_data,
                capture.summary_data,
                city,
                checkin_d,
                checkout_d,
                adults
            )

            print(
                f"\nFound {len(hotels)} hotels\n"
            )

            # Save hotels to database
            for i, hotel in enumerate(
                hotels,
                start=1
            ):
                save_hotel_to_db(hotel)

                if i % 25 == 0:
                    print(
                        f"Saved {i}/{len(hotels)} hotels..."
                    )

            print(
                f"\nFinished. Total hotels: {len(hotels)}"
            )

            return len(hotels)

        finally:
            browser.close()

if __name__ == "__main__":
    main()