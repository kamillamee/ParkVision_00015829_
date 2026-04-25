"""Quick schema / data inspector for parking_slots."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "database" / "parking.db"

c = sqlite3.connect(str(DB))
print("--- DDL ---")
for r in c.execute("SELECT sql FROM sqlite_master WHERE name='parking_slots'"):
    print(r[0])
print("--- UNIQUE indexes ---")
for r in c.execute("PRAGMA index_list(parking_slots)"):
    if r[2]:  # unique flag
        cols = [ic[2] for ic in c.execute(f"PRAGMA index_info({r[1]})").fetchall()]
        print(f"{r[1]}  UNIQUE({', '.join(cols)})")
print("--- rows ---")
for r in c.execute("SELECT lot_id, slot_number, zone, is_occupied FROM parking_slots ORDER BY lot_id, slot_number"):
    print(r)
c.close()
