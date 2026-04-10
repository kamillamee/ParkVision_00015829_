"""MJPEG live stream + frame metadata for parking map overlays."""
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.parking_vision import get_pipeline

router = APIRouter(prefix="/api/stream", tags=["stream"])

BOUNDARY = b"frame"


@router.get("/mjpeg/{lot_id}")
async def mjpeg_stream(lot_id: int):
    """Multipart MJPEG stream (use as <img src="...">)."""
    pipe = get_pipeline(lot_id)
    if pipe is None:
        raise HTTPException(
            status_code=404,
            detail="Live stream not available for this lot (enable is_live + video file, or start server with PARKING_VISION_ENABLED=true).",
        )

    async def generate():
        # Small async wrapper so FastAPI can multiplex; pull sync JPEG from worker.
        while True:
            jpeg = await asyncio.to_thread(pipe.get_latest_jpeg)
            if not jpeg:
                await asyncio.sleep(0.05)
                continue
            yield (
                b"--" + BOUNDARY + b"\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            )
            await asyncio.sleep(1.0 / 30.0)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/frame/{lot_id}/meta")
async def frame_meta(lot_id: int):
    """Native frame size for SVG viewBox (avoids probing JPEG)."""
    pipe = get_pipeline(lot_id)
    if pipe is None:
        raise HTTPException(status_code=404, detail="No active vision pipeline for this lot.")
    return {"width": pipe.width, "height": pipe.height}
