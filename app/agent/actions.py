"""Undo log: every change the agent makes is recorded with what is needed to reverse it.

Stored in the database (`agent_actions`), so ↩️ Undo still works after a restart.
"""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentAction, utcnow
from app.services.expenses import ExpenseService
from app.services.reminders import ReminderService
from app.services.settings import SettingsService


class ActionLog:
    def __init__(
        self,
        session: AsyncSession,
        expenses: ExpenseService,
        reminders: ReminderService,
        settings: SettingsService,
    ) -> None:
        self.session = session
        self.expenses = expenses
        self.reminders = reminders
        self.settings = settings

    async def record(self, kind: str, payload: dict, summary: str) -> AgentAction:
        action = AgentAction(
            kind=kind, payload=json.dumps(payload, ensure_ascii=False), summary=summary
        )
        self.session.add(action)
        await self.session.commit()
        return action

    async def get(self, action_id: int) -> AgentAction | None:
        return await self.session.get(AgentAction, action_id)

    @staticmethod
    def payload(action: AgentAction) -> dict:
        return json.loads(action.payload)

    async def undo(self, action_id: int) -> AgentAction | None:
        """Reverse an action. None if it doesn't exist or was already undone."""
        action = await self.get(action_id)
        if action is None or action.undone_at is not None:
            return None
        data = self.payload(action)
        match action.kind:
            case "expenses_added":
                await self.expenses.delete(data["ids"])
            case "expenses_deleted":
                await self.expenses.restore(data["rows"])
            case "expense_updated":
                await self.expenses.restore([data["previous"]])
            case "reminder_created":
                await self.reminders.delete(data["id"])
            case "reminders_cancelled":
                await self.reminders.set_status(data["ids"], "active")
            case "reminder_updated":
                await self.reminders.restore(data["snapshot"])
            case "settings_updated":
                for key, value in data["previous"].items():
                    if value is None:
                        await self.settings.unset(key)
                    else:
                        await self.settings.set(key, value)
            case _:
                return None
        action.undone_at = utcnow()
        await self.session.commit()
        return action
