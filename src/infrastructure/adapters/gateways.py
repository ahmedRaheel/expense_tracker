from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from src.usecase.context.identity import CurrentUser
from src.usecase.dto.expenses import ExpenseCreate, ExpensePatch
from src.infrastructure.adapters import categories, expenses, reports, notifications

class SqlCategoryAdapter:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, actor, payload):
        return await categories.create_category(self.session, actor, payload)

    async def list(self, actor):
        return await categories.list_categories(self.session, actor)

class SqlExpenseAdapter:
    def __init__(self, session: AsyncSession, redis):
        self.session, self.redis = session, redis

    async def create(self, actor, payload, key):
        return await expenses.create_expense(self.session, actor, payload, key, self.redis)

    async def get(self, actor, expense_id):
        return await expenses.get_expense(self.session, actor, expense_id)

    async def list(self, actor, **kwargs):
        return await expenses.list_expenses(self.session, actor, **kwargs)

    async def update(self, actor, expense_id, version, payload):
        return await expenses.update_expense(self.session, actor, expense_id, version, payload, self.redis)

    async def delete(self, actor, expense_id):
        await expenses.delete_expense(self.session, actor, expense_id, self.redis)

class SqlReportAdapter:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def monthly(self, actor, year, month):
        return await reports.build_monthly_report(self.session, actor, year, month)

class SqlNotificationAdapter:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, actor, limit):
        return await notifications.list_notifications(self.session, actor, limit)
