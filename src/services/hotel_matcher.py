import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Optional, Set

from sqlalchemy.orm import Session

from src.models.hotel import Hotel

# Below this blended score, two hotel names are not considered the same
# hotel at all.
MATCH_THRESHOLD = 0.70
LOW_CONFIDENCE_THRESHOLD = 0.80

_NOISE_WORDS = {
    "hotel",
    "hotels",
    "by",
    "resort",
    "resorts",
    "the",
    "a",
    "an",
    "and",
    "spa",
    "apartments",
    "apartment",
    "serviced",
    "residence",
}

_GENERIC_CITY_WORDS = {
    "riyadh", "jeddah", "dammam", "mecca", "makkah", "medina",
    "الرياض", "جدة", "الدمام", "مكة", "المدينة"
}

_GENERIC_BRAND_WORDS = {
    "marriott", "hilton", "ihg", "hotel", "hotels",
    "resort", "resorts", "by", "the", "and",
}


def _normalize_name(name: str) -> str:
    if not name:
        return ""

    name = unicodedata.normalize("NFKD", name)
    name = "".join(
        c for c in name
        if not unicodedata.combining(c)
    )

    name = name.lower()
    name = re.sub(r"[^\w\s]", " ", name)

    tokens = [
        token
        for token in name.split()
        if token not in _NOISE_WORDS
    ]

    return " ".join(tokens)


def _meaningful_tokens(name: str) -> Set[str]:
    normalized = _normalize_name(name)

    return {
        token
        for token in normalized.split()
        if token not in _GENERIC_CITY_WORDS
        and token not in _GENERIC_BRAND_WORDS
    }


def _token_jaccard(tokens_a: Set[str], tokens_b: Set[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union) if union else 0.0


def _similarity(name_a: str, name_b: str) -> float:
    normalized_a = _normalize_name(name_a)
    normalized_b = _normalize_name(name_b)

    seq_ratio = SequenceMatcher(
        None,
        normalized_a,
        normalized_b
    ).ratio()

    tokens_a = _meaningful_tokens(name_a)
    tokens_b = _meaningful_tokens(name_b)

    # If there are no meaningful tokens to compare, we cannot
    # confidently identify the hotels from character similarity alone.
    if not tokens_a or not tokens_b:
        return 0.0

    jaccard = _token_jaccard(tokens_a, tokens_b)

    # No meaningful words in common -> definitely different hotels.
    if jaccard == 0.0:
        return 0.0

    return (seq_ratio + jaccard) / 2

    


@dataclass
class HotelListing:
    hotel_id: int
    name: str
    website: str
    hotel_url: str
    price: Optional[float]
    original_price: Optional[float]
    currency: Optional[str]
    rating: Optional[float]


@dataclass
class HotelMatch:
    canonical_name: str
    city: Optional[str]
    listings: List[HotelListing]
    match_confidence: float  # lowest pairwise similarity within the group; 1.0 for a single-listing group

    @property
    def cheapest_listing(self) -> Optional[HotelListing]:
        priced = [l for l in self.listings if l.price is not None]
        return min(priced, key=lambda l: l.price) if priced else None

    @property
    def price_spread(self) -> Optional[float]:
        priced = [l.price for l in self.listings if l.price is not None]
        return (max(priced) - min(priced)) if len(priced) >= 2 else None


def _hotel_to_listing(hotel: Hotel) -> HotelListing:
    return HotelListing(
        hotel_id=hotel.id,
        name=hotel.name,
        website=hotel.website,
        hotel_url=hotel.hotel_url,
        price=hotel.price,
        original_price=hotel.original_price,
        currency=hotel.currency,
        rating=hotel.rating,
    )


def match_hotels(
    db: Session,
    city: str,
    check_in,
    check_out,
) -> List[HotelMatch]:
    """
    Fetch all crawled hotels for the given city/dates and group them into
    cross-site matches by fuzzy name similarity.

    Matching strategy: greedy nearest-neighbor. For each hotel not yet
    assigned to a group, compare it against every other ungrouped hotel;
    join the single best match above MATCH_THRESHOLD, if any. This is O(n^2)
    in the number of hotels for one city/date combo, which is fine at the
    scale a city search returns (tens to low hundreds), but would need a
    smarter approach (blocking/indexing) at much larger scale.
    """
    hotels = (
        db.query(Hotel)
        .filter(Hotel.city == city, Hotel.check_in == check_in, Hotel.check_out == check_out)
        .all()
    )

    remaining = list(hotels)
    matches: List[HotelMatch] = []

    while remaining:
        anchor = remaining.pop(0)
        group = [anchor]
        best_pairwise_scores = []

        still_remaining = []
        for candidate in remaining:
            # A match can contain only one listing from each website.
            if candidate.website in {hotel.website for hotel in group}:
                still_remaining.append(candidate)
                continue

            score = _similarity(anchor.name, candidate.name)

            if score >= MATCH_THRESHOLD:
                group.append(candidate)
                best_pairwise_scores.append(score)
            else:
                still_remaining.append(candidate)

        remaining = still_remaining

        confidence = min(best_pairwise_scores) if best_pairwise_scores else 1.0
        matches.append(HotelMatch(
            canonical_name=anchor.name,
            city=city,
            listings=[_hotel_to_listing(h) for h in group],
            match_confidence=confidence,
        ))

    return matches