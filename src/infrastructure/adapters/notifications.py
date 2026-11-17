"""User-scoped notification read service."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.application.context.identity import Actor
from src.domain.models.notifications import Notification
from src.application.dto.notifications import NotificationDTO

async def list_notifications(session: AsyncSession, user: Actor, limit: int) -> list[NotificationDTO]:
    rows = await session.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit))
    return [NotificationDTO.model_validate(row) for row in rows.all()]
