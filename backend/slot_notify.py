"""Cross-thread notifier for slot-status changes.

The vision worker runs in a plain ``threading.Thread`` but SSE subscribers
live on the FastAPI event loop. ``notify_slot_changed`` is safe to call from
either side — it schedules ``asyncio.Event.set`` on each subscriber via
``call_soon_threadsafe``.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Optional, Set

_subscribers: Set[asyncio.Event] = set()
_lock = threading.Lock()
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def subscribe() -> asyncio.Event:
    ev = asyncio.Event()
    with _lock:
        _subscribers.add(ev)
    return ev


def unsubscribe(ev: asyncio.Event) -> None:
    with _lock:
        _subscribers.discard(ev)


def notify_slot_changed() -> None:
    loop = _main_loop
    if loop is None:
        return
    with _lock:
        events = list(_subscribers)
    for ev in events:
        try:
            loop.call_soon_threadsafe(ev.set)
        except RuntimeError:
            pass
