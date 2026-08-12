from __future__ import annotations

from a5.domain.models import ToolBudgetSnapshot


class ToolBudgetExceeded(RuntimeError):
    pass


class ToolBudgetManager:
    def __init__(self, max_tool_calls: int) -> None:
        if max_tool_calls < 1:
            raise ValueError("max_tool_calls must be positive")
        self.max_tool_calls = max_tool_calls
        self.used_tool_calls = 0

    @property
    def remaining_tool_calls(self) -> int:
        return self.max_tool_calls - self.used_tool_calls

    @property
    def budget_exhausted(self) -> bool:
        return self.remaining_tool_calls == 0

    def consume(self) -> ToolBudgetSnapshot:
        if self.budget_exhausted:
            raise ToolBudgetExceeded("tool budget exhausted; additional call prohibited")
        self.used_tool_calls += 1
        return self.snapshot()

    def snapshot(self) -> ToolBudgetSnapshot:
        return ToolBudgetSnapshot(
            max_tool_calls=self.max_tool_calls,
            used_tool_calls=self.used_tool_calls,
            remaining_tool_calls=self.remaining_tool_calls,
            budget_exhausted=self.budget_exhausted,
        )
