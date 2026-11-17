"""PostgreSQL + Redis implementation of AuthenticationPort."""
import asyncio
from sqlalchemy import select, update
from src.usecase.errors import AppError
from src.usecase.dto.auth import UserDTO, TokenPair
from src.domain.models.auth import User, RefreshToken
from src.infrastructure.database.session import utcnow
from src.infrastructure.adapters.auth_security import (
    begin_login_attempt, complete_login_attempt, create_token_pair,
    hash_password, verify_password, hash_token,
)

class SqlAuthenticationAdapter:
    def __init__(self, session, redis):
        self.session, self.redis = session, redis

    async def register(self, payload):
        email = str(payload.email).lower()
        if await self.session.scalar(select(User.id).where(User.email == email)) is not None:
            raise AppError(409, "EMAIL_EXISTS", "Email already registered")
        user = User(email=email, password_hash=await asyncio.to_thread(hash_password, payload.password),
                    base_currency=payload.base_currency)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return UserDTO.model_validate(user)

    async def login(self, payload):
        email = str(payload.email).lower()
        await begin_login_attempt(self.redis, email)
        user = await self.session.scalar(select(User).where(User.email == email))
        good = await asyncio.to_thread(verify_password, user.password_hash, payload.password) if user else False
        await complete_login_attempt(self.redis, email, successful=good)
        if not good:
            raise AppError(401, "BAD_CREDENTIALS", "Invalid email or password")
        pair = await create_token_pair(self.session, user)
        await self.session.commit()
        return TokenPair.model_validate(pair)

    async def refresh(self, payload):
        async with self.session.begin():
            token = await self.session.scalar(select(RefreshToken).where(
                RefreshToken.token_hash == hash_token(payload.refresh_token)).with_for_update())
            if token is None:
                raise AppError(401, "BAD_REFRESH_TOKEN", "Invalid refresh token")
            if token.revoked_at is not None:
                await self.session.execute(update(RefreshToken).where(
                    RefreshToken.user_id == token.user_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=utcnow()))
                await self.session.execute(update(User).where(User.id == token.user_id).values(
                    session_version=User.session_version + 1))
                replay, pair = True, None
            elif token.expires_at <= utcnow():
                token.revoked_at = utcnow()
                replay, pair = False, None
            else:
                user = await self.session.get(User, token.user_id)
                token.revoked_at = utcnow()
                if user is None:
                    raise AppError(401, "BAD_REFRESH_TOKEN", "Invalid refresh token")
                pair = await create_token_pair(self.session, user)
                await self.session.flush()
                token.replaced_by = await self.session.scalar(select(RefreshToken.id).where(
                    RefreshToken.token_hash == hash_token(pair["refresh_token"])))
                replay = False
        if replay:
            raise AppError(401, "REFRESH_REUSED", "Refresh token reuse detected; all sessions revoked")
        if pair is None:
            raise AppError(401, "BAD_REFRESH_TOKEN", "Refresh token expired")
        return TokenPair.model_validate(pair)

    async def logout(self, payload, actor):
        await self.session.execute(update(RefreshToken).where(
            RefreshToken.user_id == actor.id,
            RefreshToken.token_hash == hash_token(payload.refresh_token),
            RefreshToken.revoked_at.is_(None)).values(revoked_at=utcnow()))
        await self.session.commit()
