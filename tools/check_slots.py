"""Render slot polygons over the first frame of each parking-lot video so
you can visually confirm polygons line up with the painted bays *before*
starting the backend.

Polygons are drawn at native coordinates — no rescaling. If they don't
align here, fix the JSON (don't expect the runtime to rescale).

Output files:
  - video/slots_overlay_lot1.jpg   (bmu / bmu.mp4)
  - video/slots_overlay_lot2.jpg   (west / west.mp4)

Usage:
  python tools/check_slots.py
  python tools/check_slots.py --lot-id 1
  python tools/check_slots.py --frame 120
  python tools/check_slots.py --image path/to.jpg --lot-id 2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_module.inference import load_slots_config  # noqa: E402

LOT_DEFS = {
    1: {
        "name": "bmu",
        "video": ROOT / "video" / "bmu.mp4",
        "slots": ROOT / "config" / "bmu.json",
        "overlay": ROOT / "video" / "slots_overlay_lot1.jpg",
    },
    2: {
        "name": "west",
        "video": ROOT / "video" / "west.mp4",
        "slots": ROOT / "config" / "west.json",
        "overlay": ROOT / "video" / "slots_overlay_lot2.jpg",
    },
}


def _read_frame(video_path: Path, frame_index: int) -> Optional[np.ndarray]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"ERROR: cannot open video {video_path}")
        return None
    try:
        if frame_index > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, float(frame_index))
        ok, frame = cap.read()
        if not ok or frame is None:
            print(f"ERROR: cannot read frame {frame_index} from {video_path}")
            return None
        return frame
    finally:
        cap.release()


def _draw_polygon(
    vis: np.ndarray,
    pts: np.ndarray,
    label: str,
    border: Tuple[int, int, int] = (0, 200, 0),
    fill: Tuple[int, int, int] = (0, 200, 0),
    fill_alpha: float = 0.25,
) -> None:
    overlay = vis.copy()
    cv2.fillPoly(overlay, [pts], fill)
    cv2.addWeighted(overlay, fill_alpha, vis, 1.0 - fill_alpha, 0, dst=vis)
    cv2.polylines(vis, [pts], True, border, 2, cv2.LINE_AA)
    for p in pts:
        cv2.circle(vis, tuple(int(v) for v in p), 3, (0, 0, 255), -1)
    cx = int(np.mean(pts[:, 0]))
    cy = int(np.mean(pts[:, 1]))
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(vis, (cx - tw // 2 - 4, cy - th - 4), (cx + tw // 2 + 4, cy + 6), (0, 0, 0), -1)
    cv2.putText(
        vis, label, (cx - tw // 2, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255),
        2, cv2.LINE_AA,
    )


def render_lot_overlay(
    lot_id: int,
    frame: np.ndarray,
    slots_json: Path,
    output: Path,
) -> bool:
    spots = load_slots_config(slots_json)
    if not spots:
        print(f"ERROR: no slots loaded from {slots_json}")
        return False
    fh, fw = int(frame.shape[0]), int(frame.shape[1])

    vis = frame.copy()
    for slot_number, pts in spots.items():
        _draw_polygon(vis, np.asarray(pts, dtype=np.int32), slot_number)

    header = f"lot={lot_id}  frame={fw}x{fh}  slots={len(spots)}"
    cv2.rectangle(vis, (0, 0), (fw, 34), (0, 0, 0), -1)
    cv2.putText(
        vis, header, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255),
        1, cv2.LINE_AA,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), vis):
        print(f"ERROR: failed to write {output}")
        return False
    print(f"OK: wrote {output}")
    return True


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render slot polygons on a video frame for visual audit",
    )
    parser.add_argument("--lot-id", type=int, choices=sorted(LOT_DEFS.keys()), default=None)
    parser.add_argument("--frame", type=int, default=0)
    parser.add_argument("--image", type=str, default=None,
                        help="Use a still image instead of the video (requires --lot-id)")
    parser.add_argument("--video", type=str, default=None)
    parser.add_argument("--slots-json", type=str, default=None)
    parser.add_argument("--output", type=str, default=None)
    return parser.parse_args()


def main():
    args = parse_args()
    lot_ids = [args.lot_id] if args.lot_id is not None else sorted(LOT_DEFS.keys())

    overrides_used = bool(args.image or args.video or args.slots_json or args.output)
    if overrides_used and args.lot_id is None:
        print("ERROR: --image/--video/--slots-json/--output require --lot-id")
        sys.exit(2)

    for lot_id in lot_ids:
        defaults = LOT_DEFS[lot_id]
        slots_json = Path(args.slots_json) if args.slots_json else defaults["slots"]
        output = Path(args.output) if args.output else defaults["overlay"]
        if args.image:
            img = cv2.imread(str(Path(args.image)))
            if img is None:
                print(f"ERROR: cannot read image {args.image}")
                continue
            frame = img
        else:
            video_path = Path(args.video) if args.video else defaults["video"]
            if not video_path.exists():
                print(f"WARN: skipping lot {lot_id}: video missing at {video_path}")
                continue
            frame = _read_frame(video_path, args.frame)
            if frame is None:
                continue
        if not slots_json.exists():
            print(f"WARN: skipping lot {lot_id}: slots JSON missing at {slots_json}")
            continue
        render_lot_overlay(lot_id, frame, slots_json, output)


if __name__ == "__main__":
    main()
