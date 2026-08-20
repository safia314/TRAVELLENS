import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.app.database import SessionLocal
from src.models.hotel import Hotel
from src.crawlers.almosafer_places import get_place_id


# Configuration

# Maximum number of hotels saved/enriched per crawl.
MAX_HOTELS = 100



MAX_AMENITY_WORKERS = 5


# Almosafer amenity category headings.
AMENITY_CATEGORY_NAMES = {
    "Food & drink",
    "General",
    "Front desk services",
    "Beauty & wellness",
    "Accessibility",
    "Family friendly",
    "Pool & beach",
    "Parking & transportation",
}


# Extra information displayed directly below an amenity.
AMENITY_MODIFIERS = {
    "Free",
    "Extra charge",
}


# Database

def save_hotel_to_db(data: dict):
    """Save or update one hotel."""

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

                
                if key == "amenities" and not value:
                    continue

                setattr(existing_hotel, key, value)

            print(
                f"[DB UPDATE] {data['name']}"
            )

        else:

            hotel = Hotel(**data)

            db.add(hotel)

            print(
                f"[DB INSERT] {data['name']}"
            )

        db.commit()

    except Exception as e:

        db.rollback()

        print(
            "[DB ERROR]",
            e
        )

    finally:

        db.close()


# Amenity extraction from hotel detail page

def extract_hotel_amenities(
    page,
    hotel_url: str
) -> list[str]:
    """
    Open an Almosafer hotel detail page and extract detailed,
    human-readable amenities.

    The top summary amenities are ignored.
    Only amenities under the detailed category sections are kept.
    """

    try:

        page.goto(
            hotel_url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        # Give the page a little time for client-side content.
        page.wait_for_timeout(3000)

        body_text = page.locator(
            "body"
        ).inner_text()

        marker = "Amenities for "

        start = body_text.find(
            marker
        )

        if start == -1:

            print(
                f"[AMENITIES] Section not found: "
                f"{hotel_url}"
            )

            return []

       

        category_positions = []

        for category in AMENITY_CATEGORY_NAMES:

            position = body_text.find(
                category,
                start
            )

            if position != -1:

                category_positions.append(
                    position
                )

        if not category_positions:

            print(
                "[AMENITIES] Detailed categories "
                f"not found: {hotel_url}"
            )

            return []

        detailed_start = min(
            category_positions
        )

        # Detailed amenities end before FAQs.

        end = body_text.find(
            "FAQs",
            detailed_start
        )

        if end == -1:

            end = len(body_text)

        section = body_text[
            detailed_start:end
        ]

        # Clean lines.

        lines = [
            line.strip()
            for line in section.splitlines()
            if line.strip()
        ]

        # Extract amenities.

        amenities = []

        for line in lines:

            # Ignore category headings.
            if line in AMENITY_CATEGORY_NAMES:

                continue

            if line in AMENITY_MODIFIERS:

                if amenities:

                    if line not in amenities[-1]:

                        amenities[-1] = (
                            f"{amenities[-1]} "
                            f"({line})"
                        )

                continue

            amenities.append(
                line
            )

        # Remove duplicates while preserving order.

        cleaned = []

        seen = set()

        for amenity in amenities:

            amenity = amenity.strip()

            if not amenity:

                continue

            normalized = amenity.lower()

            if normalized in seen:

                continue

            seen.add(
                normalized
            )

            cleaned.append(
                amenity
            )

        return cleaned

    except Exception as e:

        print(
            f"[AMENITIES ERROR] "
            f"{hotel_url}: {e}"
        )

        return []


# Parallel amenity worker

def _extract_amenities_worker(
    hotel: dict
) -> tuple[str, list[str]]:
    """
    Worker used by ThreadPoolExecutor.

    Each worker creates its own Playwright browser/context/page.
    Playwright objects are never shared between threads.
    """

    hotel_name = hotel["name"]

    hotel_url = hotel["hotel_url"]

    try:

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True
            )

            context = browser.new_context(
                viewport={
                    "width": 1280,
                    "height": 800
                }
            )

            page = context.new_page()

            try:

                amenities = extract_hotel_amenities(
                    page,
                    hotel_url
                )

                return (
                    hotel_name,
                    amenities
                )

            finally:

                browser.close()

    except Exception as e:

        print(
            f"[AMENITIES WORKER ERROR] "
            f"{hotel_name}: {e}"
        )

        return (
            hotel_name,
            []
        )


# Parallel enrichment

def enrich_hotels_with_amenities(
    hotels: list,
    max_workers: int = MAX_AMENITY_WORKERS
) -> None:
    """
    Extract amenities from hotel detail pages in parallel.

    At most max_workers hotel detail pages are processed at the same time.
    """

    if not hotels:

        print(
            "[AMENITIES] No hotels to enrich."
        )

        return

    print(
        f"\n[AMENITIES] Enriching "
        f"{len(hotels)} hotels using "
        f"{max_workers} parallel workers...\n"
    )

    with ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix="amenity-worker"
    ) as executor:

        futures = {
            executor.submit(
                _extract_amenities_worker,
                hotel
            ): hotel

            for hotel in hotels
        }

        completed = 0

        total = len(hotels)

        for future in as_completed(
            futures
        ):

            hotel = futures[future]

            completed += 1

            try:

                hotel_name, amenities = (
                    future.result()
                )

                hotel["amenities"] = (
                    ", ".join(amenities)
                )

                print(
                    f"[AMENITIES] "
                    f"{completed}/{total} "
                    f"{hotel_name} → "
                    f"{len(amenities)} amenities"
                )

            except Exception as e:

                print(
                    f"[AMENITIES ERROR] "
                    f"{hotel['name']}: {e}"
                )

                # Keep empty value so save_hotel_to_db()
                # will not erase existing data.
                hotel["amenities"] = ""


# Merge API responses into hotel rows

def merge_hotels(
    price_data: dict,
    summary_data: dict,
    city: str,
    checkin: date,
    checkout: date,
    adults: int
) -> list:
    """
    Merge Almosafer search-price results and hotel summaries
    into database-ready hotel dictionaries.

    Only the first MAX_HOTELS results are kept.
    """

    hotels = []

    summaries = summary_data["hotels"]

    currency = price_data.get(
        "currency",
        "SAR"
    )

    # Limit the number of hotels processed.
    search_results = price_data[
        "searchResults"
    ][:MAX_HOTELS]

    for result in search_results:

        hotel_id = str(
            result["hotelId"]
        )

        if hotel_id not in summaries:

            continue

        info = summaries[
            hotel_id
        ]

        review = (
            info.get("review")
            or {}
        )

        hotel_name = info[
            "name"
        ]["en"]

        # Build Almosafer hotel slug.
        slug = (
            hotel_name.lower()
            .replace("&", "and")
            .replace("'", "")
            .replace(",", "")
            .replace("/", "-")
            .replace(" ", "-")
        )

        hotel_url = (
            "https://sa.almosafer.com/en/"
            "hotel/details/atg/"
            f"{slug}-{hotel_id}"
        )

        image_url = info.get(
            "thumbnailUrl"
        )

        # Convert HTTP image URLs to HTTPS.
        if (
            image_url
            and image_url.startswith(
                "http://"
            )
        ):

            image_url = image_url.replace(
                "http://",
                "https://",
                1
            )

        hotels.append({

            "name": hotel_name,

            "website": "almosafer",

            "hotel_url": hotel_url,

            "image_url": image_url,

            "city": city,

            "check_in": checkin,

            "check_out": checkout,

            "adults": adults,

            "currency": currency,

            "rating": review.get(
                "score"
            ),

            "reviews": review.get(
                "count"
            ),

            "price": result.get(
                "basePrice"
            ),

            "original_price": result.get(
                "firstPrice"
            ),

            "discount_percentage": result.get(
                "discountPercentage"
            ),

            "is_tax_included": True,

            "tax_amount": (
                result.get("vat", {})
                .get("outputVat")
            ),

            # Populated later by the
            # detail-page amenity extraction.
            "amenities": "",
        })

    return hotels


# Search URL / date handling

def validate_date_range(
    checkin: str,
    checkout: str
) -> tuple:
    """
    Parse and validate YYYY-MM-DD dates.
    """

    fmt = "%Y-%m-%d"

    try:

        checkin_d = datetime.strptime(
            checkin,
            fmt
        ).date()

        checkout_d = datetime.strptime(
            checkout,
            fmt
        ).date()

    except ValueError:

        raise ValueError(
            "Dates must be in YYYY-MM-DD format, "
            "e.g. 2026-08-14"
        )

    if checkin_d < date.today():

        raise ValueError(
            f"checkin ({checkin}) is in the past"
        )

    if checkout_d <= checkin_d:

        raise ValueError(
            f"checkout ({checkout}) must be "
            f"after checkin ({checkin})"
        )

    return (
        checkin_d,
        checkout_d
    )


def build_search_url(
    city: str,
    place_id: str,
    checkin: date,
    checkout: date,
    adults: int
) -> str:
    """
    Build an Almosafer search URL.
    """

    checkin_str = checkin.strftime(
        "%d-%m-%Y"
    )

    checkout_str = checkout.strftime(
        "%d-%m-%Y"
    )

    query = urlencode({
        "placeId": place_id,
        "city": city
    })

    return (
        "https://www.almosafer.com/en/hotels/"
        f"{city}/"
        f"{checkin_str}/"
        f"{checkout_str}/"
        f"{adults}_adult"
        f"?{query}"
    )


# Response / request capture

class SearchCapture:
    """
    Holds the Almosafer API responses we care about.
    """

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

    def capture_response(
        self,
        response
    ):

        try:

            if (
                "application/json"
                not in response.headers.get(
                    "content-type",
                    ""
                )
            ):

                return

            
            # Search polling API.
           

            if (
                "/api/enigma/search/poll/"
                in response.url
            ):

                data = response.json()

                self.saw_any_poll_response = True

                status = data.get(
                    "searchStatus"
                )

                print(
                    f"[POLL] status={status} "
                    f"url={response.url}"
                )

                if (
                    status
                    == "COMPLETED_SUCCESSFULLY"
                ):

                    self.poll_data = data

                    print(
                        "[FOUND] Search Results"
                    )

                elif (
                    status is not None
                    and status.startswith(
                        "COMPLETED_"
                    )
                ):

                    self.failed_status = (
                        status
                    )

                return

            
            # Hotel summaries API.
            

            if (
                "/api/enigma/v2/content/"
                "hotels/summaries"
                in response.url
            ):

                self.summary_data = (
                    response.json()
                )

                print(
                    "[FOUND] Hotel Summaries"
                )

        except Exception as e:

            print(
                f"[DEBUG] capture_response "
                f"error on {response.url}: {e}"
            )

    def capture_request(
        self,
        request
    ):

        if (
            "/api/enigma/v6/packages"
            in request.url
        ):

            self.hotel_request = {

                "url": request.url,

                "method": request.method,

                "headers": dict(
                    request.headers
                ),

                "body": request.post_data,
            }

            print(
                "\n========== HOTEL REQUEST =========="
            )

            print(
                request.post_data
            )

            print(
                "===================================\n"
            )



# CLI


def parse_args():

    parser = argparse.ArgumentParser(
        description=(
            "Scrape Almosafer hotel listings "
            "for a chosen city and dates."
        )
    )

    parser.add_argument(
        "--city",
        required=True,
        help=(
            'City name as Almosafer expects it, '
            'e.g. "جدة"'
        )
    )

    parser.add_argument(
        "--place-id",
        default=None,
        help=(
            "Optional Almosafer placeId. "
            "If omitted, it is resolved automatically."
        )
    )

    parser.add_argument(
        "--checkin",
        required=True,
        help=(
            "Check-in date, YYYY-MM-DD"
        )
    )

    parser.add_argument(
        "--checkout",
        required=True,
        help=(
            "Check-out date, YYYY-MM-DD"
        )
    )

    parser.add_argument(
        "--adults",
        type=int,
        default=2,
        help=(
            "Number of adults "
            "(default: 2)"
        )
    )

    parser.add_argument(
        "--wait-ms",
        type=int,
        default=30000,
        help=(
            "Maximum wait time for "
            "search API responses."
        )
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help=(
            "Number of extra attempts "
            "if search fails."
        )
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help=(
            "Run browser headless."
        )
    )

    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help=(
            "Run with a visible browser."
        )
    )

    return parser.parse_args()



# Search attempt


def run_search_attempt(
    page,
    capture: SearchCapture,
    search_url: str,
    wait_ms: int,
    reload: bool
) -> bool:
    """
    Run one Almosafer search attempt.
    """

    capture.reset()

    page.goto(
        search_url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    waited_ms = 0

    step_ms = 1000

    while waited_ms < wait_ms:

        if (
            capture.poll_data is not None
            and capture.summary_data is not None
        ):

            return True

        if (
            capture.failed_status
            is not None
        ):

            print(
                "[ATTEMPT FAILED] "
                f"Almosafer returned "
                f"{capture.failed_status} "
                f"after {waited_ms}ms."
            )

            return False

        page.wait_for_timeout(
            step_ms
        )

        waited_ms += step_ms

    if capture.poll_data is None:

        if (
            capture.saw_any_poll_response
        ):

            print(
                "[ATTEMPT FAILED] "
                "Poll requests were seen "
                "but never reached "
                "COMPLETED_SUCCESSFULLY "
                f"within {waited_ms}ms."
            )

        else:

            print(
                "[ATTEMPT FAILED] "
                "No search-poll requests "
                "were observed."
            )

        return False

    if capture.summary_data is None:

        print(
            "[ATTEMPT FAILED] "
            "Hotel summaries not found "
            f"after {waited_ms}ms."
        )

        return False

    return True



# Place ID


def _resolve_place_id(
    city: str,
    place_id,
    headless: bool
):
    """
    Use the supplied placeId if available.
    Otherwise resolve it automatically from the city.
    """

    if place_id:

        return place_id

    print(
        f"[PLACE ID] No place_id supplied — "
        f"resolving '{city}' automatically..."
    )

    return get_place_id(
        city,
        headless=headless
    )



# Main CLI entry point


def main():

    args = parse_args()

    
    # Validate dates.
    

    try:

        checkin_d, checkout_d = (
            validate_date_range(
                args.checkin,
                args.checkout
            )
        )

    except ValueError as e:

        print(
            f"[ERROR] {e}"
        )

        sys.exit(1)

    
    # Resolve place ID.
    

    try:

        place_id = _resolve_place_id(
            args.city,
            args.place_id,
            args.headless
        )

    except RuntimeError as e:

        print(
            f"[ERROR] {e}"
        )

        sys.exit(1)

    
    # Build search URL.
    

    search_url = build_search_url(
        args.city,
        place_id,
        checkin_d,
        checkout_d,
        args.adults
    )

    capture = SearchCapture()

    
    # Start Playwright for the search itself.
    

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=args.headless
        )

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

        print(
            "[OPENING SEARCH PAGE]"
        )

        print(
            f"[URL] {search_url}"
        )

        try:

            success = False

            total_attempts = (
                args.retries + 1
            )

            for attempt in range(
                1,
                total_attempts + 1
            ):

                print(
                    f"\n[ATTEMPT "
                    f"{attempt}/{total_attempts}]"
                )

                success = run_search_attempt(
                    page,
                    capture,
                    search_url,
                    args.wait_ms,
                    reload=(
                        attempt > 1
                    )
                )

                if success:

                    break

                if (
                    attempt
                    < total_attempts
                ):

                    print(
                        "[RETRYING] "
                        "Reloading search page..."
                    )

            if not success:

                print(
                    "\n[ERROR] Search failed "
                    f"after {total_attempts} "
                    "attempt(s)."
                )

                sys.exit(1)

            
            # Merge search results.
            # MAX_HOTELS limits this to 100.
            

            hotels = merge_hotels(
                capture.poll_data,
                capture.summary_data,
                args.city,
                checkin_d,
                checkout_d,
                args.adults
            )

            print(
                f"\nFound "
                f"{len(hotels)} hotels\n"
            )

            
            # Extract amenities in parallel.
            #
            # Only 5 detail pages are open at the same time.
            

            enrich_hotels_with_amenities(
                hotels,
                max_workers=MAX_AMENITY_WORKERS
            )

            
            # Save hotels.
            

            for i, hotel in enumerate(
                hotels,
                start=1
            ):

                save_hotel_to_db(
                    hotel
                )

                if i % 25 == 0:

                    print(
                        f"Saved {i}/"
                        f"{len(hotels)} hotels..."
                    )

            print(
                f"\nFinished. "
                f"Total hotels: {len(hotels)}"
            )

        finally:

            browser.close()



# Service-layer entry point


def run_almosafer(
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
    Run Almosafer crawler from the API/service layer.

    Returns the number of hotels saved.
    """

    
    # Validate dates.
    

    checkin_d, checkout_d = (
        validate_date_range(
            checkin,
            checkout
        )
    )

    
    # Resolve place ID automatically if needed.
    

    resolved_place_id = (
        _resolve_place_id(
            city,
            place_id,
            headless
        )
    )

    
    # Build search URL.
    

    search_url = build_search_url(
        city,
        resolved_place_id,
        checkin_d,
        checkout_d,
        adults
    )

    capture = SearchCapture()

    
    # Search browser.
    

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=headless
        )

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

            print(
                "[OPENING SEARCH PAGE]"
            )

            print(
                f"[URL] {search_url}"
            )

            success = False

            total_attempts = (
                retries + 1
            )

            for attempt in range(
                1,
                total_attempts + 1
            ):

                print(
                    f"\n[ATTEMPT "
                    f"{attempt}/{total_attempts}]"
                )

                success = run_search_attempt(
                    page,
                    capture,
                    search_url,
                    wait_ms,
                    reload=(
                        attempt > 1
                    )
                )

                if success:

                    break

                if (
                    attempt
                    < total_attempts
                ):

                    print(
                        "[RETRYING] "
                        "Reloading search page..."
                    )

            if not success:

                raise RuntimeError(
                    "Almosafer search failed "
                    f"after {total_attempts} "
                    "attempt(s)."
                )

            
            # Merge search results.
            

            hotels = merge_hotels(
                capture.poll_data,
                capture.summary_data,
                city,
                checkin_d,
                checkout_d,
                adults
            )

            print(
                f"\nFound "
                f"{len(hotels)} hotels\n"
            )

            
            # Extract amenities using 5 workers.
            

            enrich_hotels_with_amenities(
                hotels,
                max_workers=MAX_AMENITY_WORKERS
            )

            
            # Save hotels.
            

            for i, hotel in enumerate(
                hotels,
                start=1
            ):

                save_hotel_to_db(
                    hotel
                )

                if i % 25 == 0:

                    print(
                        f"Saved {i}/"
                        f"{len(hotels)} hotels..."
                    )

            print(
                f"\nFinished. "
                f"Total hotels: {len(hotels)}"
            )

            return len(hotels)

        finally:

            browser.close()



# Script entry point


if __name__ == "__main__":
    main()