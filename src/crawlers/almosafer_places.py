"""
Resolves an Almosafer `placeId` for a given city name.

Almosafer doesn't publish a documented public places/autocomplete API, so
this drives their own destination search box with Playwright and captures
whatever autocomplete network response it fires — the same technique the
main crawler uses to capture search-poll results.

Because the exact endpoint path and input selector aren't publicly
documented, this tries a handful of likely candidates. If Almosafer's
markup doesn't match any of them, it fails loudly with the URLs it *did*
see, so the candidate lists below can be extended rather than debugged
blind.
"""

import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

# Substrings that a places/autocomplete API URL is likely to contain.
AUTOCOMPLETE_URL_HINTS = [
    "autocomplete",
    "places/search",
    "places?",
    "/places/",
    "location/search",
    "suggest",
]

# Candidate selectors for the destination search input on the hotels page.
# The first entry is the confirmed real one (found via the debug input
# inventory); the rest are kept as fallbacks in case Almosafer changes it.
DESTINATION_INPUT_SELECTORS = [
    '#DesktopSearchWidget_Destination_InputField_Test_Id',
    'input[placeholder*="Search for properties"]',
    'input[placeholder*="Where"]',
    'input[data-testid*="destination"]',
    'input[data-testid*="location"]',
    'input[name="destination"]',
]

# A Google-style placeId looks like "ChIJ..." — used to help pick the right
# field out of an unfamiliar JSON shape.
PLACE_ID_PATTERN = re.compile(r"^ChIJ[\w-]+$")


class _PlaceCapture:
    def __init__(self):
        self.responses = []  # list of (url, json_data)

    def capture_response(self, response):
        try:
            if "application/json" not in response.headers.get("content-type", ""):
                return
            url = response.url
            if any(hint in url.lower() for hint in AUTOCOMPLETE_URL_HINTS):
                data = response.json()
                self.responses.append((url, data))
                print(f"[PLACES DEBUG] Captured candidate response: {url}")
        except Exception:
            pass


def _dump_debug_artifacts(page, tag: str = "places_debug"):
    """Save a screenshot + HTML snapshot to /tmp so a selector-mismatch
    failure can actually be inspected instead of guessed at again."""
    try:
        out_dir = Path("/tmp/almosafer_debug")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_path = out_dir / f"{tag}_{stamp}.html"
        png_path = out_dir / f"{tag}_{stamp}.png"
        html_path.write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(png_path), full_page=True)
        print(f"[PLACES DEBUG] Saved debug artifacts: {html_path}, {png_path}")
    except Exception as e:
        print(f"[PLACES DEBUG] Could not save debug artifacts: {e}")


def _list_visible_inputs(page):
    """Inventory every visible <input> on the page — name, id, placeholder,
    type, data-testid — so the real destination field can be identified
    when none of the guessed selectors match."""
    try:
        inputs = page.evaluate("""
            () => Array.from(document.querySelectorAll('input')).map(el => ({
                name: el.name,
                id: el.id,
                placeholder: el.placeholder,
                type: el.type,
                testid: el.getAttribute('data-testid'),
                visible: el.offsetParent !== null,
            }))
        """)
        print("[PLACES DEBUG] Inputs found on page:")
        for inp in inputs:
            print(f"  {inp}")
        return inputs
    except Exception as e:
        print(f"[PLACES DEBUG] Could not inventory inputs: {e}")
        return []


def _find_place_id_candidates(obj, out: list):
    """Walk an arbitrary JSON structure and collect dicts that look like
    place entries (i.e. contain a ChIJ-style placeId)."""
    if isinstance(obj, dict):
        for key in ("placeId", "place_id", "id"):
            value = obj.get(key)
            if isinstance(value, str) and PLACE_ID_PATTERN.match(value):
                out.append(obj)
                break
        for v in obj.values():
            _find_place_id_candidates(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _find_place_id_candidates(item, out)


def _pick_best_match(candidates: list, city: str):
    """Prefer a candidate whose display name contains the requested city
    text; fall back to the first candidate found."""

    def display_name(c):
        for key in ("name", "displayName", "title", "description"):
            val = c.get(key)
            if isinstance(val, str):
                return val
            if isinstance(val, dict):
                return val.get("en") or val.get("ar") or ""
        return ""

    for c in candidates:
        if city in display_name(c):
            for key in ("placeId", "place_id", "id"):
                if key in c:
                    return c[key], display_name(c)

    c = candidates[0]
    for key in ("placeId", "place_id", "id"):
        if key in c:
            return c[key], display_name(c)
    return None, None


def get_place_id(city: str, headless: bool = True, wait_ms: int = 6000) -> str:
    """
    Resolve an Almosafer placeId for `city` by typing it into their
    destination search box and capturing the autocomplete response.

    Raises RuntimeError with diagnostic detail if the input field or the
    autocomplete response can't be found, so failures are debuggable
    instead of silent.
    """
    capture = _PlaceCapture()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.on("response", capture.capture_response)

        page.goto("https://www.almosafer.com/en", wait_until="domcontentloaded", timeout=60000)

        # The destination search box lives under the "Stays" tab, not on a
        # dedicated /hotels URL (that path 404s) — click it first.
        stays_selectors = [
            'text="Stays"',
            'a:has-text("Stays")',
            'button:has-text("Stays")',
        ]
        for sel in stays_selectors:
            try:
                tab = page.locator(sel).first
                if tab.count() > 0 and tab.is_visible(timeout=2000):
                    tab.click(timeout=3000)
                    page.wait_for_timeout(1000)
                    break
            except Exception:
                continue

        typed = False
        used_selector = None
        for sel in DESTINATION_INPUT_SELECTORS:
            try:
                field = page.locator(sel).first
                if field.count() > 0 and field.is_visible(timeout=2000):
                    field.click(timeout=3000)
                    field.fill("")
                    field.type(city, delay=80)
                    typed = True
                    used_selector = sel
                    break
            except Exception:
                continue

        if not typed:
            _list_visible_inputs(page)
            _dump_debug_artifacts(page, tag="no_input_found")
            browser.close()
            raise RuntimeError(
                "Could not find Almosafer's destination search input with any known selector "
                f"({DESTINATION_INPUT_SELECTORS}). Their markup may have changed — see the "
                "[PLACES DEBUG] input inventory above, and check the saved screenshot/HTML "
                "in /tmp/almosafer_debug/ for the real field."
            )

        print(f"[PLACES DEBUG] Typed '{city}' into {used_selector}, waiting for autocomplete...")
        page.wait_for_timeout(wait_ms)

        if not capture.responses:
            _dump_debug_artifacts(page, tag="no_autocomplete_response")

        browser.close()

    if not capture.responses:
        raise RuntimeError(
            f"No autocomplete-looking API responses were observed while typing '{city}'. "
            f"Checked URLs containing any of: {AUTOCOMPLETE_URL_HINTS}. "
            "Almosafer's endpoint naming may not match these hints — capture network traffic "
            "manually (like the [POLL]/[RESPONSE] logging in the main crawler) to find the real one."
        )

    for url, data in capture.responses:
        candidates = []
        _find_place_id_candidates(data, candidates)
        if candidates:
            place_id, matched_name = _pick_best_match(candidates, city)
            if place_id:
                print(f"[PLACE ID] Resolved '{city}' -> {place_id} (matched \"{matched_name}\", from {url})")
                return place_id

    raise RuntimeError(
        f"Captured {len(capture.responses)} candidate response(s) but couldn't extract a "
        f"placeId for '{city}' from any of them. Response shape may differ from what this "
        "function expects — inspect the captured URLs above."
    )