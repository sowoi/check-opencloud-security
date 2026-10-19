"""Bound request bodies before form, JSON and MCP parsers allocate them."""

from __future__ import annotations

import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_REQUEST_BYTES = 1024 * 1024
REQUEST_BODY_SECONDS = 30


class RequestBodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH", "DELETE"}:
            await self.app(scope, receive, send)
            return

        body = bytearray()
        async def collect() -> bool:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return False
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                    raise OverflowError
                body.extend(chunk)
                if not message.get("more_body", False):
                    return True

        try:
            if not await asyncio.wait_for(collect(), timeout=REQUEST_BODY_SECONDS):
                return
        except (TimeoutError, OverflowError) as exc:
            status = 413 if isinstance(exc, OverflowError) else 408
            response = JSONResponse(
                {"detail": "The request body is too large." if status == 413 else "The request body took too long."},
                status_code=status,
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return

        delivered = False
        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
