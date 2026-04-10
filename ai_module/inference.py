import argparse
import os
import tempfile
import cv2
import numpy as np
from ultralytics import YOLO
from pathlib import Path
import requests
import json
from typing import List, Tuple, Optional
import time
import threading
import torch
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.geometry import box as shapely_box
from shapely.geometry import Point as ShapelyPoint
from ultralytics.nn.tasks import DetectionModel
from ultralytics.nn.modules import Conv, C2f, SPPF, Bottleneck, Detect
from torch.nn.modules.container import Sequential, ModuleList, ModuleDict
from torch.nn.modules.conv import Conv2d
from torch.nn.modules.batchnorm import BatchNorm2d
from torch.nn.modules.activation import SiLU
from torch.nn.modules.pooling import MaxPool2d
from torch.nn.modules.upsampling import Upsample
try:
    torch.serialization.set_default_load_weights_only(False)
except AttributeError:
    pass
_torch_load = torch.load
def _unsafe_torch_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return _torch_load(*args, **kwargs)
torch.load = _unsafe_torch_load
torch.serialization.add_safe_globals([
    DetectionModel,
    Conv,
    C2f,
    SPPF,
    Bottleneck,
    Detect,
    Sequential,
    ModuleList,
    ModuleDict,
    Conv2d,
    BatchNorm2d,
    SiLU,
    MaxPool2d,
    Upsample,
])

AI_API_KEY = os.getenv("AI_API_KEY", "ai-module-secret-key-12345")
BACKEND_URL = "http://127.0.0.1:8000"
ROOT_DIR = Path(__file__).parent.parent
VIDEO_PATH = ROOT_DIR / "video" / "Parking.mp4"
VIDEO_PATH_WEST = ROOT_DIR / "video" / "Parking-west.mp4"
MODEL_PATH = ROOT_DIR / "models" / "yolo11m.pt"
SLOTS_CONFIG = ROOT_DIR / "config" / "slots.json"
SLOTS_CONFIG_WEST = ROOT_DIR / "config" / "slots-west.json"
LATEST_JPEG_BY_LOT = {1: "latest.jpg", 2: "latest-lot-2.jpg"}
CHECK_INTERVAL_SECONDS = 0.5
DETECTION_CONFIDENCE = 0.35
try:
    DETECTION_IMAGE_SIZE = max(320, int(os.getenv("DETECTION_IMAGE_SIZE", "768")))
except ValueError:
    DETECTION_IMAGE_SIZE = 768
SLOTS_BASE_SIZE = (2560, 1440)
VEHICLE_CLASS_NAMES = {'car', 'truck', 'bus'}
OVERLAP_THRESHOLD = 0.18
LOT_OVERLAP_THRESHOLD = {
    1: 0.18,
    2: 0.12,
}
STATUS_SWITCH_CONSECUTIVE = 2

DEFAULT_SLOTS = {
    "A1": [(100, 100), (200, 100), (200, 200), (100, 200)],
    "A2": [(250, 100), (350, 100), (350, 200), (250, 200)],
    "A3": [(400, 100), (500, 100), (500, 200), (400, 200)],
    "B1": [(100, 250), (200, 250), (200, 350), (100, 350)],
    "B2": [(250, 250), (350, 250), (350, 350), (250, 350)],
    "B3": [(400, 250), (500, 250), (500, 350), (400, 350)],
}

def load_slots_config(path: Path):
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    print(f"WARN: Slots config not found at {path}, using built-in defaults")
    return DEFAULT_SLOTS


def reconcile_slot_names_with_backend(slots_config: dict, backend_url: str, lot_id: int) -> dict:
    try:
        r = requests.get(f"{backend_url}/api/slots/status?lot_id={lot_id}", timeout=3.0)
        if r.status_code != 200:
            return slots_config
        rows = r.json()
        if not isinstance(rows, list):
            return slots_config
        db_names = sorted([str(x.get("slot_number")) for x in rows if x and x.get("slot_number")])
        cfg_names = sorted([str(k) for k in slots_config.keys()])
        if not db_names or not cfg_names:
            return slots_config
        if set(db_names).intersection(cfg_names):
            return slots_config
        if len(db_names) != len(cfg_names):
            return slots_config
        mapped = {db_name: slots_config[cfg_name] for db_name, cfg_name in zip(db_names, cfg_names)}
        print(f"INFO: Remapped slot names to DB naming for lot {lot_id}")
        return mapped
    except Exception:
        return slots_config


def infer_config_base_size(slots_config: dict) -> Tuple[int, int]:
    max_x = 0
    max_y = 0
    for points in slots_config.values():
        for p in points:
            try:
                max_x = max(max_x, int(p[0]))
                max_y = max(max_y, int(p[1]))
            except Exception:
                continue
    candidates = [(1280, 720), (1920, 1080), (2560, 1440), (3840, 2160)]
    for w, h in candidates:
        if max_x <= w and max_y <= h:
            return (w, h)
    return (max(max_x, 1), max(max_y, 1))

def scale_slots_config(slots_config, target_size, base_size=SLOTS_BASE_SIZE):
    if base_size is None:
        base_size = infer_config_base_size(slots_config)
    base_w, base_h = base_size
    target_w, target_h = target_size
    scale_x = target_w / base_w
    scale_y = target_h / base_h
    scaled = {}
    for slot_number, polygon in slots_config.items():
        scaled[slot_number] = [
            [min(target_w - 1, max(0, int(p[0] * scale_x))),
             min(target_h - 1, max(0, int(p[1] * scale_y)))]
            for p in polygon
        ]
    return scaled

def roi_bbox_from_slots(
    slots_config: dict,
    frame_w: int,
    frame_h: int,
    margin_frac: float = 0.08,
) -> Optional[Tuple[int, int, int, int]]:
    xs: List[int] = []
    ys: List[int] = []
    for points in slots_config.values():
        for p in points:
            try:
                xs.append(int(p[0]))
                ys.append(int(p[1]))
            except Exception:
                continue
    if not xs or not ys:
        return None
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(1, max_x - min_x)
    span_y = max(1, max_y - min_y)
    pad_x = int(span_x * margin_frac) + 20
    pad_y = int(span_y * margin_frac) + 20
    x1 = max(0, min_x - pad_x)
    y1 = max(0, min_y - pad_y)
    x2 = min(frame_w, max_x + pad_x)
    y2 = min(frame_h, max_y + pad_y)
    if x2 <= x1 + 4 or y2 <= y1 + 4:
        return None
    return (x1, y1, x2, y2)


def build_shapely_polygons(slots_config: dict) -> dict:
    polys = {}
    for slot_number, points in slots_config.items():
        try:
            poly = ShapelyPolygon(points)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_valid and poly.area > 0:
                polys[slot_number] = poly
            else:
                print(f"WARN: Slot {slot_number} has an invalid polygon and will be skipped")
        except Exception as e:
            print(f"WARN: Could not build polygon for slot {slot_number}: {e}")
    return polys


def compute_overlap_ratio(bbox, slot_poly: ShapelyPolygon) -> float:
    x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    car_area = max(1.0, (x2 - x1) * (y2 - y1))
    vehicle_box = shapely_box(x1, y1, x2, y2)
    try:
        intersection_area = slot_poly.intersection(vehicle_box).area
        IoS = intersection_area / slot_poly.area
        IoC = intersection_area / car_area
        return max(IoS, IoC * 0.75)
    except Exception:
        return 0.0


def _slot_fallback_match(bbox, slot_poly: ShapelyPolygon, overlap: float) -> bool:
    x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    bottom_center = ShapelyPoint((x1 + x2) * 0.5, y2)
    if slot_poly.contains(bottom_center) and overlap >= 0.03:
        return True
    center = ShapelyPoint((x1 + x2) * 0.5, (y1 + y2) * 0.5)
    return slot_poly.contains(center) and overlap >= 0.05


def assign_vehicles_to_slots(
    detections: list,
    shapely_polygons: dict,
    overlap_threshold: float,
) -> dict:
    slot_status = {slot_number: False for slot_number in shapely_polygons}

    for det in detections:
        bbox = det['bbox']

        overlaps = {
            slot_number: compute_overlap_ratio(bbox, poly)
            for slot_number, poly in shapely_polygons.items()
        }

        best_slot = max(overlaps, key=overlaps.get) if overlaps else None
        best_overlap = overlaps[best_slot] if best_slot is not None else 0.0

        for slot_number, poly in shapely_polygons.items():
            if slot_status[slot_number]:
                continue

            overlap = overlaps[slot_number]

            if slot_number == best_slot and overlap >= overlap_threshold:
                slot_status[slot_number] = True
                continue

            if _slot_fallback_match(bbox, poly, overlap):
                slot_status[slot_number] = True

    return slot_status


def is_vehicle_assigned_to_slot(bbox, slot_poly: ShapelyPolygon, overlap_threshold: float) -> bool:
    overlap = compute_overlap_ratio(bbox, slot_poly)
    if overlap >= overlap_threshold:
        return True
    return _slot_fallback_match(bbox, slot_poly, overlap)

def _detection_debug_enabled() -> bool:
    return os.getenv("PARKING_VISION_DEBUG_DETECTION", os.getenv("AI_DETECTION_DEBUG", "")).lower() in (
        "1", "true", "yes", "on",
    )


def _detection_debug_draw_enabled() -> bool:
    return os.getenv("PARKING_VISION_DEBUG_DRAW", "").lower() in ("1", "true", "yes", "on")


def _debug_yolo_detections(
    frame: np.ndarray,
    results,
    model,
    conf_used: float,
    roi_xyxy: Optional[Tuple[int, int, int, int]],
    infer_hw: Tuple[int, int],
    scale_x: float,
    scale_y: float,
    off_x: float,
    off_y: float,
    car_detections: list,
    debug_context: str,
    debug_lot_id: Optional[int],
    *,
    shapely_polygons: Optional[dict] = None,
    slot_status: Optional[dict] = None,
    overlap_threshold: float = 0.18,
):
    fh, fw = int(frame.shape[0]), int(frame.shape[1])
    ih, iw = int(infer_hw[0]), int(infer_hw[1])
    boxes = results[0].boxes if results is not None else None
    n_raw = len(boxes) if boxes is not None else 0

    car_slot_info = []
    if shapely_polygons:
        for det in car_detections:
            overlaps = {
                sn: compute_overlap_ratio(det['bbox'], poly)
                for sn, poly in shapely_polygons.items()
            }
            best_slot = max(overlaps, key=overlaps.get) if overlaps else None
            best_score = overlaps[best_slot] if best_slot else 0.0
            car_slot_info.append((det, best_slot, best_score, overlaps))
    else:
        for det in car_detections:
            car_slot_info.append((det, None, 0.0, {}))

    if _detection_debug_enabled():
        print(
            f"[YOLO-DEBUG] {debug_context} full_frame={fw}x{fh} roi={roi_xyxy} "
            f"infer_tensor={iw}x{ih} conf_thresh={conf_used:.3f} raw_boxes={n_raw} "
            f"car_boxes_after_filter={len(car_detections)}"
        )
        for i, (det, best_slot, best_score, overlaps) in enumerate(car_slot_info):
            bb = det['bbox']
            cf = det['confidence']
            cname = det['class']
            triggered = best_score >= overlap_threshold
            all_str = " ".join(f"{sn}={v:.2f}" for sn, v in overlaps.items())
            print(
                f"  [car {i}] {cname} conf={cf:.3f} "
                f"bbox=[{bb[0]:.0f},{bb[1]:.0f},{bb[2]:.0f},{bb[3]:.0f}] "
                f"best={best_slot}({best_score:.2f}) thresh={overlap_threshold:.2f} "
                f"triggered={'YES' if triggered else 'NO'} all=[{all_str}]"
            )

    if _detection_debug_draw_enabled() and debug_lot_id is not None:
        vis = frame.copy()

        if shapely_polygons:
            overlay = vis.copy()
            for sn, poly in shapely_polygons.items():
                occupied = bool((slot_status or {}).get(sn, False))
                fill_col = (0, 0, 180) if occupied else (0, 180, 0)
                try:
                    pts = np.array(list(poly.exterior.coords), dtype=np.int32)
                    cv2.fillPoly(overlay, [pts], fill_col)
                except Exception:
                    pass
            vis = cv2.addWeighted(overlay, 0.25, vis, 0.75, 0)

            for sn, poly in shapely_polygons.items():
                occupied = bool((slot_status or {}).get(sn, False))
                border_col = (0, 0, 255) if occupied else (0, 255, 0)
                try:
                    pts = np.array(list(poly.exterior.coords), dtype=np.int32)
                    cv2.polylines(vis, [pts], True, border_col, 2)
                    cx = int(np.mean(pts[:, 0]))
                    cy = int(np.mean(pts[:, 1]))
                    label = f"{sn} {'OCC' if occupied else 'FREE'}"
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                    cv2.rectangle(vis, (cx - tw // 2 - 3, cy - th - 3), (cx + tw // 2 + 3, cy + 3), (0, 0, 0), -1)
                    cv2.putText(vis, label, (cx - tw // 2, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
                except Exception:
                    pass

        if roi_xyxy is not None:
            rx1, ry1, rx2, ry2 = roi_xyxy
            cv2.rectangle(vis, (rx1, ry1), (rx2, ry2), (255, 200, 0), 2)
            cv2.putText(vis, "ROI", (rx1 + 4, ry1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 1, cv2.LINE_AA)

        for det, best_slot, best_score, _ in car_slot_info:
            bb = det['bbox']
            bx1, by1, bx2, by2 = int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])
            cf = det['confidence']
            cname = det['class']
            triggered = best_score >= overlap_threshold
            box_col = (0, 255, 80) if triggered else (0, 165, 255)

            cv2.rectangle(vis, (bx1, by1), (bx2, by2), box_col, 2)

            line1 = f"{cname} {cf:.2f}"
            line2 = f"\u2192{best_slot or '?'} ratio={best_score:.2f}"
            font, fscale, fthick = cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1

            for li, txt in enumerate([line1, line2]):
                ty = max(14, by1 - 4 + li * 18) if by1 > 36 else by2 + 14 + li * 18
                (tw, th), _ = cv2.getTextSize(txt, font, fscale, fthick)
                cv2.rectangle(vis, (bx1, ty - th - 2), (bx1 + tw + 2, ty + 2), (0, 0, 0), -1)
                cv2.putText(vis, txt, (bx1 + 1, ty), font, fscale, box_col, fthick, cv2.LINE_AA)

        out = ROOT_DIR / "video" / f"debug_detection_lot{debug_lot_id}.jpg"
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
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
    frame,
    model,
    slots_config: dict,
    shapely_polygons: dict,
    conf,
    imgsz,
    device,
    overlap_threshold,
    *,
    roi_xyxy: Optional[Tuple[int, int, int, int]] = None,
    infer_resize: Optional[Tuple[int, int]] = None,
    use_track: bool = False,
    debug_context: str = "",
    debug_lot_id: Optional[int] = None,
):
    off_x, off_y = 0, 0
    scale_to_crop_x, scale_to_crop_y = 1.0, 1.0

    if roi_xyxy is not None:
        x1, y1, x2, y2 = roi_xyxy
        x1 = max(0, int(x1))
        y1 = max(0, int(y1))
        x2 = min(frame.shape[1], int(x2))
        y2 = min(frame.shape[0], int(y2))
        if x2 <= x1 + 1 or y2 <= y1 + 1:
            roi_xyxy = None
        else:
            crop = frame[y1:y2, x1:x2]
            off_x, off_y = x1, y1
            infer = crop
            if infer_resize is not None:
                rw, rh = int(infer_resize[0]), int(infer_resize[1])
                ch, cw = crop.shape[0], crop.shape[1]
                if cw > 0 and ch > 0 and rw > 0 and rh > 0:
                    infer = cv2.resize(crop, (rw, rh))
                    scale_to_crop_x = cw / float(rw)
                    scale_to_crop_y = ch / float(rh)
            results = _forward_detector(model, infer, conf, imgsz, device, use_track)
            detections = []
            if results[0].boxes is not None:
                for box in results[0].boxes:
                    class_id = int(box.cls[0].cpu().numpy())
                    class_name = model.names.get(class_id, '').lower()
                    if class_name not in VEHICLE_CLASS_NAMES:
                        continue
                    bbox = box.xyxy[0].cpu().numpy()
                    bx1 = bbox[0] * scale_to_crop_x + off_x
                    by1 = bbox[1] * scale_to_crop_y + off_y
                    bx2 = bbox[2] * scale_to_crop_x + off_x
                    by2 = bbox[3] * scale_to_crop_y + off_y
                    confidence = float(box.conf[0].cpu().numpy())
                    detections.append(
                        {'bbox': np.array([bx1, by1, bx2, by2]), 'confidence': confidence, 'class': class_name}
                    )

            slot_status = assign_vehicles_to_slots(detections, shapely_polygons, overlap_threshold)
            for slot_number in slots_config:
                if slot_number not in slot_status:
                    slot_status[slot_number] = False
            _debug_yolo_detections(
                frame,
                results,
                model,
                conf,
                (x1, y1, x2, y2),
                (infer.shape[0], infer.shape[1]),
                scale_to_crop_x,
                scale_to_crop_y,
                float(off_x),
                float(off_y),
                detections,
                debug_context or "detect",
                debug_lot_id,
                shapely_polygons=shapely_polygons,
                slot_status=slot_status,
                overlap_threshold=overlap_threshold,
            )
            return slot_status, results[0]

    results = _forward_detector(model, frame, conf, imgsz, device, use_track)

    detections = []
    if results[0].boxes is not None:
        for box in results[0].boxes:
            class_id = int(box.cls[0].cpu().numpy())
            class_name = model.names.get(class_id, '').lower()
            if class_name not in VEHICLE_CLASS_NAMES:
                continue
            bbox = box.xyxy[0].cpu().numpy()
            confidence = float(box.conf[0].cpu().numpy())
            detections.append({'bbox': bbox, 'confidence': confidence, 'class': class_name})

    slot_status = assign_vehicles_to_slots(detections, shapely_polygons, overlap_threshold)
    for slot_number in slots_config:
        if slot_number not in slot_status:
            slot_status[slot_number] = False

    _debug_yolo_detections(
        frame,
        results,
        model,
        conf,
        None,
        (frame.shape[0], frame.shape[1]),
        1.0,
        1.0,
        0.0,
        0.0,
        detections,
        debug_context or "detect",
        debug_lot_id,
        shapely_polygons=shapely_polygons,
        slot_status=slot_status,
        overlap_threshold=overlap_threshold,
    )
    return slot_status, results[0]


class SlotStatusSmoother:

    def __init__(self, consecutive_required: int = STATUS_SWITCH_CONSECUTIVE,
                 acquire_consecutive: int = None, release_consecutive: int = None):
        self.acquire_consecutive = max(1, int(acquire_consecutive if acquire_consecutive is not None else consecutive_required))
        self.release_consecutive = max(1, int(release_consecutive if release_consecutive is not None else consecutive_required * 4))
        self.stable_status = {}
        self.pending_status = {}
        self.pending_count = {}

    def update(self, raw_status: dict) -> dict:
        output = {}
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


def _do_update_backend(slot_status: dict, backend_url: str, api_key: str, frame_index: int):
    global _backend_last_error_time, _backend_error_suppress_until
    updates = [
        {"slot_number": slot, "is_occupied": occupied}
        for slot, occupied in slot_status.items()
    ]
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    try:
        response = requests.post(
            f"{backend_url}/api/slots/update-status",
            json=updates,
            headers=headers,
            timeout=BACKEND_UPDATE_TIMEOUT
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
            print(f"WARN: Backend timeout (>{BACKEND_UPDATE_TIMEOUT}s). Is server running? python run.py")
            _backend_error_suppress_until = time.time() + 30.0
    except Exception as e:
        if time.time() > _backend_error_suppress_until:
            print(f"Error updating backend: {e}")
            _backend_error_suppress_until = time.time() + 15.0


def update_backend_slots(slot_status: dict, backend_url: str, api_key: str = AI_API_KEY, frame_index: int = 0):
    t = threading.Thread(
        target=_do_update_backend,
        args=(slot_status, backend_url, api_key, frame_index),
        daemon=True
    )
    t.start()


class AsyncDetector:

    def __init__(
        self,
        model,
        slots_config,
        shapely_polygons,
        conf,
        imgsz,
        device,
        overlap_threshold,
        switch_consecutive,
        roi_xyxy=None,
        infer_resize=None,
        use_track=False,
        debug_context: str = "",
        debug_lot_id: Optional[int] = None,
    ):
        self.model = model
        self.slots_config = slots_config
        self.shapely_polygons = shapely_polygons
        self.conf = conf
        self.imgsz = imgsz
        self.device = device
        self.overlap_threshold = overlap_threshold
        self.roi_xyxy = roi_xyxy
        self.infer_resize = infer_resize
        self.use_track = use_track
        self.debug_context = debug_context
        self.debug_lot_id = debug_lot_id
        self.status_smoother = SlotStatusSmoother(consecutive_required=switch_consecutive)
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
                raw_slot_status, _ = detect_parking_occupancy(
                    frame,
                    self.model,
                    self.slots_config,
                    self.shapely_polygons,
                    self.conf,
                    self.imgsz,
                    self.device,
                    self.overlap_threshold,
                    roi_xyxy=self.roi_xyxy,
                    infer_resize=self.infer_resize,
                    use_track=self.use_track,
                    debug_context=self.debug_context,
                    debug_lot_id=self.debug_lot_id,
                )
                smoothed = self.status_smoother.update(raw_slot_status)
                with self._lock:
                    self._result = (frame_index, smoothed)
            except Exception:
                continue

def load_smart_parking_model(model_path: Path = MODEL_PATH):
    if not model_path.exists():
        print(f"WARN: Model not found at {model_path}")
        print("Downloading YOLO11m model...")
        model_path.parent.mkdir(parents=True, exist_ok=True)
        with torch.serialization.safe_globals([
            DetectionModel, Conv, C2f, SPPF, Bottleneck, Detect,
            Sequential, ModuleList, ModuleDict, Conv2d, BatchNorm2d, SiLU,
            MaxPool2d, Upsample,
        ]):
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
    with torch.serialization.safe_globals([
        DetectionModel, Conv, C2f, SPPF, Bottleneck, Detect,
        Sequential, ModuleList, ModuleDict, Conv2d, BatchNorm2d, SiLU,
        MaxPool2d, Upsample,
    ]):
        return YOLO(str(model_path))


def parse_args():
    parser = argparse.ArgumentParser(description="Smart Vision YOLO video simulation")
    parser.add_argument("--interval", type=float, default=CHECK_INTERVAL_SECONDS,
                        help="Seconds between YOLO updates (default: 0.5)")
    parser.add_argument("--backend-url", default=BACKEND_URL, help="Backend base URL")
    parser.add_argument("--lot-id", type=int, default=1,
                        help="Parking lot id: 1 = British School (Parking.mp4), 2 = Westminster (Parking-west.mp4)")
    parser.add_argument("--video", default=None, help="Path to video file (default: by --lot-id)")
    parser.add_argument("--slots-json", default=None, help="Path to slots JSON (default: by --lot-id)")
    parser.add_argument("--latest-name", default=None,
                        help="JPEG filename written under video/ (default: latest.jpg or latest-lot-2.jpg)")
    parser.add_argument("--conf", type=float, default=DETECTION_CONFIDENCE,
                        help="YOLO confidence threshold (default: 0.35)")
    parser.add_argument("--imgsz", type=int, default=DETECTION_IMAGE_SIZE,
                        help="YOLO inference image size (default: from DETECTION_IMAGE_SIZE env or 768)")
    parser.add_argument(
        "--overlap-threshold",
        type=float,
        default=None,
        help="Slot area overlap ratio required to mark occupied (default: auto by lot/camera)",
    )
    parser.add_argument(
        "--switch-consecutive",
        type=int,
        default=STATUS_SWITCH_CONSECUTIVE,
        help="Consecutive detections required before switching slot status (default: 2)",
    )
    parser.add_argument("--device", default="cpu",
                        help="YOLO device, e.g. '0' for GPU or 'cpu' (default: cpu)")
    parser.add_argument("--no-gui", action="store_true", help="Disable GUI preview window")
    parser.add_argument("--once", action="store_true", help="Process a single frame then exit")
    parser.add_argument(
        "--legacy-disk-frames",
        action="store_true",
        help="Write latest.jpg to video/ (legacy; prefer FastAPI MJPEG embedded vision)",
    )
    parser.add_argument(
        "--no-roi",
        action="store_true",
        help="Run YOLO on full frame instead of parking ROI crop",
    )
    parser.add_argument(
        "--use-track",
        action="store_true",
        help="Use ByteTrack (model.track) when available",
    )
    parser.add_argument(
        "--debug-yolo",
        action="store_true",
        help="Print YOLO boxes each pass and write video/debug_detection_lot{lot-id}.jpg",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if getattr(args, "debug_yolo", False):
        os.environ["PARKING_VISION_DEBUG_DETECTION"] = "1"
        os.environ["PARKING_VISION_DEBUG_DRAW"] = "1"
    backend_url = args.backend_url
    conf = float(args.conf)
    imgsz = int(args.imgsz)
    device = args.device
    interval_seconds = max(0.5, float(args.interval))
    switch_consecutive = max(1, int(args.switch_consecutive))
    lot_id = int(args.lot_id)
    if args.overlap_threshold is None:
        overlap_threshold = LOT_OVERLAP_THRESHOLD.get(lot_id, OVERLAP_THRESHOLD)
    else:
        overlap_threshold = max(0.01, min(1.0, float(args.overlap_threshold)))
    slots_path = Path(args.slots_json) if args.slots_json else (
        SLOTS_CONFIG_WEST if lot_id == 2 else SLOTS_CONFIG
    )
    video_path = Path(args.video) if args.video else (
        VIDEO_PATH_WEST if lot_id == 2 else VIDEO_PATH
    )
    latest_name = args.latest_name or LATEST_JPEG_BY_LOT.get(lot_id, "latest.jpg")
    latest_path = ROOT_DIR / "video" / latest_name

    print("Smart Vision AI Module Starting...")
    print(f"  lot_id={lot_id}  video={video_path}")
    print(f"  slots={slots_path}  legacy_disk_frames={args.legacy_disk_frames}")

    if not check_backend_available(backend_url):
        print()
        print("WARN: Backend server is not running at", backend_url)
        print("      Start it first in another terminal:  python run.py")
        print("      Then run this AI module again. Detection will run but slot updates will fail until then.")
        print()

    try:
        model = load_smart_parking_model(MODEL_PATH)
    except Exception as e:
        print(f"ERROR: Error loading model: {e}")
        print("TIP: Make sure you have internet connection for first-time download")
        return

    slots_config = load_slots_config(slots_path)
    slots_config = reconcile_slot_names_with_backend(slots_config, backend_url, lot_id)
    print(f"Loaded {len(slots_config)} parking slots")

    if not video_path.exists():
        print(f"ERROR: Video not found at {video_path}")
        return

    try:
        cap = cv2.VideoCapture(str(video_path))

        if not cap.isOpened():
            print(f"ERROR: Could not open video: {video_path}")
            print("TIP: Please ensure the video file exists and is a valid video format")
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Video: {width}x{height} @ {fps:.2f} FPS")
        inferred_base = infer_config_base_size(slots_config)
        slots_config = scale_slots_config(slots_config, (width, height), base_size=inferred_base)
        print(f"Slots base={inferred_base[0]}x{inferred_base[1]} -> scaled to {width}x{height}")
    except Exception as e:
        print(f"ERROR: Error opening video file: {e}")
        return

    shapely_polygons = build_shapely_polygons(slots_config)
    print(f"Built {len(shapely_polygons)} valid slot polygons")

    print(f"Processing video: {video_path}")
    print("Starting detection loop...")
    if not args.no_gui:
        print("Press 'q' to quit, 's' to save frame")

    fps = fps if fps > 0 else 30.0
    print(f"Updating once every {interval_seconds:.2f}s")
    print(f"Status smoothing: switch after {switch_consecutive} consecutive updates")
    print(f"Overlap threshold: {overlap_threshold:.2f}")

    frame_index = 0
    next_sample_time = 0.0
    frame_delay = 1.0 / fps if fps > 0 else 0.04
    next_frame_time = time.time()
    window_shown = False
    roi_xyxy = None if args.no_roi else roi_bbox_from_slots(slots_config, width, height)
    try:
        irw = int(os.getenv("PARKING_VISION_INFER_W", "0"))
        irh = int(os.getenv("PARKING_VISION_INFER_H", "0"))
    except ValueError:
        irw, irh = 0, 0
    infer_resize = (irw, irh) if roi_xyxy is not None and irw > 0 and irh > 0 else None
    if roi_xyxy:
        print(f"ROI inference: {roi_xyxy} resize={infer_resize!r} (set PARKING_VISION_INFER_W/H>0 to downscale)")

    last_jpeg_write = 0.0
    jpeg_min_interval = 1.0 / 20.0

    detector = AsyncDetector(
        model=model,
        slots_config=slots_config,
        shapely_polygons=shapely_polygons,
        conf=conf,
        imgsz=imgsz,
        device=device,
        overlap_threshold=overlap_threshold,
        switch_consecutive=switch_consecutive,
        roi_xyxy=roi_xyxy,
        infer_resize=infer_resize,
        use_track=bool(args.use_track),
        debug_context=f"standalone lot_id={lot_id}",
        debug_lot_id=lot_id,
    )
    last_backend_slot_status = None

    while True:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            frame_index = 0
            next_sample_time = 0.0
            next_frame_time = time.time()
            time.sleep(0.05)
            continue

        if not args.no_gui:
            try:
                cv2.imshow("Smart Vision Detection", frame)
                window_shown = True
            except Exception as e:
                if not window_shown:
                    print(f"WARN: Display error: {e}. Use --no-gui to run without preview.")
                window_shown = True

        now = time.time()
        if args.legacy_disk_frames and now - last_jpeg_write >= jpeg_min_interval:
            try:
                tmp_fd, tmp_path = tempfile.mkstemp(
                    suffix='.jpg', dir=str(latest_path.parent)
                )
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
                update_backend_slots(slot_status, backend_url, frame_index=result_frame_index)
                last_backend_slot_status = slot_status

        if not args.no_gui:
            try:
                key = cv2.waitKey(max(1, int(frame_delay * 1000))) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
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
