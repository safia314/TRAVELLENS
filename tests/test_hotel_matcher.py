from datetime import date

from src.services.hotel_matcher import _normalize_name, _similarity, match_hotels, MATCH_THRESHOLD
from src.models.hotel import Hotel


def test_normalize_strips_noise_words_and_punctuation():
    assert _normalize_name("The Grand Hotel & Spa") == "grand"


def test_normalize_handles_empty_and_none():
    assert _normalize_name("") == ""
    assert _normalize_name(None) == ""


def test_similarity_exact_match_scores_one():
    assert _similarity("voco Riyadh by IHG", "voco Riyadh by IHG") == 1.0


def test_similarity_typo_still_matches_above_threshold():
    # Real case seen in production data: Almosafer says "Al Malaz",
    # Booking's scrape says "AI Malaz" (capital I for lowercase l).
    score = _similarity(
        "Holiday Inn Riyadh Al Malaz by IHG",
        "Holiday Inn Riyadh AI Malaz by IHG",
    )
    assert score >= MATCH_THRESHOLD


def test_similarity_rejects_different_branches_of_same_brand():
    # Regression test: these are two different branches of the same chain
    # (Jaber vs Al Olaya). A pure character-ratio would score ~0.72 here
    # (shared "Royal Palace Hotel" prefix), wrongly treating them as the
    # same hotel. Token-Jaccard blending should push this below threshold.
    score = _similarity(
        "Royal Palace Hotel - Jaber",
        "Royal Palace Hotel - Al Olaya",
    )
    assert score < MATCH_THRESHOLD


def test_similarity_no_shared_tokens_scores_zero():
    score = _similarity("Hilton Riyadh", "Sheraton Jeddah")
    assert score == 0.0


def _make_hotel(db_session, **kwargs):
    defaults = dict(
        website="booking.com",
        hotel_url="https://example.com/hotel",
        city="Riyadh",
        check_in=date(2026, 9, 2),
        check_out=date(2026, 9, 3),
        adults=2,
        currency="SAR",
        price=100.0,
    )
    defaults.update(kwargs)
    hotel = Hotel(**defaults)
    db_session.add(hotel)
    db_session.commit()
    db_session.refresh(hotel)
    return hotel


def test_match_hotels_groups_exact_name_across_sites_but_not_same_site(db_session):
    _make_hotel(db_session, name="Courtyard by Marriott Riyadh Olaya", website="almosafer", price=1119.36)
    _make_hotel(db_session, name="Courtyard by Marriott Riyadh Olaya", website="booking.com", price=1030.0)
    # Same-site duplicate — should NOT merge with the pair above.
    _make_hotel(db_session, name="Courtyard by Marriott Riyadh Olaya", website="booking.com", price=1050.0)

    matches = match_hotels(db_session, city="Riyadh", check_in=date(2026, 9, 2), check_out=date(2026, 9, 3))

    cross_site = [m for m in matches if len(m.listings) >= 2]
    assert len(cross_site) == 1
    assert len(cross_site[0].listings) == 2  # not 3 — same-site dupes don't join a group
    websites = {l.website for l in cross_site[0].listings}
    assert websites == {"almosafer", "booking.com"}


def test_match_hotels_keeps_different_branches_separate(db_session):
    _make_hotel(db_session, name="Royal Palace Hotel - Jaber", website="almosafer", price=324.87)
    _make_hotel(db_session, name="Royal Palace Hotel - Al Olaya", website="booking.com", price=322.0)

    matches = match_hotels(db_session, city="Riyadh", check_in=date(2026, 9, 2), check_out=date(2026, 9, 3))

    assert len(matches) == 2
    assert all(len(m.listings) == 1 for m in matches)


def test_match_confidence_is_one_for_single_listing_group(db_session):
    _make_hotel(db_session, name="Unique Solo Hotel", website="almosafer")

    matches = match_hotels(db_session, city="Riyadh", check_in=date(2026, 9, 2), check_out=date(2026, 9, 3))

    assert len(matches) == 1
    assert matches[0].match_confidence == 1.0


def test_match_hotels_scoped_to_city_and_dates(db_session):
    _make_hotel(db_session, name="Same Name Hotel", website="almosafer", city="Riyadh",
                check_in=date(2026, 9, 2), check_out=date(2026, 9, 3))
    _make_hotel(db_session, name="Same Name Hotel", website="booking.com", city="Riyadh",
                check_in=date(2026, 10, 1), check_out=date(2026, 10, 2))  # different dates

    matches = match_hotels(db_session, city="Riyadh", check_in=date(2026, 9, 2), check_out=date(2026, 9, 3))

    # Only the first hotel falls within the requested date range.
    assert len(matches) == 1
    assert len(matches[0].listings) == 1
