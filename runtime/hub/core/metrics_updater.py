"""
Background metrics updater for derived metrics.
"""

import threading
import time
from contextlib import suppress

from core.metrics import hub_active_sessions
from core.quota import get_quota_manager

UPDATE_INTERVAL = 15


def _update_once(quota_manager):
    try:
        count = quota_manager.get_active_sessions_count()
        hub_active_sessions.set(count)
    except Exception:
        # keep metric present even if quota manager fails
        hub_active_sessions.set(0)


def _update_loop():
    quota_manager = get_quota_manager()

    # run once immediately so the metric exists
    _update_once(quota_manager)

    while True:
        _update_once(quota_manager)
        time.sleep(UPDATE_INTERVAL)


def start_metrics_updater():
    # ensure metric exists even before first loop tick
    with suppress(Exception):
        hub_active_sessions.set(0)

    t = threading.Thread(target=_update_loop, daemon=True)
    t.start()
