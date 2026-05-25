"""Single place mapping domain exceptions -> HTTP responses.

Registered on the app at startup. Keeps endpoints and services free of HTTP
status bookkeeping — they just raise DomainError subclasses.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AuthError,
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)

_STATUS = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    AuthError: status.HTTP_401_UNAUTHORIZED,
    ValidationError: 422,  # Unprocessable; constant name churns across starlette versions
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle(_: Request, exc: DomainError) -> JSONResponse:
        code = _STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
        return JSONResponse(status_code=code, content={"detail": str(exc)})
