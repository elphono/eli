"""Click counting: counted in memory, written to the store in batches."""

import threading

from shorty import config, store

_pending: dict[str, int] = {}
_lock = threading.Lock()


def record(code: str) -> None:
    with _lock:
        _pending[code] = _pending.get(code, 0) + 1
        if sum(_pending.values()) < config.FLUSH_EVERY:
            return
        batch = dict(_pending)
        _pending.clear()
    store.add_clicks(batch)
