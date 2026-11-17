import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.main.config import get_settings
from src.infrastructure.database.session import SessionFactory, utcnow
from src.usecase.errors import AppError
from src.domain.models.auth import RefreshToken, User
from src.usecase.context.identity import Actor

hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(hash_value: str, password: str) -> bool:
    try:
        return hasher.verify(password, hash_value)
    except UnknownHashError:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def access_token(user_id: UUID, *, session_version: int = 0, now: datetime | None = None) -> str:
    settings = get_settings()
    now = now or utcnow()
    return jwt.encode({"sub": str(user_id), "sv": session_version, "typ": "access", "iss": "ahya-expense-api", "aud": "ahya-expense-client", "iat": now, "exp": now + timedelta(seconds=settings.access_ttl_seconds)}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def read_access(token: str) -> tuple[UUID, int]:
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience="ahya-expense-client", issuer="ahya-expense-api", options={"require": ["sub", "exp", "iat", "aud", "iss"]})
        if claims.get("typ") != "access":
            raise ValueError("Wrong token type")
        return UUID(claims["sub"]), int(claims["sv"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise AppError(401, "INVALID_TOKEN", "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"}) from exc


async def resolve_actor(token: str) -> Actor:
    """Verify JWT against database session_version, then return a detached domain identity."""
    user_id, version = read_access(token)
    async with SessionFactory() as session:
        user = await session.get(User, user_id)
        if user is None or user.session_version != version:
            raise AppError(401, "INVALID_TOKEN", "Token revoked or user does not exist")
        return Actor(id=user.id, email=user.email, base_currency=user.base_currency,
                     session_version=user.session_version)


async def create_token_pair(session: AsyncSession, user: User) -> dict:
    settings = get_settings()
    opaque = secrets.token_urlsafe(48)
    session.add(RefreshToken(user_id=user.id, token_hash=hash_token(opaque), expires_at=utcnow() + timedelta(seconds=settings.refresh_ttl_seconds)))
    return {"access_token": access_token(user.id, session_version=user.session_version), "refresh_token": opaque, "token_type": "bearer", "expires_in": settings.access_ttl_seconds}


# Two Redis keys per identity: failed attempts (15-min window) and
# short-lived in-flight slots. Admission, success and failure are atomic Lua
# operations, preventing parallel requests on separate API instances from
# passing a non-atomic GET/INCR race.
LOGIN_RESERVE_LUA = """
local failed=tonumber(redis.call('GET',KEYS[1]) or '0')
local pending=tonumber(redis.call('GET',KEYS[2]) or '0')
if failed+pending>=5 then
  return {0,math.max(1,redis.call('TTL',KEYS[1]),redis.call('TTL',KEYS[2]))}
end
local n=redis.call('INCR',KEYS[2])
if n==1 then redis.call('EXPIRE',KEYS[2],60) end
return {1,0}
"""
LOGIN_COMPLETE_LUA = """
local in_flight=tonumber(redis.call('GET',KEYS[2]) or '0')
if in_flight>0 then redis.call('DECR',KEYS[2]) end
if ARGV[1]=='success' then
  redis.call('DEL',KEYS[1])
else
  local n=redis.call('INCR',KEYS[1])
  if n==1 then redis.call('EXPIRE',KEYS[1],900) end
end
return 1
"""


def _login_keys(email: str) -> tuple[str, str]:
    key = hashlib.sha256(email.lower().encode()).hexdigest()
    return "login:fail:" + key, "login:pending:" + key


async def begin_login_attempt(redis_client, email: str) -> None:
    try:
        accepted, ttl = await redis_client.eval(LOGIN_RESERVE_LUA, 2, *_login_keys(email))
    except Exception as exc:
        raise AppError(503, "RATE_LIMIT_UNAVAILABLE", "Authentication temporarily unavailable") from exc
    if not int(accepted):
        raise AppError(429, "LOGIN_RATE_LIMITED", "Too many failed attempts", headers={"Retry-After": str(max(1, int(ttl)))})


async def complete_login_attempt(redis_client, email: str, *, successful: bool):
    try:
        await redis_client.eval(LOGIN_COMPLETE_LUA, 2, *_login_keys(email), "success" if successful else "fail")
    except Exception as exc:
        raise AppError(503, "RATE_LIMIT_UNAVAILABLE", "Authentication temporarily unavailable") from exc
