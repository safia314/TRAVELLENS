import json
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs


from playwright.sync_api import sync_playwright

from src.app.database import SessionLocal
from src.models.hotel import Hotel

import sys
from pathlib import Path

# project root
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))


# Save / Update Database

def save_hotel_to_db(data: dict):
    """Save or update hotel data"""

    db = SessionLocal()

    try:
        existing = db.query(Hotel).filter(
            (Hotel.name == data["name"]) |
            (Hotel.hotel_url == data["hotel_url"])
        ).first()

        if existing:

            for key, value in data.items():
                setattr(existing, key, value)

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


def merge_hotels(price_data, summary_data):


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

        # slug 
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

            "currency": currency,

            "rating": review.get("score"),

            "reviews": review.get("count"),

            "price": result.get("basePrice"),

            "original_price": result.get("firstPrice"),

            "discount_percentage": result.get("discountPercentage"),

            "is_tax_included": True,

            "tax_amount": result.get("vat", {}).get("outputVat"),

            "amenities": ",".join(
                map(str, facility_ids)
            )

        })

    return hotels

# Add Dates

def add_dates_to_url(url):

    """
    Rebuild Almosafer URL using dynamic dates
    """

    checkin = (datetime.now() + timedelta(days=14)).strftime("%d-%m-%Y")
    checkout = (datetime.now() + timedelta(days=16)).strftime("%d-%m-%Y")

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    place_id = query.get("placeId", [""])[0]
    city = query.get("city", [""])[0]

    return (
        f"https://www.almosafer.com/en/hotels/"
        f"{city}/{checkin}/{checkout}/2_adult"
        f"?placeId={place_id}&city={city}"
    )


# responses

responses = []

poll_data = None
summary_data = None

hotel_request = None

def capture_response(response):
    global poll_data
    global summary_data

    try:

        if "application/json" not in response.headers.get("content-type", ""):
            return

        data = response.json()

        if (
            "/api/enigma/search/poll/" in response.url
            and data.get("searchStatus") == "COMPLETED_SUCCESSFULLY"
        ):

            poll_data = data
            print("[FOUND] Search Results")

        elif "/api/enigma/v2/content/hotels/summaries" in response.url:

            summary_data = data
            print("[FOUND] Hotel Summaries")

    except Exception:
        pass

def capture_request(request):
    global hotel_request

    if "/api/enigma/v6/packages" in request.url:

        hotel_request = {
            "url": request.url,
            "method": request.method,
            "headers": dict(request.headers),
            "body": request.post_data
        }

        print("\n========== HOTEL REQUEST ==========")
        print(request.post_data)
        print("===================================\n")

# Main

if __name__ == "__main__":

    search_url = (
        "https://www.almosafer.com/en/hotels/"
        "جدة/14-08-2026/15-08-2026/2_adult"
        "?placeId=ChIJWX4TsR_QwxUR2xixN5dXWeA&city=جدة"
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            viewport={"width": 1280, "height": 800}
        )

        page = context.new_page()

        page.on("response", capture_response)
        page.on("request", capture_request)

        print("[OPENING SEARCH PAGE]")

        page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        
        page.wait_for_timeout(15000)

        if poll_data is None:
            print("Search results not found.")
            browser.close()
            exit()

        if summary_data is None:
            print("Hotel summaries not found.")
            browser.close()
            exit()

        hotels = merge_hotels(
            poll_data,
            summary_data
        )

        print(f"\nFound {len(hotels)} hotels\n")
        for i, hotel in enumerate(hotels, start=1):

        

            save_hotel_to_db(hotel)

            if i % 25 == 0:
                print(f"Saved {i}/{len(hotels)} hotels...")

        print(f"\nFinished. Total hotels: {len(hotels)}")


        browser.close()