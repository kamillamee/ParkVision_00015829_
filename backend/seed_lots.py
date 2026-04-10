"""Seed parking lots for Uzbekistan (Tashkent, Samarkand, Bukhara)"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import aiosqlite
from backend.database import init_db
from backend.config import DATABASE_PATH

# Uzbekistan parking lots: (name, address, lat, lng, is_live)
# is_live=1: real-time video/slots (demo), is_live=0: coming soon
UZBEKISTAN_LOTS = [
    ("British School of Tashkent — parking", "British School of Tashkent, Yunusobod, Tashkent", 41.3670, 69.2720, 1),
    ("Westminster University Parking", "Westminster International University in Tashkent", 41.3280, 69.2885, 1),
    ("Chorsu Parking", "Toshkent, Chorsu bozori", 41.3237, 69.2381, 0),
    ("Samarqand Central", "Samarqand sh., Registon", 39.6544, 66.9758, 0),
    ("Bukhara Old City", "Buxoro, Lyabi-Hauz", 39.7753, 64.4239, 0),
]


async def seed_lots():
    """Seed parking lots with Uzbekistan coordinates (skip if already exists)"""
    await init_db()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        added = 0
        for name, address, lat, lng, is_live in UZBEKISTAN_LOTS:
            async with db.execute(
                "SELECT 1 FROM parking_lots WHERE name = ? LIMIT 1", (name,)
            ) as c:
                if await c.fetchone():
                    continue
            try:
                await db.execute(
                    "INSERT INTO parking_lots (name, address, latitude, longitude, is_live) VALUES (?, ?, ?, ?, ?)",
                    (name, address, lat, lng, is_live),
                )
            except Exception:
                await db.execute(
                    "INSERT INTO parking_lots (name, address, latitude, longitude) VALUES (?, ?, ?, ?)",
                    (name, address, lat, lng),
                )
            added += 1
        await db.execute(
            "UPDATE parking_lots SET is_live = 1 WHERE name LIKE '%British School%' OR name LIKE '%Westminster%'"
        )
        await db.commit()
    print(f"OK: Added {added} parking lots in Uzbekistan")


if __name__ == "__main__":
    asyncio.run(seed_lots())
