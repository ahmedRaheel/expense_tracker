from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from config import get_settings
from api_version import API_V1_PREFIX
from uuid import uuid4
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
   
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield
    finally:
        await app.state.redis.aclose()

def create_app() -> FastAPI:
    app = FastAPI(title="Expense Tracker API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware,
        allow_origins=[x.strip() for x in get_settings().cors_origins.split(",")],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "If-Match", "X-Request-ID"],
        expose_headers=["ETag", "Retry-After", "X-Request-ID", "Idempotency-Replayed"])

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        header = request.headers.get("X-Request-ID", "")
        request.state.request_id = header if header and len(header) <= 64 and header.isascii() and header.isprintable() else uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.get(f"{API_V1_PREFIX}/health", tags=["Health"])
    async def health():
        return {"status": "ok"}

    
    return app

app = create_app()


