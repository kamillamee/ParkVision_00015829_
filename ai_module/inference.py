"""ParkVision YOLO occupancy detector.

Accuracy notes (design)
-----------------------
* Two occupancy algorithms are supported (pick via ``--occupancy-mode`` or
  the ``PARKING_VISION_OCCUPANCY_MODE`` env var):

  - ``point`` (default): a slot is marked occupied when the **bottom-center**
    or the **mid-center** of any vehicle bbox lies inside the slot polygon.
    The bottom-center is where the car actually touches the ground — the
    same plane the slot polygon was authored on — so this is robust in
    realistic street-level / perspective views. This matches the proven
    logic of most reference smart-parking demos.
  - ``overlap``: area-ratio of (bbox ∩ slot) / slot_area must meet
    ``--overlap-threshold``. Each car is assigned to only its best slot.
    Works best on strict top-down views where bbox == ground footprint.

* Background / road vehicles are filtered by an optional ``roi`` polygon
  in the slots JSON, a (small) minimum bbox area fraction, and a YOLO
  confidence threshold.
* ``SlotStatusSmoother`` requires N consecutive matching frames before it
  flips a slot's stable status (release threshold is higher than acquire
  so brief misses don't free a slot).
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import threading
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Allow `python ai_module/inference.py ...` to resolve the ai_module package
# without requiring PYTHONPATH to be set.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import cv2
import numpy as np
import requests
import torch
from shapely.geometry import Polygon
from ultralytics import YOLO

# Pure-Python occupancy logic lives in ai_module.occupancy so it's testable
# without OpenCV / PyTorch / Ultralytics installed.
from ai_module.occupancy import (
    DEFAULT_OCCUPANCY_MODE,
    DEFAULT_OVERLAP_THRESHOLD,
    DEFAULT_MIN_BBOX_AREA_FRAC,
    OCCUPANCY_MODE_OVERLAP,
    OCCUPANCY_MODE_POINT,
    STATUS_ACQUIRE_CONSECUTIVE,
    STATUS_RELEASE_CONSECUTIVE,
    SlotStatusSmoother,
    assign_vehicles_to_slots,
    assign_vehicles_to_slots_by_points,
    bbox_polygon as _bbox_polygon,
    compute_slot_status,
    safe_polygon as _safe_polygon,
)
from ultralytics.nn.tasks import DetectionModel
from ultralytics.nn.modules import Conv, C2f, SPPF, Bottleneck, Detect
from torch.nn.modules.container import Sequential, ModuleList, ModuleDict
from torch.nn.modules.conv import Conv2d
from torch.nn.modules.batchnorm import BatchNorm2d
from torch.nn.modules.activation import SiLU
from torch.nn.modules.pooling import MaxPool2d
from torch.nn.modules.upsampling import Upsample

# Register the module classes that appear inside the YOLO .pt checkpoint
# so torch.load can deserialize them under PyTorch's strict default.
# This replaces the previous global monkey-patch of torch.load, which was a
# security smell because it flipped weights_only=False for *every* torch.load
# call in the process.
_YOLO_SAFE_GLOBALS = [
    DetectionModel, Conv, C2f, SPPF, Bottleneck, Detect,
    Sequential, ModuleList, ModuleDict,
    Conv2d, BatchNorm2d, SiLU, MaxPool2d, Upsample,
]
try:
    torch.serialization.add_safe_globals(_YOLO_SAFE_GLOBALS)
except Exception:
    pass


AI_API_KEY = os.getenv("AI_API_KEY", "ai-module-secret-key-12345")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
ROOT_DIR = Path(__file__).parent.parent
VIDEO_PATH = ROOT_DIR / "video" / "bmu.mp4"
VIDEO_PATH_WEST = ROOT_DIR / "video" / "west.mp4"
MODEL_PATH = ROOT_DIR / "models" / "yolo11m.pt"
SLOTS_CONFIG = ROOT_DIR / "config" / "bmu.json"
SLOTS_CONFIG_WEST = ROOT_DIR / "config" / "west.json"
LATEST_JPEG_BY_LOT = {1: "latest.jpg", 2: "latest-lot-2.jpg"}

CHECK_INTERVAL_SECONDS = 0.5
# Lower confidence is OK because we filter by (a) vehicle class, (b) minimum
# bbox area, (c) optional ROI polygon, and (d) per-slot overlap ratio.
DETECTION_CONFIDENCE = 0.25
try:
    DETECTION_IMAGE_SIZE = max(320, int(os.getenv("DETECTION_IMAGE_SIZE", "640")))
except ValueError:
    DETECTION_IMAGE_SIZE = 640

VEHICLE_CLASS_NAMES = {"car", "truck", "bus", "motorcycle"}


def load_slots_config(path: Path) -> Dict[str, np.ndarray]:
    """Load slot polygons. Returns ``{slot_name: np.int32 polygon array}``.

    Polygons must be authored in the source video's pixel space — no
    rescaling is applied. Use ``tools/check_slots.py`` to confirm alignment.
    Entries whose key is ``roi`` are treated as a region-of-interest mask
    and returned separately; they are not slots.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Slots config not found at {path}. "
            "Create it via the slot editor (slots-editor.html) or tools/check_slots.py."
        )
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"Slots config {path} must be a JSON object")

    spots: Dict[str, np.ndarray] = {}
    for name, pts in raw.items():
        if name == "roi":
            continue
        try:
            spots[str(name)] = np.array(pts, dtype=np.int32)
        except Exception as e:
            print(f"WARN: Could not parse polygon for slot {name}: {e}")
    if not spots:
        raise ValueError(f"No slot polygons found in {path}")
    return spots


def load_roi_polygon(path: Path) -> Optional[np.ndarray]:
    """Load an optional 'roi' key from the slots JSON. Detections whose
    bbox center lies outside this polygon are ignored."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return None
    roi = raw.get("roi") if isinstance(raw, dict) else None
    if not roi:
        return None
    try:
        return np.array(roi, dtype=np.int32)
    except Exception:
        return None


def reconcile_slot_names_with_backend(
    spots: Dict[str, np.ndarray],
    backend_url: str,
    lot_id: int,
) -> Dict[str, np.ndarray]:
    """Pass-through: we no longer remap slot names heuristically.

    The old "sort + zip" remap was a silent footgun — polygons could be
    associated with the wrong slot if alphabetical order disagreed with
    the polygon layout. Now we require the JSON keys to match the DB
    slot_number values exactly. Kept as a no-op for backwards compatibility
    with anything that still imports it.
    """
    return spots


def _detection_debug_enabled() -> bool:
    return os.getenv(
        "PARKING_VISION_DEBUG_DETECTION",
        os.getenv("AI_DETECTION_DEBUG", ""),
    ).lower() in ("1", "true", "yes", "on")


def _detection_debug_draw_enabled() -> bool:
    return os.getenv("PARKING_VISION_DEBUG_DRAW", "").lower() in ("1", "true", "yes", "on")


def _debug_overlay(
    frame: np.ndarray,
    spots: Dict[str, np.ndarray],
    detections: list,
    slot_status: dict,
    debug_lot_id: Optional[int],
    roi_polygon: Optional[np.ndarray] = None,
) -> None:
    if debug_lot_id is None:
        return
    vis = frame.copy()
    overlay = vis.copy()
    for name, poly in spots.items():
        col = (0, 0, 200) if slot_status.get(name) else (0, 200, 0)
        cv2.fillPoly(overlay, [poly], col)
    vis = cv2.addWeighted(overlay, 0.25, vis, 0.75, 0)
    for name, poly in spots.items():
        col = (0, 0, 255) if slot_status.get(name) else (0, 255, 0)
        cv2.polylines(vis, [poly], True, col, 2)
        cx = int(poly[:, 0].mean())
        cy = int(poly[:, 1].mean())
        label = f"{name} {'OCC' if slot_status.get(name) else 'FREE'}"
        cv2.putText(vis, label, (cx - 30, cy), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, col, 2, cv2.LINE_AA)
    if roi_polygon is not None:
        cv2.polylines(vis, [roi_polygon], True, (255, 200, 0), 2)
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 165, 255), 2)
    out = ROOT_DIR / "video" / f"debug_detection_lot{debug_lot_id}.jpg"
    try:
        cv2.imwrite(str(out), vis)
    except Exception as e:
        print(f"[YOLO-DEBUG] could not write {out}: {e}")


def _forward_detector(model, frame_bgr, conf: float, imgsz: int, device, use_track: bool):
    kw = dict(conf=conf, imgsz=imgsz, device=device, verbose=False)
    if use_track:
        try:
            return model.track(frame_bgr, persist=True, tracker="bytetrack.yaml", **kw)
        except Exception:
            return model(frame_bgr, **kw)
    return model(frame_bgr, **kw)


def detect_parking_occupancy(
    frame: np.ndarray,
    model,
    spots: Dict[str, np.ndarray],
    conf: float,
    imgsz: int,
    device,
    *,
    use_track: bool = False,
    debug_context: str = "",
    debug_lot_id: Optional[int] = None,
    occupancy_mode: str = DEFAULT_OCCUPANCY_MODE,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
    min_bbox_area_frac: float = DEFAULT_MIN_BBOX_AREA_FRAC,
    roi_polygon: Optional[np.ndarray] = None,
    slot_polys: Optional[Dict[str, Polygon]] = None,
    model_lock: Optional[threading.Lock] = None,
):
    """Run YOLO on the full frame, then test each slot polygon by overlap area.

    Returns ``(slot_status: dict[name->bool], yolo_result_obj)``.
    ``model_lock`` serializes access to the shared YOLO model (Ultralytics
    inference is not thread-safe).
    """
    if model_lock is not None:
        model_lock.acquire()
    try:
        results = _forward_detector(model, frame, conf, imgsz, device, use_track)
    finally:
        if model_lock is not None:
            model_lock.release()

    frame_area = float(frame.shape[0]) * float(frame.shape[1])
    min_bbox_area = max(1.0, min_bbox_area_frac * frame_area)

    detections: List[dict] = []
    if results and results[0].boxes is not None:
        for box in results[0].boxes:
            class_id = int(box.cls[0].cpu().numpy())
            class_name = model.names.get(class_id, "").lower()
            if class_name not in VEHICLE_CLASS_NAMES:
                continue
            bbox = box.xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
            bw = max(0.0, x2 - x1)
            bh = max(0.0, y2 - y1)
            if bw * bh < min_bbox_area:
                continue
            if roi_polygon is not None:
                cx = (x1 + x2) * 0.5
                cy = (y1 + y2) * 0.5
                if cv2.pointPolygonTest(roi_polygon, (cx, cy), False) < 0:
                    continue
            confidence = float(box.conf[0].cpu().numpy())
            detections.append({
                "bbox": (x1, y1, x2, y2),
                "confidence": confidence,
                "class": class_name,
            })

    if slot_polys is None:
        slot_polys = {}
        for name, pts in spots.items():
            poly = _safe_polygon(pts)
            if poly is not None:
                slot_polys[name] = poly

    slot_status = compute_slot_status(
        detections,
        slot_polys,
        mode=occupancy_mode,
        overlap_threshold=overlap_threshold,
    )

    if _detection_debug_enabled():
        print(
            f"[YOLO-DEBUG] {debug_context} frame={frame.shape[1]}x{frame.shape[0]} "
            f"conf={conf:.2f} mode={occupancy_mode} vehicles_kept={len(detections)} "
            f"occupied={sum(1 for v in slot_status.values() if v)}/{len(slot_status)}"
        )
    if _detection_debug_draw_enabled():
        _debug_overlay(frame, spots, detections, slot_status, debug_lot_id, roi_polygon)

    return slot_status, (results[0] if results else None)


def check_backend_available(backend_url: str, timeout: float = 2.0) -> bool:
    try:
        r = requests.get(f"{backend_url}/api/slots/status", timeout=timeout)
        return r.status_code in (200, 401, 403)
    except requests.exceptions.ConnectionError:
        return False
    except Exception:
        return False


BACKEND_UPDATE_TIMEOUT = 5.0
_backend_last_error_time = 0.0
_backend_error_suppress_until = 0.0


def _do_update_backend(
    slot_status: dict,
    backend_url: str,
    api_key: str,
    frame_index: int,
    lot_id: Optional[int] = None,
):
    global _backend_last_error_time, _backend_error_suppress_until
    updates = []
    for slot, occupied in slot_status.items():
        row: Dict = {"slot_number": slot, "is_occupied": bool(occupied)}
        if lot_id is not None:
            row["lot_id"] = int(lot_id)
        updates.append(row)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    try:
        response = requests.post(
            f"{backend_url}/api/slots/update-status",
            json=updates,
            headers=headers,
            timeout=BACKEND_UPDATE_TIMEOUT,
        )
        if response.status_code == 200:
            print(f"OK: Updated backend at frame {frame_index}")
            return
        if time.time() > _backend_error_suppress_until:
            print(f"Error updating backend: HTTP {response.status_code}")
            _backend_last_error_time = time.time()
    except requests.exceptions.ConnectionError:
        if time.time() > _backend_error_suppress_until:
            print("WARN: Backend not reachable. Start server: python run.py")
            _backend_error_suppress_until = time.time() + 30.0
    except requests.exceptions.ReadTimeout:
        if time.time() > _backend_error_suppress_until:
            print(f"WARN: Backend timeout (>{BACKEND_UPDATE_TIMEOUT}s).")
            _backend_error_suppress_until = time.time() + 30.0
    except Exception as e:
        if time.time() > _backend_error_suppress_until:
            print(f"Error updating backend: {e}")
            _backend_error_suppress_until = time.time() + 15.0


def update_backend_slots(
    slot_status: dict,
    backend_url: str,
    api_key: str = AI_API_KEY,
    frame_index: int = 0,
    lot_id: Optional[int] = None,
):
    t = threading.Thread(
        target=_do_update_backend,
        args=(slot_status, backend_url, api_key, frame_index, lot_id),
        daemon=True,
    )
    t.start()


class AsyncDetector:
    def __init__(
        self,
        model,
        spots: Dict[str, np.ndarray],
        conf: float,
        imgsz: int,
        device,
        acquire_consecutive: int = STATUS_ACQUIRE_CONSECUTIVE,
        release_consecutive: int = STATUS_RELEASE_CONSECUTIVE,
        use_track: bool = False,
        debug_context: str = "",
        debug_lot_id: Optional[int] = None,
        occupancy_mode: str = DEFAULT_OCCUPANCY_MODE,
        overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
        min_bbox_area_frac: float = DEFAULT_MIN_BBOX_AREA_FRAC,
        roi_polygon: Optional[np.ndarray] = None,
    ):
        self.model = model
        self.spots = spots
        self.slot_polys: Dict[str, Polygon] = {}
        for name, pts in spots.items():
            poly = _safe_polygon(pts)
            if poly is not None:
                self.slot_polys[name] = poly
        self.conf = conf
        self.imgsz = imgsz
        self.device = device
        self.use_track = use_track
        self.debug_context = debug_context
        self.debug_lot_id = debug_lot_id
        self.occupancy_mode = occupancy_mode
        self.overlap_threshold = overlap_threshold
        self.min_bbox_area_frac = min_bbox_area_frac
        self.roi_polygon = roi_polygon
        self.status_smoother = SlotStatusSmoother(
            acquire_consecutive=acquire_consecutive,
            release_consecutive=release_consecutive,
        )
        self._lock = threading.Lock()
        self._request: Optional[Tuple[int, np.ndarray]] = None
        self._result: Optional[Tuple[int, dict]] = None
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, frame_index: int, frame: np.ndarray) -> bool:
        with self._lock:
            self._request = (frame_index, frame.copy())
        return True

    def pop_result(self) -> Optional[Tuple[int, dict]]:
        with self._lock:
            out = self._result
            self._result = None
            return out

    def stop(self):
        self._running = False
        self._thread.join(timeout=1.0)

    def _run(self):
        while self._running:
            req = None
            with self._lock:
                if self._request is not None:
                    req = self._request
                    self._request = None
            if req is None:
                time.sleep(0.002)
                continue
            frame_index, frame = req
            try:
                raw, _ = detect_parking_occupancy(
                    frame, self.model, self.spots,
                    self.conf, self.imgsz, self.device,
                    use_track=self.use_track,
                    debug_context=self.debug_context,
                    debug_lot_id=self.debug_lot_id,
                    occupancy_mode=self.occupancy_mode,
                    overlap_threshold=self.overlap_threshold,
                    min_bbox_area_frac=self.min_bbox_area_frac,
                    roi_polygon=self.roi_polygon,
                    slot_polys=self.slot_polys,
                )
                smoothed = self.status_smoother.update(raw)
                with self._lock:
                    self._result = (frame_index, smoothed)
            except Exception as e:
                print(f"AsyncDetector error: {e}")
                continue


def load_smart_parking_model(model_path: Path = MODEL_PATH):
    if not model_path.exists():
        print(f"WARN: Model not found at {model_path}, downloading yolo11m.pt...")
        model_path.parent.mkdir(parents=True, exist_ok=True)
        with torch.serialization.safe_globals(_YOLO_SAFE_GLOBALS):
            model = YOLO("yolo11m.pt")
        try:
            import shutil
            cached = Path.home() / ".cache" / "ultralytics" / "yolo11m.pt"
            if cached.exists():
                shutil.copy(str(cached), str(model_path))
                print(f"OK: Model saved to {model_path}")
        except Exception as e:
            print(f"WARN: Could not save model: {e}")
        return model
    print(f"Loading model from {model_path}")
    with torch.serialization.safe_globals(_YOLO_SAFE_GLOBALS):
        return YOLO(str(model_path))


def parse_args():
    parser = argparse.ArgumentParser(description="ParkVision YOLO occupancy detector")
    parser.add_argument("--interval", type=float, default=CHECK_INTERVAL_SECONDS,
                        help="Seconds between YOLO updates (default: 0.5)")
    parser.add_argument("--backend-url", default=BACKEND_URL, help="Backend base URL")
    parser.add_argument("--lot-id", type=int, default=1,
                        help="Parking lot id: 1 = bmu (bmu.mp4), 2 = west (west.mp4)")
    parser.add_argument("--video", default=None, help="Path to video file (default: by --lot-id)")
    parser.add_argument("--slots-json", default=None, help="Path to slots JSON (default: by --lot-id)")
    parser.add_argument("--latest-name", default=None,
                        help="JPEG filename written under video/ (legacy disk frames)")
    parser.add_argument("--conf", type=float, default=DETECTION_CONFIDENCE)
    parser.add_argument("--imgsz", type=int, default=DETECTION_IMAGE_SIZE)
    parser.add_argument("--occupancy-mode", choices=[OCCUPANCY_MODE_POINT, OCCUPANCY_MODE_OVERLAP],
                        default=DEFAULT_OCCUPANCY_MODE,
                        help="'point' (default): bottom/mid-center in slot polygon; "
                             "'overlap': bbox∩slot area ratio >= --overlap-threshold")
    parser.add_argument("--overlap-threshold", type=float, default=DEFAULT_OVERLAP_THRESHOLD,
                        help="(overlap mode only) Min slot-overlap ratio to mark occupied (0..1)")
    parser.add_argument("--min-bbox-area-frac", type=float, default=DEFAULT_MIN_BBOX_AREA_FRAC,
                        help="Reject YOLO boxes smaller than this fraction of the frame")
    parser.add_argument("--acquire-consecutive", type=int, default=STATUS_ACQUIRE_CONSECUTIVE,
                        help="Consecutive frames required to mark a slot OCCUPIED")
    parser.add_argument("--release-consecutive", type=int, default=STATUS_RELEASE_CONSECUTIVE,
                        help="Consecutive frames required to mark a slot FREE")
    parser.add_argument("--device", default="cpu", help="YOLO device, e.g. '0' for GPU or 'cpu'")
    parser.add_argument("--no-gui", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--legacy-disk-frames", action="store_true")
    parser.add_argument("--use-track", action="store_true")
    parser.add_argument("--debug-yolo", action="store_true",
                        help="Print stats and write video/debug_detection_lot{lot-id}.jpg")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.debug_yolo:
        os.environ["PARKING_VISION_DEBUG_DETECTION"] = "1"
        os.environ["PARKING_VISION_DEBUG_DRAW"] = "1"

    backend_url = args.backend_url
    conf = float(args.conf)
    imgsz = int(args.imgsz)
    device = args.device
    interval_seconds = max(0.1, float(args.interval))
    acquire_consecutive = max(1, int(args.acquire_consecutive))
    release_consecutive = max(1, int(args.release_consecutive))
    lot_id = int(args.lot_id)

    slots_path = Path(args.slots_json) if args.slots_json else (
        SLOTS_CONFIG_WEST if lot_id == 2 else SLOTS_CONFIG
    )
    video_path = Path(args.video) if args.video else (
        VIDEO_PATH_WEST if lot_id == 2 else VIDEO_PATH
    )
    latest_name = args.latest_name or LATEST_JPEG_BY_LOT.get(lot_id, "latest.jpg")
    latest_path = ROOT_DIR / "video" / latest_name

    print("ParkVision AI Module Starting...")
    print(f"  lot_id={lot_id}  video={video_path}")
    print(f"  slots={slots_path}  legacy_disk_frames={args.legacy_disk_frames}")

    if not check_backend_available(backend_url):
        print(f"WARN: Backend at {backend_url} not reachable. Detection will run; updates will fail.")

    try:
        model = load_smart_parking_model(MODEL_PATH)
    except Exception as e:
        print(f"ERROR loading model: {e}")
        return

    try:
        spots = load_slots_config(slots_path)
    except Exception as e:
        print(f"ERROR loading slots config: {e}")
        return
    roi_polygon = load_roi_polygon(slots_path)
    print(f"Loaded {len(spots)} parking slots" + ("  (with ROI mask)" if roi_polygon is not None else ""))

    if not video_path.exists():
        print(f"ERROR: Video not found at {video_path}")
        return

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"ERROR: cannot open video: {video_path}")
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Video: {width}x{height} @ {fps:.2f} FPS")

    print("Starting detection loop...")
    if not args.no_gui:
        print("Press 'q' to quit, 's' to save frame")
    print(
        f"Updating once every {interval_seconds:.2f}s, "
        f"mode={args.occupancy_mode}, overlap>={args.overlap_threshold:.2f}, "
        f"acquire={acquire_consecutive} / release={release_consecutive}"
    )

    frame_index = 0
    next_sample_time = 0.0
    frame_delay = 1.0 / fps if fps > 0 else 0.04
    next_frame_time = time.time()

    last_jpeg_write = 0.0
    jpeg_min_interval = 1.0 / 20.0

    # --once runs a single synchronous detection (no thread) so the debug
    # image / backend update is guaranteed to happen before we exit.
    if args.once:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
        if not ret:
            print("ERROR: couldn't read a single frame")
            cap.release()
            return
        raw, _ = detect_parking_occupancy(
            frame, model, spots,
            conf, imgsz, device,
            use_track=bool(args.use_track),
            debug_context=f"standalone lot_id={lot_id}",
            debug_lot_id=lot_id,
            occupancy_mode=args.occupancy_mode,
            overlap_threshold=float(args.overlap_threshold),
            min_bbox_area_frac=float(args.min_bbox_area_frac),
            roi_polygon=roi_polygon,
        )
        print(f"[once] raw slot status for lot {lot_id}:")
        for name, occ in sorted(raw.items()):
            print(f"  {name}: {'OCC' if occ else 'FREE'}")
        if check_backend_available(backend_url):
            _do_update_backend(raw, backend_url, AI_API_KEY, 0, lot_id=lot_id)
        cap.release()
        return

    detector = AsyncDetector(
        model=model,
        spots=spots,
        conf=conf,
        imgsz=imgsz,
        device=device,
        acquire_consecutive=acquire_consecutive,
        release_consecutive=release_consecutive,
        use_track=bool(args.use_track),
        debug_context=f"standalone lot_id={lot_id}",
        debug_lot_id=lot_id,
        occupancy_mode=args.occupancy_mode,
        overlap_threshold=float(args.overlap_threshold),
        min_bbox_area_frac=float(args.min_bbox_area_frac),
        roi_polygon=roi_polygon,
    )
    last_backend_slot_status = None

    while True:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            frame_index = 0
            next_sample_time = 0.0
            next_frame_time = time.time()
            # Video looped — drop smoother state so the first detection on
            # the new cycle is taken as truth instead of being voted against
            # the prior-cycle stable status.
            detector.status_smoother.reset()
            last_backend_slot_status = None
            time.sleep(0.05)
            continue

        if not args.no_gui:
            try:
                cv2.imshow("ParkVision Detection", frame)
            except Exception as e:
                print(f"WARN: Display error: {e}. Use --no-gui to run without preview.")

        now = time.time()
        if args.legacy_disk_frames and now - last_jpeg_write >= jpeg_min_interval:
            try:
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg", dir=str(latest_path.parent))
                os.close(tmp_fd)
                cv2.imwrite(tmp_path, frame)
                os.replace(tmp_path, str(latest_path))
                last_jpeg_write = now
            except Exception:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        video_time = frame_index / fps if fps > 0 else 0.0
        if video_time >= next_sample_time:
            detector.submit(frame_index, frame)
            next_sample_time += interval_seconds

        detection_result = detector.pop_result()
        if detection_result is not None:
            result_frame_index, slot_status = detection_result
            if slot_status != last_backend_slot_status:
                update_backend_slots(
                    slot_status,
                    backend_url,
                    frame_index=result_frame_index,
                    lot_id=lot_id,
                )
                last_backend_slot_status = slot_status

        if not args.no_gui:
            try:
                key = cv2.waitKey(max(1, int(frame_delay * 1000))) & 0xFF
                if key == ord("q") or key == 27:
                    break
                elif key == ord("s"):
                    output_path = Path(__file__).parent.parent / "data" / "parking_frame.jpg"
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(output_path), frame)
                    print(f"Saved frame to {output_path}")
            except Exception:
                pass

        frame_index += 1
        if args.once:
            break

        next_frame_time += frame_delay
        sleep_for = next_frame_time - time.time()
        if sleep_for > 0:
            time.sleep(sleep_for)

    detector.stop()
    cap.release()
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass
    print("AI Module stopped")


if __name__ == "__main__":
    main()
