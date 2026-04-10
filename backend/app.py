from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from backend.limiter import limiter
from backend.routes import auth, slots, reservations, cars, admin, chat, sensors, lots, payments, stream
import threading
import time

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from backend.database import init_db
        import aiosqlite
        from backend.config import DATABASE_PATH
        
        await init_db()
        print("OK: Database initialized successfully")

        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT COUNT(*) as count FROM parking_slots") as cursor:
                slot_count = (await cursor.fetchone())["count"]
                if slot_count == 0:
                    print("WARN: No parking slots found. Auto-seeding slots...")
                    try:
                        import json
                        from backend.config import SLOTS_CONFIG

                        if SLOTS_CONFIG.exists():
                            with open(SLOTS_CONFIG, 'r', encoding='utf-8') as f:
                                slots_data = json.load(f)
                        else:
                            slots_data = {
                                "A1": [[100, 100], [200, 100], [200, 200], [100, 200]],
                                "A2": [[250, 100], [350, 100], [350, 200], [250, 200]],
                                "A3": [[400, 100], [500, 100], [500, 200], [400, 200]],
                                "A4": [[550, 100], [650, 100], [650, 200], [550, 200]],
                                "B1": [[100, 250], [200, 250], [200, 350], [100, 350]],
                                "B2": [[250, 250], [350, 250], [350, 350], [250, 350]],
                                "B3": [[400, 250], [500, 250], [500, 350], [400, 350]],
                                "B4": [[550, 250], [650, 250], [650, 350], [550, 350]],
                                "C1": [[100, 400], [200, 400], [200, 500], [100, 500]],
                                "C2": [[250, 400], [350, 400], [350, 500], [250, 500]],
                                "C3": [[400, 400], [500, 400], [500, 500], [400, 500]],
                                "C4": [[550, 400], [650, 400], [650, 500], [550, 500]]
                            }

                        default_lot_id = None
                        try:
                            async with db.execute("SELECT id FROM parking_lots LIMIT 1") as c:
                                row = await c.fetchone()
                                if row:
                                    default_lot_id = row["id"]
                        except Exception:
                            pass

                        for slot_number, polygon in slots_data.items():
                            zone = slot_number[0]
                            if default_lot_id is not None:
                                try:
                                    async with db.execute(
                                        """INSERT INTO parking_slots (slot_number, zone, is_occupied, lot_id)
                                           VALUES (?, ?, 0, ?)""",
                                        (slot_number, zone, default_lot_id)
                                    ):
                                        pass
                                except Exception:
                                    async with db.execute(
                                        """INSERT INTO parking_slots (slot_number, zone, is_occupied)
                                           VALUES (?, ?, 0)""",
                                        (slot_number, zone)
                                    ):
                                        pass
                            else:
                                async with db.execute(
                                    """INSERT INTO parking_slots (slot_number, zone, is_occupied)
                                       VALUES (?, ?, 0)""",
                                    (slot_number, zone)
                                ):
                                    pass
                        
                        await db.commit()
                        print(f"OK: Auto-seeded {len(slots_data)} parking slots")
                    except Exception as e:
                        print(f"WARN: Could not auto-seed slots: {e}")
                        print("   Run manually: python backend/seed_slots.py")
    except Exception as e:
        print(f"WARN: Database initialization warning: {e}")

    def _start_vision_delayed():
        time.sleep(1.5)
        try:
            from backend.parking_vision import start_parking_vision_workers
            start_parking_vision_workers()
        except Exception as e:
            print(f"WARN: Embedded parking vision failed to start: {e}")

    threading.Thread(target=_start_vision_delayed, daemon=True).start()

    yield

    try:
        from backend.parking_vision import stop_parking_vision_workers
        stop_parking_vision_workers()
    except Exception:
        pass

app = FastAPI(
    title="Smart Vision System API",
    description="AI-powered parking management system",
    version="1.0.0",
    lifespan=lifespan
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(slots.router)
app.include_router(reservations.router)
app.include_router(cars.router)
app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(sensors.router)
app.include_router(lots.router)
app.include_router(payments.router)
app.include_router(stream.router)

frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path / "static")), name="static")

video_path = Path(__file__).parent.parent / "video"
if video_path.exists():
    _nocache_img = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    @app.get("/media/latest.jpg")
    async def serve_latest_frame():
        latest = video_path / "latest.jpg"
        if latest.exists():
            return FileResponse(str(latest), media_type="image/jpeg", headers=_nocache_img)
        raise HTTPException(status_code=404, detail="Latest frame not available. Run AI module.")

    @app.get("/media/lot/{lot_id}/latest.jpg")
    async def serve_latest_frame_for_lot(lot_id: int):
        import aiosqlite
        from backend.config import DATABASE_PATH

        fname = "latest.jpg"
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT name FROM parking_lots WHERE id = ?", (lot_id,)
                ) as c:
                    row = await c.fetchone()
            if row and row["name"] and "westminster" in row["name"].lower():
                fname = "latest-lot-2.jpg"
        except Exception:
            pass

        latest = video_path / fname
        if latest.exists():
            return FileResponse(str(latest), media_type="image/jpeg", headers=_nocache_img)
        raise HTTPException(
            status_code=404,
            detail=f"Latest frame not available for lot {lot_id}. Run the AI module for this lot.",
        )

    app.mount("/media", StaticFiles(directory=str(video_path)), name="media")

@app.get("/")
async def read_root():
    index_path = frontend_path / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Smart Vision System API"}

FRONTEND_PAGES = {
    "login", "register", "dashboard", "my-cars",
    "my-reservations", "account", "admin", "slots-editor",
    "map", "lot", "payment-methods", "checkout"
}

@app.get("/{page}")
async def serve_page(page: str, request: Request):
    if page.startswith("api") or page in ("docs", "redoc", "openapi"):
        raise HTTPException(status_code=404, detail="Not found")

    if page in FRONTEND_PAGES or page.endswith(".html"):
        page_name = page.replace(".html", "")
        if page_name in FRONTEND_PAGES:
            page_path = frontend_path / f"{page_name}.html"
            if page_path.exists():
                return FileResponse(str(page_path))
    
    raise HTTPException(status_code=404, detail="Page not found")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "message": str(exc)}
    )
