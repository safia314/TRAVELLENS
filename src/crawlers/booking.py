import json
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from src.app.database import SessionLocal
from src.models.hotel import Hotel


import sys
from pathlib import Path

# Add project root directory (TRAVELLENS) to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))


import json
import re
from datetime import datetime, timedelta
# ...
from src.app.database import SessionLocal
from src.models.hotel import Hotel


# ==========================================
# 1. Save / Update Database Function
# ==========================================
def save_hotel_to_db(data: dict):
    """ Save or update hotel data using SQLAlchemy ORM """
    db = SessionLocal()
    try:
        existing_hotel = db.query(Hotel).filter(
            (Hotel.name == data['name']) | (Hotel.hotel_url == data['hotel_url'])
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

def add_dates_to_url(url):
    """ Add search dates to URL to force Booking.com to show prices """
    checkin = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    checkout = (datetime.now() + timedelta(days=16)).strftime("%Y-%m-%d")
    
    if "?" in url:
        return f"{url}&checkin={checkin}&checkout={checkout}&group_adults=2&no_rooms=1"
    return f"{url}?checkin={checkin}&checkout={checkout}&group_adults=2&no_rooms=1"

# ==========================================
# 2. Extract Hotel Data (Scraper)
# ==========================================
def scrape_hotel_page(page, url):
    """ Extract hotel details and map them to the table structure """
    target_url = add_dates_to_url(url)
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
                clean_text = a.split('\n')[0]
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
        '.prco-valign-middle-helper',
        '.bui-price-display__value',
        '.f6431b446d',
        'span[class*="price"]'
    ]
    
    for sel in price_selectors:
        price_elem = soup.select_one(sel)
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            numbers = re.findall(r'[\d\.\,]+', price_text)
            if numbers:
                parsed_price = float(numbers[0].replace(',', ''))
                if parsed_price > 50:
                    price = parsed_price
                    break

    orig_selectors = [
        '.bui-price-display__original',
        '.prco-inline-block-maker-helper',
        'del',
        '[data-testid="item-original-price"]'
    ]
    for sel in orig_selectors:
        orig_elem = soup.select_one(sel)
        if orig_elem:
            orig_text = orig_elem.get_text(strip=True)
            numbers = re.findall(r'[\d\.\,]+', orig_text)
            if numbers:
                original_price = float(numbers[0].replace(',', ''))
                break

    tax_elem = soup.select_one('[data-testid="taxes-and-charges"], .prd-taxes-and-charges-under-price')
    if tax_elem:
        tax_text = tax_elem.get_text(strip=True)
        tax_numbers = re.findall(r'[\d\.\,]+', tax_text)
        if tax_numbers:
            tax_amount = float(tax_numbers[0].replace(',', ''))

    if original_price and price and original_price > price:
        discount_percentage = round(((original_price - price) / original_price) * 100, 2)

    hotel_data = {
        "name": hotel_name,
        "website": "booking.com",
        "hotel_url": url,
        "image_url": image_url,
        "currency": currency,
        "rating": float(rating) if rating else None,
        "reviews": int(reviews) if reviews else None,
        "original_price": original_price,
        "discount_percentage": discount_percentage,
        "price": price,
        "is_tax_included": True,
        "tax_amount": tax_amount,
        "amenities": amenities_str
    }
    
    return hotel_data

# ==========================================
# 3. Get Hotel Links
# ==========================================
def get_hotel_links(page, search_url, max_links=20):
    """ Extract hotel links with page scrolling """
    print(f"[SEARCHING] Searching for hotels in: {search_url}")
    page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)

    hotel_links = []

    for _ in range(5):
        page.evaluate("window.scrollBy(0, 1500)")
        page.wait_for_timeout(1500)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        for link in soup.select('a[href*="/hotel/"]'):
            href = link.get("href")
            if href:
                if href.startswith("/"):
                    href = "https://www.booking.com" + href
                
                parsed = urlparse(href)
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                
                if clean_url not in hotel_links and "/hotel/" in clean_url:
                    hotel_links.append(clean_url)

        if len(hotel_links) >= max_links:
            break

    return hotel_links[:max_links]

# ==========================================
# 4. Main Execution
# ==========================================
if __name__ == "__main__":
    search_url = "https://www.booking.com/searchresults.html?ss=Jeddah"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        links = get_hotel_links(page, search_url, max_links=20)
        print(f"[FOUND] Found {len(links)} hotels.")

        for index, link in enumerate(links, 1):
            print(f"--- Processing hotel ({index}/{len(links)}) ---")
            try:
                data = scrape_hotel_page(page, link)
                save_hotel_to_db(data)
            except Exception as e:
                print(f"[ERROR] Failed to scrape hotel {link}: {e}")

        browser.close()
        print("\n[FINISHED] Process completed successfully!")