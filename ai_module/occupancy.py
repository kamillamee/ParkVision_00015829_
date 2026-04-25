"""Pure-Python slot occupancy logic (no OpenCV / PyTorch / Ultralytics deps).

Keeps the overlap-ratio + best-slot assignment + temporal smoothing algorithms
testable without the heavy vision stack.
"""
from __future__ import annotations

from typing import Dict, Optional

from shapely.geometry import Point, Polygon, box as shapely_box
from shapely.validation import make_valid


# Occupancy algorithm:
#   "point"   — bottom-center + mid-center of each bbox vs slot polygon
#               (simple, robust in perspective views, matches real ground
#               contact of a parked vehicle)
#   "overlap" — area-ratio of (bbox ∩ slot) / slot_area >= threshold
#               (stricter but over-penalises tall bboxes / generous slot
#               polygons; left available as an opt-in for top-down views)
OCCUPANCY_MODE_POINT = "point"
OCCUPANCY_MODE_OVERLAP = "overlap"
DEFAULT_OCCUPANCY_MODE = OCCUPANCY_MODE_POINT

# Only used in "overlap" mode — the fraction of the slot polygon that must
# be covered by the assigned car bbox.
DEFAULT_OVERLAP_THRESHOLD = 0.25

# Reject YOLO bboxes smaller than this fraction of the frame (drops tiny
# distant cars that happen to land on a slot polygon). Kept very small so
# legitimate cars further from the camera aren't filtered out; set to 0
# to disable.
DEFAULT_MIN_BBOX_AREA_FRAC = 0.0005

# Smoothing: number of consecutive frames required to lock a slot occupied
# / free. Kept symmetrical so UI latency is even in both directions; raise
# release if brief YOLO misses start freeing bays spuriously.
STATUS_ACQUIRE_CONSECUTIVE = 2
STATUS_RELEASE_CONSECUTIVE = 2


def safe_polygon(pts) -> Optional[Polygon]:
    """Build a Shapely polygon and repair self-intersections if needed."""
    try:
        poly = Polygon([(float(x), float(y)) for x, y in pts])
    except Exception:
        return None
    if poly.is_empty:
        return None
    if not poly.is_valid:
        try:
            poly = make_valid(poly)
        except Exception:
            return None
    if poly.is_empty or poly.area <= 0:
        return None
    return poly


def bbox_polygon(x1: float, y1: float, x2: float, y2: float) -> Polygon:
    return shapely_box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def assign_vehicles_to_slots_by_points(
    detections,
    slot_polys: Dict[str, Polygon],
) -> Dict[str, bool]:
    """Point-in-polygon occupancy (default).

    A slot is marked occupied when the bottom-center OR the mid-center of
    any vehicle bbox falls inside (or on the boundary of) its polygon.
    This matches the simple, proven logic used by most reference
    smart-parking demos and sidesteps the biggest failure mode of the
    area-ratio method: in perspective / street-level views the bbox
    extends up into the sky while the slot polygon lies on the ground,
    so the ratio (bbox ∩ slot) / slot_area drastically under-reports
    occupancy.

    The two probe points share the same x (bbox vertical midline), so a
    single car on a normal side-by-side row can trigger at most one
    slot.
    """
    status: Dict[str, bool] = {name: False for name in slot_polys}
    if not detections or not slot_polys:
        return status

    for det in detections:
        bbox = det.get("bbox")
        if bbox is None or len(bbox) < 4:
            continue
        try:
            x1, y1, x2, y2 = (float(v) for v in bbox[:4])
        except Exception:
            continue

        cx = (x1 + x2) * 0.5
        probe_points = (
            Point(cx, y2),                    # bottom-center (wheels on ground)
            Point(cx, (y1 + y2) * 0.5),       # mid-center (covers near-camera cars)
        )

        for name, spoly in slot_polys.items():
            if status[name]:
                continue
            for p in probe_points:
                try:
                    if spoly.covers(p):       # includes boundary, unlike contains()
                        status[name] = True
                        break
                except Exception:
                    continue

    return status


def assign_vehicles_to_slots(
    detections,
    slot_polys: Dict[str, Polygon],
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> Dict[str, bool]:
    """Each detected car is assigned to the single slot it overlaps most,
    and that slot is marked occupied iff the overlap ratio meets the
    threshold. Cars straddling two bays don't mark both occupied anymore.
    """
    status: Dict[str, bool] = {name: False for name in slot_polys}
    if not detections or not slot_polys:
        return status

    for det in detections:
        bbox = det.get("bbox")
        if bbox is None or len(bbox) < 4:
            continue
        try:
            x1, y1, x2, y2 = (float(v) for v in bbox[:4])
        except Exception:
            continue
        bpoly = bbox_polygon(x1, y1, x2, y2)
        if bpoly.is_empty or bpoly.area <= 0:
            continue

        best_name: Optional[str] = None
        best_ratio = 0.0
        for name, spoly in slot_polys.items():
            try:
                inter = spoly.intersection(bpoly).area
            except Exception:
                inter = 0.0
            if inter <= 0:
                continue
            ratio = inter / spoly.area
            if ratio > best_ratio:
                best_ratio = ratio
                best_name = name

        if best_name is not None and best_ratio >= overlap_threshold:
            status[best_name] = True

    return status


def compute_slot_status(
    detections,
    slot_polys: Dict[str, Polygon],
    mode: str = DEFAULT_OCCUPANCY_MODE,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> Dict[str, bool]:
    """Single entry point — picks the configured occupancy algorithm."""
    if mode == OCCUPANCY_MODE_OVERLAP:
        return assign_vehicles_to_slots(detections, slot_polys, overlap_threshold)
    return assign_vehicles_to_slots_by_points(detections, slot_polys)


class SlotStatusSmoother:
    """Require N consecutive matching detections before flipping a slot.
    Release threshold defaults to 2x acquire so brief misses don't free a slot."""

    def __init__(
        self,
        consecutive_required: int = STATUS_ACQUIRE_CONSECUTIVE,
        acquire_consecutive: Optional[int] = None,
        release_consecutive: Optional[int] = None,
    ):
        self.acquire_consecutive = max(
            1,
            int(acquire_consecutive if acquire_consecutive is not None else consecutive_required),
        )
        default_release = (
            STATUS_RELEASE_CONSECUTIVE
            if acquire_consecutive is None
            else consecutive_required * 2
        )
        self.release_consecutive = max(
            1,
            int(release_consecutive if release_consecutive is not None else default_release),
        )
        self.stable_status: Dict[str, bool] = {}
        self.pending_status: Dict[str, bool] = {}
        self.pending_count: Dict[str, int] = {}

    def reset(self) -> None:
        """Drop all stable + pending state.

        Used when the source stream discontinues (e.g. demo video loops back
        to frame 0). Without this, the prior-cycle stable status persists
        and the smoother would need release/acquire frames to catch up.
        """
        self.stable_status.clear()
        self.pending_status.clear()
        self.pending_count.clear()

    def update(self, raw_status: dict) -> dict:
        output: Dict[str, bool] = {}
        for slot_number, current in raw_status.items():
            current = bool(current)
            stable = self.stable_status.get(slot_number)

            if stable is None:
                self.stable_status[slot_number] = current
                self.pending_status[slot_number] = current
                self.pending_count[slot_number] = 1
                output[slot_number] = current
                continue

            if current == stable:
                self.pending_status[slot_number] = stable
                self.pending_count[slot_number] = 0
                output[slot_number] = stable
                continue

            if self.pending_status.get(slot_number) == current:
                self.pending_count[slot_number] = self.pending_count.get(slot_number, 0) + 1
            else:
                self.pending_status[slot_number] = current
                self.pending_count[slot_number] = 1

            threshold = self.acquire_consecutive if current else self.release_consecutive
            if self.pending_count[slot_number] >= threshold:
                self.stable_status[slot_number] = current
                self.pending_count[slot_number] = 0

            output[slot_number] = self.stable_status[slot_number]
        return output
