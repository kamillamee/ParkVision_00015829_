"""Run YOLO on each video frame and display detections."""
import argparse
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO
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

VIDEO_PATH = Path(__file__).parent.parent / "video" / "Parking.mp4"
MODEL_PATH = Path(__file__).parent.parent / "models" / "yolo11m.pt"

def parse_args():
    parser = argparse.ArgumentParser(description="YOLO video evaluation viewer")
    parser.add_argument("--video", default=str(VIDEO_PATH), help="Path to video file")
    parser.add_argument("--model", default=str(MODEL_PATH), help="Path to YOLO weights")
    parser.add_argument("--conf", type=float, default=0.15, help="YOLO confidence threshold")
    parser.add_argument("--imgsz", type=int, default=640, help="YOLO inference image size")
    return parser.parse_args()

def main():
    args = parse_args()
    video_path = Path(args.video)
    model_path = Path(args.model)

    if not video_path.exists():
        print(f"ERROR: Video not found at {video_path}")
        return

    model_weights = str(model_path) if model_path.exists() else "yolo11m.pt"
    if not model_path.exists():
        print(f"Model not found at {model_path}, using YOLO11m (will download if needed)")
    print(f"Loading model: {model_weights}")
    with torch.serialization.safe_globals([
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
    ]):
        model = YOLO(model_weights)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"ERROR: Could not open video: {video_path}")
        return

    print("Press 'q' to quit.")
    while True:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        results = model(frame, conf=args.conf, imgsz=args.imgsz)
        annotated_frame = results[0].plot()
        cv2.imshow("YOLO Detections", annotated_frame)


        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
