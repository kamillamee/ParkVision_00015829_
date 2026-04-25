"""Embedded YOLO vision workers for every ``is_live`` parking lot.

One worker per lot runs a capture thread (grabs frames + encodes JPEG for
MJPEG streaming) plus a detection thread (runs YOLO + overlap-ratio slot
assignment). The YOLO model is shared across workers to save memory, so a
single process-wide lock serializes inference (Ultralytics is not
thread-safe).
"""
from __future__ import annotations

import logging
import os
import sys
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.config import (
    DATABASE_PATH,
    VIDEO_PATH,
    VIDEO_PATH_WEST,
    SLOTS_CONFIG,
    SLOTS_CONFIG_WEST,
    MODEL_PATH,
    PARKING_VISION_ENABLED,
    PARKING_VISION_DETECT_FPS,
    PARKING_VISION_FRAME_SKIP,
    PARKING_VISION_DISPLAY_FPS,
    PARKING_VISION_STREAM_QUALITY,
    PARKING_VISION_USE_TRACK,
    PARKING_VISION_CONF,
)
from ai_module.inference import (
    load_slots_config,
    load_roi_polygon,
    detect_parking_occupancy,
    SlotStatusSmoother,
    load_smart_parking_model,
    DETECTION_CONFIDENCE,
    DETECTION_IMAGE_SIZE,
    DEFAULT_OCCUPANCY_MODE,
    DEFAULT_OVERLAP_THRESHOLD,
    DEFAULT_MIN_BBOX_AREA_FRAC,
    OCCUPANCY_MODE_OVERLAP,
    OCCUPANCY_MODE_POINT,
    STATUS_ACQUIRE_CONSECUTIVE,
    STATUS_RELEASE_CONSECUTIVE,
    _safe_polygon,
)

VISION_DEVICE = os.getenv("PARKING_VISION_DEVICE", "cpu")
_mode_env = os.getenv("PARKING_VISION_OCCUPANCY_MODE", DEFAULT_OCCUPANCY_MODE).strip().lower()
if _mode_env not in (OCCUPANCY_MODE_POINT, OCCUPANCY_MODE_OVERLAP):
    _mode_env = DEFAULT_OCCUPANCY_MODE
PARKING_VISION_OCCUPANCY_MODE = _mode_env
try:
    PARKING_VISION_OVERLAP_THRESHOLD = float(
        os.getenv("PARKING_VISION_OVERLAP_THRESHOLD", str(DEFAULT_OVERLAP_THRESHOLD))
    )
except ValueError:
    PARKING_VISION_OVERLAP_THRESHOLD = DEFAULT_OVERLAP_THRESHOLD
try:
    PARKING_VISION_MIN_BBOX_AREA_FRAC = float(
        os.getenv("PARKING_VISION_MIN_BBOX_AREA_FRAC", str(DEFAULT_MIN_BBOX_AREA_FRAC))
    )
except ValueError:
    PARKING_VISION_MIN_BBOX_AREA_FRAC = DEFAULT_MIN_BBOX_AREA_FRAC

logger = logging.getLogger("parkvision.vision")

_pipelines: Dict[int, "LotVisionPipeline"] = {}
_pipelines_lock = threading.Lock()
_model = None
_model_lock = threading.Lock()
# Serializes Ultralytics inference calls across all pipelines; Ultralytics
# is not documented as thread-safe when the model is shared.
_model_inference_lock = threading.Lock()


def _resolve_video_slots_for_lot(name: str) -> Tuple[Path, Path]:
    n = (name or "").lower()
    if "westminster" in n:
        return VIDEO_PATH_WEST, SLOTS_CONFIG_WEST
    return VIDEO_PATH, SLOTS_CONFIG


def get_pipeline(lot_id: int) -> Optional["LotVisionPipeline"]:
    with _pipelines_lock:
        return _pipelines.get(lot_id)


def discover_live_lots() -> List[Tuple[int, str]]:
    if not DATABASE_PATH.exists():
        return []
    conn = sqlite3.connect(str(DATABASE_PATH))
    try:
        try:
            rows = conn.execute(
                "SELECT id, name FROM parking_lots WHERE COALESCE(is_live,0) = 1 ORDER BY id"
            ).fetchall()
        except Exception:
            rows = []
    finally:
        conn.close()
    return [(int(r[0]), str(r[1])) for r in rows]


def _db_slot_names_for_lot(lot_id: int) -> List[str]:
    """Read slot_number values straight from SQLite — avoids a circular HTTP
    call from the vision worker back to its own FastAPI process."""
    try:
        conn = sqlite3.connect(str(DATABASE_PATH))
        try:
            rows = conn.execute(
                "SELECT slot_number FROM parking_slots WHERE lot_id = ? ORDER BY slot_number",
                (lot_id,),
            ).fetchall()
        finally:
            conn.close()
        return [str(r[0]) for r in rows if r and r[0] is not None]
    except Exception:
        return []


def get_model():
    global _model
    with _model_lock:
        if _model is None:
            _model = load_smart_parking_model(MODEL_PATH)
        return _model


def _update_slots_in_db(lot_id: int, status: Dict[str, bool]) -> None:
    """Write occupancy updates directly to SQLite (no HTTP round-trip).

    Each update is scoped by ``(lot_id, slot_number)`` so two lots that
    happen to share a slot name will never cross-update each other.
    """
    if not status:
        return
    ts = datetime.now(timezone.utc).isoformat()
    try:
        conn = sqlite3.connect(str(DATABASE_PATH))
        try:
            conn.executemany(
                "UPDATE parking_slots SET is_occupied = ?, last_updated = ? "
                "WHERE slot_number = ? AND lot_id = ?",
                [
                    (1 if occ else 0, ts, slot, lot_id)
                    for slot, occ in status.items()
                ],
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.warning("lot %s: failed to write slot updates to DB: %s", lot_id, e)
        return
    try:
        from backend.slot_notify import notify_slot_changed
        notify_slot_changed()
    except Exception:
        pass


class LotVisionPipeline:
    def __init__(self, lot_id: int, lot_name: str, video_path: Path, slots_json: Path):
        self.lot_id = lot_id
        self.lot_name = lot_name
        self.video_path = video_path
        self.slots_json = slots_json
        self._lock = threading.Lock()
        self._jpeg: bytes = b""
        self.width = 1280
        self.height = 720
        self._stop = threading.Event()
        self._cap_thread: Optional[threading.Thread] = None
        self._det_thread: Optional[threading.Thread] = None

        self._spots: Dict[str, np.ndarray] = {}
        self._slot_polys: Dict[str, object] = {}
        self._roi_polygon: Optional[np.ndarray] = None
        self._smoother = SlotStatusSmoother(
            acquire_consecutive=STATUS_ACQUIRE_CONSECUTIVE,
            release_consecutive=STATUS_RELEASE_CONSECUTIVE,
        )
        self._last_backend: Optional[dict] = None
        # Bumped every time the source video loops back to frame 0. Detection
        # results from a stale epoch are discarded so the post-loop smoother
        # never sees a pre-loop reading.
        self._loop_seq = 0
        self._force_submit_next = False
        self._debug_loop = os.getenv("PARKVISION_DEBUG_LOOP", "").lower() in (
            "1", "true", "yes", "on"
        )

        self._det_frame_lock = threading.Lock()
        self._det_pending: Optional[np.ndarray] = None
        self._det_conf = float(PARKING_VISION_CONF) if PARKING_VISION_CONF else DETECTION_CONFIDENCE

    def start(self):
        self._cap_thread = threading.Thread(target=self._run_capture, daemon=True)
        self._det_thread = threading.Thread(target=self._run_detection, daemon=True)
        self._cap_thread.start()
        self._det_thread.start()

    def stop(self):
        self._stop.set()
        if self._cap_thread:
            self._cap_thread.join(timeout=2.0)
        if self._det_thread:
            self._det_thread.join(timeout=2.0)

    def get_latest_jpeg(self) -> bytes:
        with self._lock:
            return self._jpeg

    def _setup(self, frame_w: int, frame_h: int):
        spots = load_slots_config(self.slots_json)
        # Warn (don't remap) if DB slot names don't match config keys.
        db_names = set(_db_slot_names_for_lot(self.lot_id))
        cfg_names = set(spots.keys())
        missing_in_cfg = sorted(db_names - cfg_names)
        missing_in_db = sorted(cfg_names - db_names)
        if db_names and (missing_in_cfg or missing_in_db):
            logger.warning(
                "lot %s: slot name mismatch between DB and %s. "
                "DB has no polygon for: %s. Config has no DB row for: %s. "
                "Fix the JSON keys or re-seed the DB.",
                self.lot_id,
                self.slots_json.name,
                missing_in_cfg,
                missing_in_db,
            )

        self._spots = spots
        self._slot_polys = {}
        for name, pts in spots.items():
            poly = _safe_polygon(pts)
            if poly is not None:
                self._slot_polys[name] = poly

        self._roi_polygon = load_roi_polygon(self.slots_json)
        self._det_conf = float(PARKING_VISION_CONF) if PARKING_VISION_CONF else DETECTION_CONFIDENCE
        print(
            f"PARKING_VISION lot={self.lot_id} ({self.lot_name}) "
            f"video={self.video_path.name} frame={frame_w}x{frame_h} "
            f"slots={len(spots)} roi={'yes' if self._roi_polygon is not None else 'no'} "
            f"det_conf={self._det_conf} overlap>={PARKING_VISION_OVERLAP_THRESHOLD:.2f} "
            f"frame_skip={PARKING_VISION_FRAME_SKIP} detect_fps={PARKING_VISION_DETECT_FPS}"
        )
        if spots:
            first = next(iter(spots))
            print(
                f"PARKING_VISION lot={self.lot_id} alignment check — "
                f"slot {first!r} polygon: {spots[first].tolist()} "
                f"(verify these pixels match the bay in the {frame_w}x{frame_h} video)"
            )

    def _push_slots(self, status: dict, frame_index: int):
        if status == self._last_backend:
            return
        self._last_backend = dict(status)
        _update_slots_in_db(self.lot_id, status)

    def _run_capture(self):
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            print(f"PARKING_VISION: cannot open video {self.video_path}")
            return
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.width, self.height = fw, fh
        try:
            self._setup(fw, fh)
        except Exception as e:
            print(f"PARKING_VISION lot={self.lot_id}: setup failed: {e}")
            cap.release()
            return

        display_fps = min(PARKING_VISION_DISPLAY_FPS, max(1.0, fps))
        frame_delay = 1.0 / display_fps
        next_wall = time.time()
        frame_index = 0
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(PARKING_VISION_STREAM_QUALITY)]

        while not self._stop.is_set():
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                frame_index = 0
                # Demo videos loop. Bump epoch BEFORE clearing pending —
                # any detection thread mid-inference will see the new seq
                # when it returns and drop its stale result.
                self._loop_seq += 1
                self._smoother.reset()
                self._last_backend = None
                with self._det_frame_lock:
                    self._det_pending = None
                self._force_submit_next = True
                if self._debug_loop:
                    print(
                        f"[LOOP] lot={self.lot_id} video looped seq={self._loop_seq}"
                        f" — smoother+dedup+pending cleared"
                    )
                time.sleep(0.05)
                continue

            ok, buf = cv2.imencode(".jpg", frame, encode_params)
            if ok:
                with self._lock:
                    self._jpeg = buf.tobytes()

            frame_index += 1
            should_submit = (
                self._force_submit_next
                or frame_index % max(1, PARKING_VISION_FRAME_SKIP) == 0
            )
            if should_submit:
                with self._det_frame_lock:
                    self._det_pending = frame.copy()
                if self._force_submit_next and self._debug_loop:
                    print(
                        f"[LOOP] lot={self.lot_id} force-submitting first post-loop frame"
                        f" (seq={self._loop_seq})"
                    )
                self._force_submit_next = False

            next_wall += frame_delay
            sleep_for = next_wall - time.time()
            if sleep_for > 0:
                time.sleep(sleep_for)

        cap.release()

    def _run_detection(self):
        model = get_model()
        detect_interval = 1.0 / max(1.0, PARKING_VISION_DETECT_FPS)
        next_detect = 0.0
        frame_i = 0
        det_conf = self._det_conf

        while not self._stop.is_set():
            frame = None
            with self._det_frame_lock:
                if self._det_pending is not None:
                    frame = self._det_pending
                    self._det_pending = None
            if frame is None:
                time.sleep(0.005)
                continue

            now = time.time()
            if now < next_detect:
                continue
            next_detect = now + detect_interval
            frame_i += 1
            seq_at_pickup = self._loop_seq

            try:
                raw, _ = detect_parking_occupancy(
                    frame, model, self._spots,
                    det_conf, DETECTION_IMAGE_SIZE, VISION_DEVICE,
                    use_track=PARKING_VISION_USE_TRACK,
                    debug_context=f"lot_id={self.lot_id} name={self.lot_name!r}",
                    debug_lot_id=self.lot_id,
                    occupancy_mode=PARKING_VISION_OCCUPANCY_MODE,
                    overlap_threshold=PARKING_VISION_OVERLAP_THRESHOLD,
                    min_bbox_area_frac=PARKING_VISION_MIN_BBOX_AREA_FRAC,
                    roi_polygon=self._roi_polygon,
                    slot_polys=self._slot_polys,
                    model_lock=_model_inference_lock,
                )
                # Discard a result computed from a pre-loop frame — applying
                # it would re-seed the freshly-reset smoother with stale
                # data, which is exactly the bug we were chasing.
                if self._loop_seq != seq_at_pickup:
                    if self._debug_loop:
                        print(
                            f"[LOOP] lot={self.lot_id} dropped stale inference"
                            f" (pickup_seq={seq_at_pickup} now_seq={self._loop_seq})"
                        )
                    continue
                smoothed = self._smoother.update(raw)
                if self._debug_loop:
                    raw_occ = sum(1 for v in raw.values() if v)
                    sm_occ = sum(1 for v in smoothed.values() if v)
                    changed = smoothed != self._last_backend
                    print(
                        f"[LOOP] lot={self.lot_id} seq={self._loop_seq}"
                        f" raw_occ={raw_occ}/{len(raw)} smoothed_occ={sm_occ}/{len(smoothed)}"
                        f" push={changed}"
                    )
                self._push_slots(smoothed, frame_i)
            except Exception as e:
                print(f"PARKING_VISION detect error lot={self.lot_id}: {e}")


def start_parking_vision_workers():
    if not PARKING_VISION_ENABLED:
        print("INFO: PARKING_VISION_ENABLED=false — embedded MJPEG/detection off")
        return
    live = discover_live_lots()
    if not live:
        print("INFO: No is_live parking lots — embedded vision not started")
        return

    started = 0
    for lot_id, name in live:
        vpath, spath = _resolve_video_slots_for_lot(name)
        if not vpath.exists():
            print(f"WARN: PARKING_VISION skip lot {lot_id}: missing video {vpath}")
            continue
        if not spath.exists():
            print(f"WARN: PARKING_VISION skip lot {lot_id}: missing slots {spath}")
            continue
        pipe = LotVisionPipeline(lot_id, name, vpath, spath)
        with _pipelines_lock:
            _pipelines[lot_id] = pipe
        pipe.start()
        started += 1
    print(f"OK: PARKING_VISION started {started} lot worker(s)")


def stop_parking_vision_workers():
    with _pipelines_lock:
        pipes = list(_pipelines.values())
        _pipelines.clear()
    for p in pipes:
        p.stop()
