import re
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import get_settings

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CSRF_HEADER = "X-Requested-With"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id and enforces a CSRF custom-header check.

    The session lives in an HttpOnly SameSite=Strict cookie. As defense in depth,
    state-changing requests that carry that cookie must also send a custom header,
    which browsers refuse to attach cross-origin without a CORS preflight.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else f"req_{uuid.uuid4().hex}"
        request.state.request_id = request_id

        settings = get_settings()
        if (
            request.method not in _SAFE_METHODS
            and settings.session_cookie_name in request.cookies
            and not request.headers.get(CSRF_HEADER)
        ):
            response: Response = JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "CSRF_HEADER_MISSING",
                        "message": f"Missing {CSRF_HEADER} header",
                        "details": None,
                        "request_id": request_id,
                    }
                },
            )
        else:
            response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        return response
