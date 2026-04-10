"""
Sensor emulator: sends random (or deterministic) occupancy readings to the backend.
Simulates ultrasonic/IR sensors per slot. Run with backend running on default port.

Usage:
  python tools/sensor_emulator.py
  python tools/sensor_emulator.py --interval 2 --source ultrasonic
"""
import argparse
import random
import time
import requests
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "http://127.0.0.1:8000"
SLOTS_CONFIG = ROOT / "config" / "slots.json"


def load_slot_numbers():
    """Load slot numbers from config or API."""
    if SLOTS_CONFIG.exists():
        import json
        with open(SLOTS_CONFIG, "r", encoding="utf-8") as f:
            return list(json.load(f).keys())
    try:
        r = requests.get(f"{DEFAULT_URL}/api/slots/status", timeout=3)
        if r.ok:
            return [s["slot_number"] for s in r.json()]
    except Exception:
        pass
    return ["A1", "A2", "A3", "B1", "B2", "B3"]


def send_readings(base_url: str, slot_numbers: list, source: str):
    """Send one batch of random sensor readings."""
    readings = [
        {
            "slot_number": sn,
            "source": source,
            "is_occupied": random.choice([True, False]),
        }
        for sn in slot_numbers
    ]
    try:
        r = requests.post(
            f"{base_url}/api/sensors/readings",
            json={"readings": readings},
            timeout=5,
        )
        if r.ok:
            data = r.json()
            print(f"  OK: {data.get('updated_count', 0)} slots updated from {source}")
        else:
            print(f"  WARN: {r.status_code} {r.text[:80]}")
    except requests.exceptions.ConnectionError:
        print("  WARN: Backend not reachable. Is the server running?")
    except Exception as e:
        print(f"  WARN: {e}")


def main():
    parser = argparse.ArgumentParser(description="Smart Vision sensor emulator")
    parser.add_argument("--url", default=DEFAULT_URL, help="Backend base URL")
    parser.add_argument("--interval", type=float, default=3.0, help="Seconds between batches")
    parser.add_argument("--source", default="ultrasonic", help="Sensor source name (e.g. ultrasonic, ir)")
    parser.add_argument("--once", action="store_true", help="Send one batch and exit")
    args = parser.parse_args()

    slot_numbers = load_slot_numbers()
    print(f"Sensor emulator: {len(slot_numbers)} slots, source={args.source}, interval={args.interval}s")
    print(f"Backend: {args.url}")
    print("Press Ctrl+C to stop.\n")

    while True:
        print(f"[{time.strftime('%H:%M:%S')}] Sending sensor readings...")
        send_readings(args.url, slot_numbers, args.source)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
