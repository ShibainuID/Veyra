"""Pure track rules: scan-zone handoff, identity continuity, and movement scores."""

import pytest

from domain.tracks import POLICY, TracksFormatError, follow_link, movement_windows, parse_tracks, resolve_handoff

ZONE = [[0.0, 0.0], [0.25, 0.0], [0.25, 0.25], [0.0, 0.25]]  # top-left 200 x 150 px of an 800 x 600 frame


def box(tid, cx, cy, w=100, h=60):
    return [tid, cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, 0.9]


def tracks(frames, fps=1.0):
    return parse_tracks({"width": 800, "height": 600, "fps": fps, "frames": frames})


def still(tid, cx, cy, seconds, start=0):
    return {t: box(tid, cx, cy) for t in range(start, start + seconds)}


def merge(*paths, until):
    return [[float(t), [p[t] for p in paths if t in p]] for t in range(until)]


def test_single_track_in_zone_receives_identity():
    t = tracks(merge(still("1", 100, 75, 20), still("2", 600, 400, 20), until=20))
    h = resolve_handoff(t, ZONE, scan_t=5)
    assert (h.status, h.track_id) == ("confirmed", "1")


def test_two_tracks_in_zone_stay_uncertain():
    t = tracks(merge(still("1", 80, 70, 20), still("2", 130, 80, 20), until=20))
    h = resolve_handoff(t, ZONE, scan_t=5)
    assert (h.status, h.track_id, h.reason) == ("uncertain", None, "multiple_tracks_in_zone")
    assert h.candidates == ("1", "2")


def test_empty_zone_is_unresolved():
    t = tracks(merge(still("1", 600, 400, 20), until=20))
    assert resolve_handoff(t, ZONE, scan_t=5).status == "unresolved"


def test_brief_pass_through_zone_does_not_count():
    passing = {t: box("2", 100, 75) for t in (5,)}
    t = tracks(merge(still("1", 100, 75, 20), passing, until=20))
    h = resolve_handoff(t, ZONE, scan_t=5)
    assert (h.status, h.track_id) == ("confirmed", "1")


def test_identity_holds_through_a_brief_touch():
    other = {t: box("2", 300 + (5 if t == 10 else 200), 300) for t in range(30)}
    t = tracks(merge(still("1", 300, 300, 30), other, until=30), fps=1.0)
    assert follow_link(t, "1", 0.0, {**POLICY, "crowd_s": 2.0}) == (None, None)


def test_sustained_overlap_releases_identity_from_its_start():
    other = {t: box("2", 305 if t >= 10 else 600, 300) for t in range(30)}
    t = tracks(merge(still("1", 300, 300, 30), other, until=30))
    until, reason = follow_link(t, "1", 0.0)
    assert (until, reason) == (10.0, "crowding")


def test_track_gap_releases_identity_at_last_sighting():
    mine = {t: box("1", 300, 300) for t in range(30) if not 10 < t < 15}
    t = tracks(merge(mine, until=30))
    assert follow_link(t, "1", 0.0) == (10.0, "track_lost")


def test_track_leaving_before_the_end_is_released():
    t = tracks(merge(still("1", 300, 300, 10), still("2", 600, 300, 30), until=30))
    assert follow_link(t, "1", 0.0) == (9.0, "track_lost")


def test_movement_score_is_body_diagonals_per_minute():
    diag = (100 ** 2 + 60 ** 2) ** 0.5
    walking = {t: box("1", 100 + t * diag / 10, 300) for t in range(121)}
    t = tracks(merge(walking, until=121))
    windows = movement_windows(t, "1")
    assert [w["start_s"] for w in windows[:2]] == [0.0, 60.0]
    # 0.1 body diagonal per second over 59 steps in 60 visible seconds -> 5.9 per minute.
    assert windows[0]["movement_score"] == pytest.approx(5.9, abs=0.01)
    assert windows[0]["visible_fraction"] == 1.0


def test_partly_visible_window_reports_visibility():
    half = {t: box("1", 300, 300) for t in range(30)}
    w = movement_windows(tracks(merge(half, until=60)), "1")[0]
    assert w["visible_fraction"] == 0.5 and w["movement_score"] == 0.0


def test_malformed_tracks_are_rejected():
    with pytest.raises(TracksFormatError):
        parse_tracks({"width": 800, "height": 600, "frames": [[2.0, []], [1.0, []]]})
    with pytest.raises(TracksFormatError):
        parse_tracks({"frames": []})
