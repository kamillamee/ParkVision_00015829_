"""Quick script to seed parking slots - run this if slots are missing"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.seed_slots import main

if __name__ == "__main__":
    print("=" * 60)
    print("Seeding Parking Slots")
    print("=" * 60)
    print()
    asyncio.run(main())
