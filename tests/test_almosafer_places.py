from src.crawlers.almosafer_places import _find_place_id_candidates, _pick_best_match, PLACE_ID_PATTERN


def test_place_id_pattern_matches_real_shape():
    assert PLACE_ID_PATTERN.match("ChIJWX4TsR_QwxUR2xixN5dXWeA")
    assert not PLACE_ID_PATTERN.match("not-a-place-id")
    assert not PLACE_ID_PATTERN.match("12345")


def test_find_place_id_candidates_extracts_from_nested_structure():
    data = {
        "results": [
            {"placeId": "ChIJabc123def456", "name": "Jeddah"},
            {"id": "not-a-place-id"},  # doesn't match ChIJ pattern — excluded
            {"nested": {"place_id": "ChIJdef456ghi789", "displayName": "Riyadh"}},
        ]
    }
    candidates = []
    _find_place_id_candidates(data, candidates)

    found_ids = {c.get("placeId") or c.get("place_id") for c in candidates}
    assert found_ids == {"ChIJabc123def456", "ChIJdef456ghi789"}


def test_find_place_id_candidates_handles_empty_input():
    candidates = []
    _find_place_id_candidates({}, candidates)
    _find_place_id_candidates([], candidates)
    assert candidates == []


def test_pick_best_match_prefers_name_matching_requested_city():
    candidates = [
        {"placeId": "ChIJwrongwrongwrong", "name": "Wrong City"},
        {"placeId": "ChIJrightrightright", "name": "جدة"},
    ]
    place_id, matched_name = _pick_best_match(candidates, "جدة")
    assert place_id == "ChIJrightrightright"
    assert matched_name == "جدة"


def test_pick_best_match_falls_back_to_first_when_no_name_matches():
    candidates = [
        {"placeId": "ChIJfirstfirstfirst", "name": "Some Other Place"},
    ]
    place_id, _ = _pick_best_match(candidates, "جدة")
    assert place_id == "ChIJfirstfirstfirst"
