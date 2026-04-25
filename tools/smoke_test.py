"""Smoke test: hit the running ParkVision API and MJPEG streams."""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def get_json(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return r.status, json.loads(r.read())


def head_stream(path, max_bytes=16 * 1024):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        buf = r.read(max_bytes)
        return r.status, len(buf), r.headers.get("Content-Type")


def main():
    print(f"--- GET / ---")
    with urllib.request.urlopen(BASE + "/", timeout=5) as r:
        html = r.read()
    print(f"  status={r.status} bytes={len(html)}")

    print(f"--- GET /api/lots ---")
    st, lots = get_json("/api/lots")
    print(f"  status={st} lot_count={len(lots)}")
    for lot in lots:
        print(f"  lot_id={lot['id']} name={lot['name']!r} is_live={lot.get('is_live')}")

    print(f"--- GET /api/slots/status ---")
    st, slots = get_json("/api/slots/status")
    print(f"  status={st} rows={len(slots)}")
    for s in slots:
        print(
            f"  lot={s['lot_id']}  {s['slot_number']}  "
            f"{'OCC' if s['is_occupied'] else 'free'}  "
            f"upd={(s['last_updated'] or '')[:19]}"
        )

    print(f"--- GET /api/slots/stats?lot_id=1 ---")
    st, stats1 = get_json("/api/slots/stats?lot_id=1")
    print(f"  status={st}  {stats1}")

    print(f"--- GET /api/slots/stats?lot_id=2 ---")
    st, stats2 = get_json("/api/slots/stats?lot_id=2")
    print(f"  status={st}  {stats2}")

    print(f"--- GET /api/slots/config?lot_id=1 ---")
    st, cfg1 = get_json("/api/slots/config?lot_id=1")
    print(f"  status={st}  keys={list(cfg1.keys())}")

    print(f"--- GET /api/slots/config?lot_id=2 ---")
    st, cfg2 = get_json("/api/slots/config?lot_id=2")
    print(f"  status={st}  keys={list(cfg2.keys())}")

    for lot in (1, 2):
        try:
            print(f"--- GET /api/stream/mjpeg/{lot} (first 16KB) ---")
            st, got, ct = head_stream(f"/api/stream/mjpeg/{lot}")
            print(f"  status={st}  bytes_read={got}  content-type={ct}")
        except Exception as e:
            print(f"  FAILED: {e}")

        try:
            print(f"--- GET /api/stream/frame/{lot} ---")
            with urllib.request.urlopen(BASE + f"/api/stream/frame/{lot}", timeout=5) as r:
                body = r.read()
            print(f"  status={r.status}  bytes={len(body)}  content-type={r.headers.get('Content-Type')}")
        except Exception as e:
            print(f"  FAILED: {e}")

        try:
            print(f"--- GET /api/stream/frame/{lot}/meta ---")
            st, meta = get_json(f"/api/stream/frame/{lot}/meta")
            print(f"  status={st}  {meta}")
        except Exception as e:
            print(f"  FAILED: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
