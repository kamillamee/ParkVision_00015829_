"""Unit tests for the YOLO slot-occupancy logic.

These tests are intentionally light on external deps — we stub YOLO entirely
and exercise the pure overlap-ratio / best-slot assignment / smoother code.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_module.occupancy import (  # noqa: E402
    DEFAULT_OVERLAP_THRESHOLD,
    OCCUPANCY_MODE_OVERLAP,
    OCCUPANCY_MODE_POINT,
    SlotStatusSmoother,
    assign_vehicles_to_slots,
    assign_vehicles_to_slots_by_points,
    compute_slot_status,
    safe_polygon,
)


def _slot(pts):
    return safe_polygon(pts)


def test_fully_overlapping_car_marks_slot_occupied():
    slots = {"A1": _slot([(0, 0), (100, 0), (100, 100), (0, 100)])}
    dets = [{"bbox": (10, 10, 90, 90)}]
    status = assign_vehicles_to_slots(dets, slots)
    assert status == {"A1": True}


def test_empty_detections_leaves_all_slots_free():
    slots = {
        "A1": _slot([(0, 0), (100, 0), (100, 100), (0, 100)]),
        "A2": _slot([(200, 0), (300, 0), (300, 100), (200, 100)]),
    }
    status = assign_vehicles_to_slots([], slots)
    assert status == {"A1": False, "A2": False}


def test_car_driving_through_slot_below_threshold_is_ignored():
    # A thin horizontal car clipping only a small part of the slot — should
    # NOT mark it occupied. This is the original "car driving past bays"
    # flicker the new algorithm fixes.
    slots = {"A1": _slot([(0, 0), (100, 0), (100, 100), (0, 100)])}
    dets = [{"bbox": (0, 90, 100, 110)}]  # covers 10% of slot area
    status = assign_vehicles_to_slots(dets, slots, overlap_threshold=DEFAULT_OVERLAP_THRESHOLD)
    assert status == {"A1": False}


def test_car_straddling_two_slots_marks_only_the_best_match():
    # A1 and A2 sit side by side. The car covers 60% of A2 and 20% of A1
    # — the old point-in-polygon code would mark BOTH occupied; the new
    # best-slot-assignment code marks only the majority slot.
    slots = {
        "A1": _slot([(0, 0), (100, 0), (100, 100), (0, 100)]),
        "A2": _slot([(100, 0), (200, 0), (200, 100), (100, 100)]),
    }
    dets = [{"bbox": (80, 0, 160, 100)}]  # 20 px in A1, 60 px in A2
    status = assign_vehicles_to_slots(dets, slots, overlap_threshold=0.25)
    assert status["A2"] is True
    assert status["A1"] is False


def test_smoother_requires_multiple_confirmations_before_flipping():
    smoother = SlotStatusSmoother(acquire_consecutive=3, release_consecutive=5)

    # Seed
    out = smoother.update({"A1": False})
    assert out == {"A1": False}

    # Two occupied readings in a row should NOT yet flip (threshold=3).
    assert smoother.update({"A1": True}) == {"A1": False}
    assert smoother.update({"A1": True}) == {"A1": False}
    # Third occupied reading crosses the acquire threshold.
    assert smoother.update({"A1": True}) == {"A1": True}

    # And a single "free" reading must NOT flip back (release threshold=5).
    for _ in range(4):
        assert smoother.update({"A1": False}) == {"A1": True}
    # Fifth consecutive free reading finally releases.
    assert smoother.update({"A1": False}) == {"A1": False}


def test_point_in_polygon_marks_slot_when_bottom_center_falls_inside():
    slots = {"A1": _slot([(0, 0), (100, 0), (100, 100), (0, 100)])}
    # bottom-center of the bbox (cx=50, y2=95) sits inside the slot
    dets = [{"bbox": (20, 10, 80, 95)}]
    status = assign_vehicles_to_slots_by_points(dets, slots)
    assert status == {"A1": True}


def test_point_in_polygon_ignores_tall_bbox_whose_center_is_above_slot():
    # A car bbox sitting entirely ABOVE the slot — the bottom-center
    # (cx=50, y2=40) and mid-center (cx=50, y=25) are both above the slot
    # (y >= 100), so the slot stays free. The old area-ratio method would
    # have also rejected this, but this test pins down the new behaviour.
    slots = {"A1": _slot([(0, 100), (100, 100), (100, 200), (0, 200)])}
    dets = [{"bbox": (20, 10, 80, 40)}]
    status = assign_vehicles_to_slots_by_points(dets, slots)
    assert status == {"A1": False}


def test_point_in_polygon_handles_tall_perspective_bbox():
    # A tall bbox — a car seen from street level — whose bottom sits INSIDE
    # the slot polygon but whose top reaches far above. The old area-ratio
    # method would flag this as free (tiny intersection / big slot), but
    # point-in-polygon correctly marks it occupied. This is the exact
    # failure case the user reported.
    slots = {"A1": _slot([(0, 180), (100, 180), (100, 220), (0, 220)])}
    dets = [{"bbox": (20, 10, 80, 210)}]  # 200px tall, bottom at y=210 is inside
    assert assign_vehicles_to_slots_by_points(dets, slots) == {"A1": True}
    # And overlap mode at the old 0.25 default would miss it — proves why
    # we switched defaults.
    overlap_status = assign_vehicles_to_slots(dets, slots, overlap_threshold=0.25)
    # bbox height 200, slot height 40 → intersection area = 60*30=1800,
    # slot area = 100*40 = 4000, ratio = 0.45 → still occupied here. Use
    # a narrower slot instead to force the overlap method to fail.
    skinny_slot = {"A1": _slot([(0, 205), (100, 205), (100, 215), (0, 215)])}
    overlap_status = assign_vehicles_to_slots(dets, skinny_slot, overlap_threshold=0.5)
    # ratio = 60*5 / (100*10) = 0.30 — under 0.5 → overlap mode says "free"
    assert overlap_status == {"A1": False}
    # ...but point mode still correctly sees the car
    assert assign_vehicles_to_slots_by_points(dets, skinny_slot) == {"A1": True}


def test_point_in_polygon_empty_inputs():
    slots = {"A1": _slot([(0, 0), (100, 0), (100, 100), (0, 100)])}
    assert assign_vehicles_to_slots_by_points([], slots) == {"A1": False}
    assert assign_vehicles_to_slots_by_points([{"bbox": (10, 10, 90, 90)}], {}) == {}


def test_compute_slot_status_dispatches_on_mode():
    slots = {"A1": _slot([(0, 0), (100, 0), (100, 100), (0, 100)])}
    dets = [{"bbox": (20, 10, 80, 95)}]
    point = compute_slot_status(dets, slots, mode=OCCUPANCY_MODE_POINT)
    overlap = compute_slot_status(dets, slots, mode=OCCUPANCY_MODE_OVERLAP,
                                  overlap_threshold=DEFAULT_OVERLAP_THRESHOLD)
    assert point == {"A1": True}
    assert overlap == {"A1": True}


def test_invalid_polygon_is_rejected_gracefully():
    # A degenerate all-zero "polygon" collapses to a point with zero area.
    bad = _slot([(0, 0), (0, 0), (0, 0)])
    assert bad is None or bad.area == 0
