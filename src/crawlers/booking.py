import argparse
import json
import re
import sys
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlparse, urlencode, urlunparse, parse_qsl

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.app.database import SessionLocal
from src.models.hotel import Hotel
from src.services.city_normalizer import normalize_city


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
def save_hotel_to_db(data: dict):
    """Save or update hotel data using SQLAlchemy ORM."""
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
            print(f"[DB UPDATE] Hotel updated: {data['name']}")
        else:
            new_hotel = Hotel(**data)
            db.add(new_hotel)
            print(f"[DB INSERT] New hotel added: {data['name']}")

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[DB ERROR] Database error: {e}")
    finally:
        db.close()


# --------------------------------------------------------------------------
# URL helpers
# --------------------------------------------------------------------------
def add_dates_to_url(url: str, checkin: str, checkout: str, adults: int, rooms: int) -> str:
    """
    Attach/override the search parameters (checkin, checkout, adults, rooms)
    on a hotel/search URL so Booking.com returns priced results for the
    dates the caller asked for, instead of a hardcoded 14/16-day offset.
    """
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    query.update({
        "checkin": checkin,
        "checkout": checkout,
        "group_adults": str(adults),
        "no_rooms": str(rooms),
    })
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


def validate_date_range(checkin: str, checkout: str):
    """Parse and sanity-check the dates the user supplied. Raises ValueError on bad input."""
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


# --------------------------------------------------------------------------
# Hotel page scraper
# --------------------------------------------------------------------------
def scrape_hotel_page(page, url: str, city: str, checkin: date, checkout: date, adults: int, rooms: int) -> dict:
    """Extract hotel details and map them to the table structure."""
    target_url = add_dates_to_url(url, checkin.isoformat(), checkout.isoformat(), adults, rooms)
    print(f"\n[FETCHING] Scraping hotel from: {url}")

    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

    for offset in [500, 1200, 2000]:
        page.evaluate(f"window.scrollTo(0, {offset})")
        page.wait_for_timeout(800)

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    json_ld_script = soup.find("script", type="application/ld+json")
    ld_data = {}
    if json_ld_script:
        try:
            ld_data = json.loads(json_ld_script.string)
        except Exception:
            pass

    hotel_name = ld_data.get("name")
    if not hotel_name:
        h2 = soup.find("h2", class_="pp-header__title") or soup.find("h2")
        hotel_name = h2.get_text(strip=True) if h2 else "Unknown Hotel"

    rating = None
    reviews = None
    if "aggregateRating" in ld_data:
        rating = ld_data["aggregateRating"].get("ratingValue")
        reviews = ld_data["aggregateRating"].get("reviewCount")

    image_url = ld_data.get("image")
    if not image_url:
        img_tag = soup.select_one(".gallery-side-reviews-wrapper img, [data-testid='gallery-image'] img")
        if img_tag:
            image_url = img_tag.get("src")

    amenities_list = []
    amenity_nodes = soup.select(
        '[data-testid*="facility"], '
        '[data-testid="property-most-popular-facilities"] span, '
        '[data-capla-component*="Facilities"] span, '
        '.hp_desc_important_facilities div, '
        '.important_facility_text, '
        'div.k3_dept_facilities_group li'
    )

    for item in amenity_nodes:
        text = item.get_text(strip=True)
        if text and 2 < len(text) < 45 and text not in amenities_list:
            if not any(word in text for word in ["عرض", "الأسعار", "تقييم", "غرف", "حجز", "اختر", "Show", "Prices", "Review"]):
                amenities_list.append(text)

    if not amenities_list:
        try:
            js_amenities = page.evaluate("""
                () => {
                    const items = document.querySelectorAll('[data-testid*="facility"], [data-capla-component*="Facilities"]');
                    return Array.from(items).map(e => e.innerText.trim()).filter(t => t.length > 2 && t.length < 40);
                }
            """)
            for a in js_amenities:
                clean_text = a.split("\n")[0]
                if clean_text not in amenities_list:
                    amenities_list.append(clean_text)
        except Exception:
            pass

    amenities_str = ", ".join(amenities_list[:15]) if amenities_list else "Basic amenities available"

    price = None
    original_price = None
    discount_percentage = None
    tax_amount = None
    currency = "SAR"

    price_selectors = [
        '[data-testid="price-and-discounted-price"]',
        ".prco-valign-middle-helper",
        ".bui-price-display__value",
        ".f6431b446d",
        'span[class*="price"]',
    ]

    for sel in price_selectors:
        price_elem = soup.select_one(sel)
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            numbers = re.findall(r"[\d\.\,]+", price_text)
            if numbers:
                parsed_price = float(numbers[0].replace(",", ""))
                if parsed_price > 50:
                    price = parsed_price
                    break

    orig_selectors = [
        ".bui-price-display__original",
        ".prco-inline-block-maker-helper",
        "del",
        '[data-testid="item-original-price"]',
    ]
    for sel in orig_selectors:
        orig_elem = soup.select_one(sel)
        if orig_elem:
            orig_text = orig_elem.get_text(strip=True)
            numbers = re.findall(r"[\d\.\,]+", orig_text)
            if numbers:
                original_price = float(numbers[0].replace(",", ""))
                break

    tax_elem = soup.select_one('[data-testid="taxes-and-charges"], .prd-taxes-and-charges-under-price')
    if tax_elem:
        tax_text = tax_elem.get_text(strip=True)
        tax_numbers = re.findall(r"[\d\.\,]+", tax_text)
        if tax_numbers:
            tax_amount = float(tax_numbers[0].replace(",", ""))

    if original_price and price and original_price > price:
        discount_percentage = round(((original_price - price) / original_price) * 100, 2)

    hotel_data = {
        "name": hotel_name,
        "website": "booking.com",
        "hotel_url": url,
        "image_url": image_url,
        # Store the canonical form (e.g. "جدة" -> "Jeddah") so this matches
        # up with Almosafer rows for the same city under a different
        # spelling/language during cross-site comparison.
        "city": normalize_city(city),
        "check_in": checkin,
        "check_out": checkout,
        "adults": adults,
        "currency": currency,
        "rating": float(rating) if rating else None,
        "reviews": int(reviews) if reviews else None,
        "original_price": original_price,
        "discount_percentage": discount_percentage,
        "price": price,
        "is_tax_included": True,
        "tax_amount": tax_amount,
        "amenities": amenities_str,
    }

    return hotel_data


# --------------------------------------------------------------------------
# Search results -> hotel links
# --------------------------------------------------------------------------
def build_search_url(city: str, checkin: str, checkout: str, adults: int, rooms: int) -> str:
    params = {
        "ss": city,
        "checkin": checkin,
        "checkout": checkout,
        "group_adults": adults,
        "no_rooms": rooms,
    }
    return "https://www.booking.com/searchresults.html?" + urlencode(params)


def dismiss_cookie_banner(page):
    """Booking.com's GDPR/cookie banner sits on top of the results and can
    block clicks/rendering until it's dismissed."""
    selectors = [
        '#onetrust-accept-btn-handler',
        'button[data-testid="cookie-banner-accept"]',
        'button[aria-label*="Accept"]',
        'button[aria-label*="accept"]',
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible(timeout=2000):
                btn.click(timeout=2000)
                print(f"[DEBUG] Dismissed cookie banner via {sel}")
                page.wait_for_timeout(500)
                return
        except Exception:
            continue


def dismiss_genius_modal(page):
    """Booking.com shows a 'Sign in, save money' Genius modal over search
    results on many sessions. It doesn't block DOM queries the way a hard
    interstitial would, but closing it keeps screenshots/HTML readable and
    avoids it intercepting later clicks."""
    selectors = [
        'button[aria-label="Dismiss sign-in info."]',
        'button[aria-label="Close"]',
        '[data-testid="modal-close-button"]',
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible(timeout=2000):
                btn.click(timeout=2000)
                print(f"[DEBUG] Dismissed Genius modal via {sel}")
                page.wait_for_timeout(300)
                return
        except Exception:
            continue


def dump_debug_artifacts(page, tag: str = "debug"):
    """Save a screenshot + HTML snapshot so a 0-results run can be inspected
    instead of failing silently. Written to /tmp so it works regardless of
    container filesystem layout."""
    try:
        out_dir = Path("/tmp/booking_debug")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_path = out_dir / f"{tag}_{stamp}.html"
        png_path = out_dir / f"{tag}_{stamp}.png"
        html_path.write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(png_path), full_page=True)
        print(f"[DEBUG] Saved debug artifacts: {html_path}, {png_path}")
    except Exception as e:
        print(f"[DEBUG] Could not save debug artifacts: {e}")


def get_hotel_links(page, search_url: str, max_links: int = 20) -> list:
    print(f"[SEARCHING] Searching for hotels in: {search_url}")

    page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
    dismiss_cookie_banner(page)
    dismiss_genius_modal(page)

    print(f"[DEBUG] Current URL: {page.url}")
    print(f"[DEBUG] Page title: {page.title()}")

    # Wait explicitly for a property card to show up rather than a fixed
    # sleep — if none ever appear, we know within 20s instead of guessing.
    try:
        page.wait_for_selector('[data-testid="property-card"]', timeout=20000)
    except Exception:
        print("[WARN] No property cards appeared within 20s — "
              "Booking.com may be showing a captcha, a 'no results' page, "
              "or a layout the current selectors don't match.")
        dump_debug_artifacts(page, tag="no_cards")

    # Scroll to allow any lazily-loaded results to render
    for _ in range(5):
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(1500)

    cards = page.locator('[data-testid="property-card"]')
    print(f"[DEBUG] Property cards found: {cards.count()}")

    if cards.count() == 0:
        dump_debug_artifacts(page, tag="zero_cards")

    hotel_links = []

    for i in range(min(cards.count(), max_links)):
        card = cards.nth(i)

        link = card.locator('a[data-testid="title-link"]').first
        if link.count() == 0:
            link = card.locator('a[href*="/hotel/"]').first
        if link.count() == 0:
            continue

        href = link.get_attribute("href")
        if not href:
            continue

        if href.startswith("/"):
            href = "https://www.booking.com" + href

        parsed = urlparse(href)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        if clean_url.endswith("/hotel/index.html"):
            continue

        if clean_url not in hotel_links and "/hotel/" in clean_url:
            hotel_links.append(clean_url)

    print(f"[DEBUG] Valid hotel links: {len(hotel_links)}")
    return hotel_links[:max_links]


# --------------------------------------------------------------------------
# CLI / main
# --------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Scrape Booking.com hotel listings for chosen dates.")
    parser.add_argument("--city", default="Jeddah", help="City / search term (default: Jeddah)")
    parser.add_argument("--checkin", required=True, help="Check-in date, YYYY-MM-DD")
    parser.add_argument("--checkout", required=True, help="Check-out date, YYYY-MM-DD")
    parser.add_argument("--adults", type=int, default=2, help="Number of adults (default: 2)")
    parser.add_argument("--rooms", type=int, default=1, help="Number of rooms (default: 1)")
    parser.add_argument("--max-links", type=int, default=20, help="Max hotels to scrape (default: 20)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser headless (default: True)")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run with a visible browser window")
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        checkin_d, checkout_d = validate_date_range(args.checkin, args.checkout)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    count = _run_crawl(
        city=args.city,
        checkin_d=checkin_d,
        checkout_d=checkout_d,
        adults=args.adults,
        rooms=args.rooms,
        max_links=args.max_links,
        headless=args.headless,
    )

    print(f"\n[FINISHED] Process completed successfully! Saved {count} hotels.")


def run_booking(
    city: str,
    checkin: str,
    checkout: str,
    adults: int = 2,
    rooms: int = 1,
    max_links: int = 20,
    headless: bool = True
) -> int:
    """
    Run Booking.com crawler from the API/service layer.
    Returns the number of hotels saved.
    """
    checkin_d, checkout_d = validate_date_range(checkin, checkout)
    return _run_crawl(
        city=city,
        checkin_d=checkin_d,
        checkout_d=checkout_d,
        adults=adults,
        rooms=rooms,
        max_links=max_links,
        headless=headless,
    )


def _run_crawl(city: str, checkin_d: date, checkout_d: date, adults: int, rooms: int, max_links: int, headless: bool) -> int:
    """Shared crawl logic used by both the CLI (main) and run_booking()."""
    search_url = build_search_url(city, checkin_d.isoformat(), checkout_d.isoformat(), adults, rooms)
    saved_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        # Remove the most obvious automation flag. This is standard hygiene
        # for reducing false-positive bot flags on ordinary requests — not a
        # substitute for respecting a site's actual bot-detection/ToS.
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()

        try:
            links = get_hotel_links(page, search_url, max_links=max_links)
            print(f"[FOUND] Found {len(links)} hotels.")

            for index, link in enumerate(links, 1):
                print(f"--- Processing hotel ({index}/{len(links)}) ---")
                try:
                    data = scrape_hotel_page(page, link, city, checkin_d, checkout_d, adults, rooms)
                    save_hotel_to_db(data)
                    saved_count += 1
                except Exception as e:
                    print(f"[ERROR] Failed to scrape hotel {link}: {e}")
        finally:
            browser.close()

    return saved_count


if __name__ == "__main__":
    main()