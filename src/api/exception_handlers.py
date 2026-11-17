import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)


from usecase.errors import AppError


def response(request: Request, status: int, code: str, message: str, details=None, headers=None):
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or []}, "request_id": getattr(request.state, "request_id", None)},
        headers=headers,
    )


def install_exception_handlers(app: FastAPI):
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return response(request, exc.status, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(map(str, x["loc"])), "reason": x["msg"]} for x in exc.errors()]
        return response(request, 422, "VALIDATION_ERROR", "Invalid request", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return response(request, exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail), headers=exc.headers)

    @app.exception_handler(IntegrityError)
    async def db_integrity(request: Request, exc: IntegrityError):
        log.warning("Database constraint violation: %s", type(exc.orig).__name__)
        return response(request, 409, "CONFLICT", "Database constraint violation")

    @app.exception_handler(Exception)
    async def unknown_error(request: Request, exc: Exception):
        log.exception("Unexpected error request_id=%s", getattr(request.state, "request_id", "unknown"))
        return response(request, 500, "INTERNAL_ERROR", "Unexpected server error")
