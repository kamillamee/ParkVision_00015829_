from __future__ import annotations

import os
import sys
import threading
import time
import sqlite3
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import cv2
import numpy as np
import requests

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
    AI_API_KEY,
    PORT,
    PARKING_VISION_ENABLED,
    PARKING_VISION_DETECT_FPS,
    PARKING_VISION_FRAME_SKIP,
    PARKING_VISION_DISPLAY_FPS,
    PARKING_VISION_STREAM_QUALITY,
    PARKING_VISION_USE_TRACK,
    PARKING_VISION_CONF,
    PARKING_VISION_DISABLE_ROI,
    PARKING_VISION_INFER_W,
    PARKING_VISION_INFER_H,
)
from ai_module.inference import (
    load_slots_config,
    reconcile_slot_names_with_backend,
    infer_config_base_size,
    scale_slots_config,
    build_shapely_polygons,
    roi_bbox_from_slots,
    detect_parking_occupancy,
    SlotStatusSmoother,
    load_smart_parking_model,
    LOT_OVERLAP_THRESHOLD,
    OVERLAP_THRESHOLD,
    DETECTION_CONFIDENCE,
    DETECTION_IMAGE_SIZE,
    STATUS_SWITCH_CONSECUTIVE,
)

VISION_DEVICE = os.getenv("PARKING_VISION_DEVICE", "cpu")

_pipelines: Dict[int, "LotVisionPipeline"] = {}
_pipelines_lock = threading.Lock()
_model = None
_model_lock = threading.Lock()


def _overlap_for_lot_name(name: str) -> float:
    n = (name or "").lower()
    if "westminster" in n:
        return LOT_OVERLAP_THRESHOLD.get(2, OVERLAP_THRESHOLD)
    return LOT_OVERLAP_THRESHOLD.get(1, OVERLAP_THRESHOLD)


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


def get_model():
    global _model
    with _model_lock:
        if _model is None:
            _model = load_smart_parking_model(MODEL_PATH)
        return _model


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

        self._slots_config: dict = {}
        self._shapely_polygons: dict = {}
        self._roi_xyxy: Optional[Tuple[int, int, int, int]] = None
        self._infer_resize = None
        self._overlap = _overlap_for_lot_name(lot_name)
        self._smoother = SlotStatusSmoother(consecutive_required=STATUS_SWITCH_CONSECUTIVE)
        self._last_backend: Optional[dict] = None

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
        slots = load_slots_config(self.slots_json)
        backend_base = f"http://127.0.0.1:{PORT}"
        slots = reconcile_slot_names_with_backend(slots, backend_base, self.lot_id)
        inferred_base = infer_config_base_size(slots)
        scaled = scale_slots_config(slots, (frame_w, frame_h), base_size=inferred_base)
        self._slots_config = scaled
        self._shapely_polygons = build_shapely_polygons(scaled)
        self._roi_xyxy = roi_bbox_from_slots(scaled, frame_w, frame_h)
        if PARKING_VISION_DISABLE_ROI:
            self._roi_xyxy = None
            print(f"PARKING_VISION lot={self.lot_id}: PARKING_VISION_DISABLE_ROI=1 — full-frame inference")
        if self._roi_xyxy is not None and PARKING_VISION_INFER_W > 0 and PARKING_VISION_INFER_H > 0:
            self._infer_resize = (PARKING_VISION_INFER_W, PARKING_VISION_INFER_H)
        else:
            self._infer_resize = None
        self._det_conf = float(PARKING_VISION_CONF) if PARKING_VISION_CONF else DETECTION_CONFIDENCE
        print(
            f"PARKING_VISION lot={self.lot_id} ({self.lot_name}) "
            f"video={self.video_path.name} frame={frame_w}x{frame_h} "
            f"config_base={inferred_base[0]}x{inferred_base[1]} "
            f"roi={self._roi_xyxy} infer={self._infer_resize} "
            f"det_conf={self._det_conf} frame_skip={PARKING_VISION_FRAME_SKIP} detect_fps={PARKING_VISION_DETECT_FPS}"
        )
        if scaled:
            first_slot = next(iter(scaled))
            print(
                f"PARKING_VISION lot={self.lot_id} alignment check — "
                f"slot {first_slot!r} scaled poly: {scaled[first_slot]} "
                f"(verify these pixels match the parking space in the video)"
            )

    def _push_slots(self, status: dict, frame_index: int):
        if status == self._last_backend:
            return
        self._last_backend = dict(status)
        updates = [{"slot_number": k, "is_occupied": bool(v)} for k, v in status.items()]
        url = f"http://127.0.0.1:{PORT}/api/slots/update-status"
        headers = {"Content-Type": "application/json"}
        if AI_API_KEY:
            headers["X-API-Key"] = AI_API_KEY
        try:
            requests.post(url, json=updates, headers=headers, timeout=5.0)
        except Exception:
            pass

    def _run_capture(self):
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            print(f"PARKING_VISION: cannot open video {self.video_path}")
            return
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.width, self.height = fw, fh
        self._setup(fw, fh)

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
                time.sleep(0.05)
                continue

            ok, buf = cv2.imencode(".jpg", frame, encode_params)
            if ok:
                with self._lock:
                    self._jpeg = buf.tobytes()

            frame_index += 1
            if frame_index % max(1, PARKING_VISION_FRAME_SKIP) == 0:
                with self._det_frame_lock:
                    self._det_pending = frame.copy()

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

            try:
                raw, _ = detect_parking_occupancy(
                    frame,
                    model,
                    self._slots_config,
                    self._shapely_polygons,
                    det_conf,
                    DETECTION_IMAGE_SIZE,
                    VISION_DEVICE,
                    self._overlap,
                    roi_xyxy=self._roi_xyxy,
                    infer_resize=self._infer_resize,
                    use_track=PARKING_VISION_USE_TRACK,
                    debug_context=f"lot_id={self.lot_id} name={self.lot_name!r}",
                    debug_lot_id=self.lot_id,
                )
                smoothed = self._smoother.update(raw)
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
