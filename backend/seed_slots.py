"""Seed parking slots into database (British School lot + Westminster lot)"""
import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import init_db
import aiosqlite
from backend.config import DATABASE_PATH, SLOTS_CONFIG, SLOTS_CONFIG_WEST


async def seed_slots():
    """Seed parking slots from config files (lot 1: slots.json, lot 2: slots-west.json)."""
    lot1_id = None
    lot2_id = None

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            async with db.execute(
                "SELECT id FROM parking_lots WHERE name LIKE '%British School%' LIMIT 1"
            ) as c:
                row = await c.fetchone()
                if row:
                    lot1_id = row["id"]
        except Exception:
            pass
        if lot1_id is None:
            try:
                async with db.execute("SELECT id FROM parking_lots ORDER BY id LIMIT 1") as c:
                    row = await c.fetchone()
                    if row:
                        lot1_id = row["id"]
            except Exception:
                pass

        try:
            async with db.execute(
                "SELECT id FROM parking_lots WHERE name LIKE '%Westminster%' LIMIT 1"
            ) as c:
                row = await c.fetchone()
                if row:
                    lot2_id = row["id"]
        except Exception:
            pass

        async with db.execute("DELETE FROM parking_slots"):
            pass

        n = 0
        if lot1_id is not None and SLOTS_CONFIG.exists():
            with open(SLOTS_CONFIG, "r", encoding="utf-8") as f:
                slots_data = json.load(f)
            for slot_number, _polygon in slots_data.items():
                zone = slot_number[0]
                await db.execute(
                    """INSERT INTO parking_slots (slot_number, zone, is_occupied, lot_id)
                       VALUES (?, ?, 0, ?)""",
                    (slot_number, zone, lot1_id),
                )
                n += 1

        if lot2_id is not None and SLOTS_CONFIG_WEST.exists():
            with open(SLOTS_CONFIG_WEST, "r", encoding="utf-8") as f:
                west_data = json.load(f)
            for slot_number, _polygon in west_data.items():
                zone = slot_number[0]
                await db.execute(
                    """INSERT INTO parking_slots (slot_number, zone, is_occupied, lot_id)
                       VALUES (?, ?, 0, ?)""",
                    (slot_number, zone, lot2_id),
                )
                n += 1

        await db.commit()
        print(f"OK: Seeded {n} parking slots (lot1={lot1_id}, lot2={lot2_id})")


async def main():
    print("INFO: Seeding parking slots...")
    await init_db()
    await seed_slots()
    print("OK: Seeding complete.")


if __name__ == "__main__":
    asyncio.run(main())
