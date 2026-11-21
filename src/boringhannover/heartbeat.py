"""Heartbeat pings to an external dead-man's-switch monitor.

The monitor lives outside the VPS, so a failed, missed or hung scheduled run
is noticed even when the host or Coolify is down. Pings carry no payload: the
ping URL is a secret and logs stay in Coolify.
"""

from __future__ import annotations

import logging
import os
import urllib.request
from typing import Literal


logger = logging.getLogger(__name__)

PING_URL_ENV = "HEALTHCHECK_PING_URL"
_TIMEOUT_SECONDS = 5
_SUFFIX = {"start": "/start", "success": "", "fail": "/fail"}


def ping(signal: Literal["start", "success", "fail"]) -> None:
    """Report run progress; delivery problems never affect the run.

    urllib instead of httpx: httpx's INFO request log would print the secret URL.
    """
    url = os.getenv(PING_URL_ENV)
    if not url:
        return
    try:
        with urllib.request.urlopen(
            url.rstrip("/") + _SUFFIX[signal], timeout=_TIMEOUT_SECONDS
        ):
            pass
    except OSError as exc:
        # Exception text can contain the URL; log the class only.
        logger.warning(
            "Run heartbeat %r not delivered (%s)", signal, type(exc).__name__
        )
