"""Bound streamed request bodies, including requests without Content-Length."""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from .receipts import MAX_IMAGE_BYTES


class RequestBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        multipart = headers.get(b"content-type", b"").lower().startswith(b"multipart/form-data")
        limit = MAX_IMAGE_BYTES + 65536 if multipart else 128 * 1024
        size = headers.get(b"content-length")
        if size and (not size.isdigit() or int(size) > limit):
            return await JSONResponse({"detail": "Żądanie jest za duże."}, status_code=413)(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(413, "Żądanie jest za duże.")
            return message

        await self.app(scope, bounded_receive, send)
