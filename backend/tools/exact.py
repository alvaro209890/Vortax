from typing import Any

from services.exact_solver import solve_exact_problem


class ExactTool:
    async def solve(
        self,
        problem: str,
        context: str = "",
        task_id: str | None = None,
    ) -> dict[str, Any]:
        _ = task_id
        return solve_exact_problem(problem, context=context)


exact_tool = ExactTool()
