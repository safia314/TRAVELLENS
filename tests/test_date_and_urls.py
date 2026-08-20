from datetime import date, timedelta

import pytest

from src.crawlers.booking import validate_date_range as booking_validate_dates, build_search_url as booking_build_url
from src.crawlers.almosafer import validate_date_range as almosafer_validate_dates, build_search_url as almosafer_build_url


FUTURE_CHECKIN = (date.today() + timedelta(days=14)).isoformat()
FUTURE_CHECKOUT = (date.today() + timedelta(days=16)).isoformat()


@pytest.mark.parametrize("validate_fn", [booking_validate_dates, almosafer_validate_dates])
def test_validate_date_range_accepts_valid_future_dates(validate_fn):
    checkin, checkout = validate_fn(FUTURE_CHECKIN, FUTURE_CHECKOUT)
    assert checkin < checkout


@pytest.mark.parametrize("validate_fn", [booking_validate_dates, almosafer_validate_dates])
def test_validate_date_range_rejects_bad_format(validate_fn):
    with pytest.raises(ValueError):
        validate_fn("14-08-2026", FUTURE_CHECKOUT)  # wrong format (DD-MM-YYYY, not YYYY-MM-DD)


@pytest.mark.parametrize("validate_fn", [booking_validate_dates, almosafer_validate_dates])
def test_validate_date_range_rejects_checkout_before_checkin(validate_fn):
    with pytest.raises(ValueError):
        validate_fn(FUTURE_CHECKOUT, FUTURE_CHECKIN)  # swapped


@pytest.mark.parametrize("validate_fn", [booking_validate_dates, almosafer_validate_dates])
def test_validate_date_range_rejects_equal_dates(validate_fn):
    with pytest.raises(ValueError):
        validate_fn(FUTURE_CHECKIN, FUTURE_CHECKIN)  # zero-night stay


@pytest.mark.parametrize("validate_fn", [booking_validate_dates, almosafer_validate_dates])
def test_validate_date_range_rejects_past_checkin(validate_fn):
    past = (date.today() - timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):
        validate_fn(past, FUTURE_CHECKOUT)


def test_booking_build_search_url_contains_expected_params():
    url = booking_build_url("Jeddah", "2026-08-14", "2026-08-16", 2, 1)
    assert "ss=Jeddah" in url
    assert "checkin=2026-08-14" in url
    assert "checkout=2026-08-16" in url
    assert "group_adults=2" in url
    assert "no_rooms=1" in url


def test_almosafer_build_search_url_uses_dd_mm_yyyy_and_encodes_place_id():
    url = almosafer_build_url(
        "جدة",
        "ChIJWX4TsR_QwxUR2xixN5dXWeA",
        date(2026, 8, 14),
        date(2026, 8, 16),
        2,
    )
    assert "14-08-2026" in url          # DD-MM-YYYY, not ISO — Almosafer's URL shape
    assert "15-08-2026" not in url
    assert "16-08-2026" in url
    assert "placeId=ChIJWX4TsR_QwxUR2xixN5dXWeA" in url
    assert "2_adult" in url
