"""Tell the MCP gateway to re-read HANA right after a change, so the change applies there in about a second
instead of at the gateway's next periodic re-read (GATEWAY_DB_SYNC_INTERVAL, 30 s by default).

One middleware covers every route: after a successful write to servers, API keys or users, it calls the gateway's
reload route (GATEWAY_RELOAD_URL, with GATEWAY_RELOAD_SECRET) in the background, so the API response isn't held up.
If the call fails, nothing breaks: the gateway still picks the change up at its next periodic re-read.
"""

from __future__ import annotations

import asyncio
import logging
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from backend.config import get_settings

logger = logging.getLogger(__name__)

# Writes here change what the gateway serves: servers, keys, and users (deleting a user revokes their keys).
WATCHED_PREFIXES = ("/api/admin/servers", "/api/admin/keys", "/api/keys", "/api/admin/users")
CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Under a watched prefix but irrelevant to the gateway: password resets.
IGNORED_SUFFIXES = ("/password",)

_pending: set[asyncio.Task[None]] = set()  # keeps background calls alive until they finish


def _post(url: str, secret: str, timeout: float) -> None:
    request = urllib.request.Request(url, data=b"", method="POST", headers={"Authorization": f"Bearer {secret}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


async def _notify(url: str, secret: str, timeout: float, reason: str) -> None:
    try:
        await asyncio.to_thread(_post, url, secret, timeout)
        logger.info("Gateway reloaded after %s", reason)
    except urllib.error.HTTPError as exc:
        logger.warning(
            "Gateway reload after %s answered %s; it applies the change at its next periodic re-read", reason, exc.code
        )
    except Exception as exc:  # noqa: BLE001 - unreachable, timed out, ...
        logger.warning(
            "Could not reach the gateway to reload after %s (%s); it applies the change at its next periodic re-read",
            reason,
            exc,
        )


def _changes_gateway(request: Request, response: Response) -> bool:
    path = request.url.path
    return (
        request.method in CHANGING_METHODS
        and response.status_code < 400
        and path.startswith(WATCHED_PREFIXES)
        and not path.endswith(IGNORED_SUFFIXES)
    )


async def notify_gateway_on_change(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    if _changes_gateway(request, response):
        s = get_settings()
        if s.gateway_reload_url and s.gateway_reload_secret:
            reason = f"{request.method} {request.url.path}"
            task = asyncio.create_task(_notify(s.gateway_reload_url, s.gateway_reload_secret, s.gateway_reload_timeout, reason))
            _pending.add(task)
            task.add_done_callback(_pending.discard)
    return response
