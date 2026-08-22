"""
Normalizes city names to one canonical form so hotels crawled from
different sites — under different languages/spellings of the same city
(e.g. Booking.com's "Jeddah" vs Almosafer's "جدة") — can still be matched
and compared by /hotels/compare, which filters on exact city equality.

This is a maintained alias table for cities this project actually crawls,
not a general-purpose translation system. A city not listed here just
passes through unchanged (stripped) — add it below once you crawl it,
rather than guessing a mapping.
"""

from typing import Dict, Optional, Set

# Canonical name -> known aliases (any language/spelling variant seen in
# practice, lowercase). Extend this as new cities get crawled.
_CITY_ALIASES: Dict[str, Set[str]] = {
    "Jeddah": {"jeddah", "جدة"},
    "Riyadh": {"riyadh", "الرياض"},
    "Dammam": {"dammam", "الدمام"},
    "Makkah": {"mecca", "makkah", "مكة", "مكة المكرمة"},
    "Medina": {"medina", "al madinah", "المدينة", "المدينة المنورة"},
    "Khobar": {"khobar", "al khobar", "الخبر"},
    "Abha": {"abha", "أبها"},
    "Taif": {"taif", "الطائف"},
}

_ALIAS_TO_CANONICAL = {
    alias: canonical
    for canonical, aliases in _CITY_ALIASES.items()
    for alias in aliases
}


def normalize_city(raw: str) -> str:
    """
    Map a raw city string to its canonical form if it's a known alias.
    Unknown cities are returned stripped but otherwise unchanged.
    """
    if not raw:
        return raw

    key = raw.strip().lower()
    return _ALIAS_TO_CANONICAL.get(key, raw.strip())


def detect_city_in_text(text: str) -> Optional[str]:
    """
    Look for a known city name/alias mentioned anywhere inside a longer
    piece of text (e.g. a chat question like "cheapest hotel in Jeddah"),
    as opposed to normalize_city() which expects the city as the whole
    input. Returns the canonical name of the first match, or None.

    Only matches cities already in _CITY_ALIASES — this is a lookup
    against a maintained list, not general place-name extraction, so a
    city crawled but not yet added here won't be detected.
    """
    if not text:
        return None

    lowered = text.lower()
    for alias, canonical in _ALIAS_TO_CANONICAL.items():
        if alias in lowered:
            return canonical
    return None