"""权限与 HITL：高危操作暂停 → 人工审批 → 同一 run 内 resume 续跑。

要点：
- 权限判定是纯逻辑（check_permission），数据（PermissionContext）由宿主预加载。
- 高危插件（permission="admin"）执行前返回 REQUIRE_APPROVAL → run 暂停为 awaiting_human。
- 经 Checkpointer 端口保存状态；宿主审批后调用 resume(approvals) 在同一 run 续跑。
运行：``python example/permissions_hitl.py``
"""

import asyncio

from src import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
from src.core.checkpointer import InMemoryCheckpointer
from src.plugins.registry import PluginRegistry
from src.ports import PermissionContext, PermissionDecision, check_permission
from src.tools.base import BaseTool, ToolResult

from _shared import ScriptedLLM, finish, plan, tool_call


class DeleteAccountTool(BaseTool):
    """高危工具：permission="admin"，执行前必须人工审批。"""

    name = "delete_account"
    description = "删除用户账号（高危，需审批）"
    permission = "admin"
    parameters = {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
        "required": ["user_id"],
    }

    async def run(self, user_id: str) -> ToolResult:
        return ToolResult(success=True, output=f"已删除账号 {user_id}")


class BusinessPermissionManager:
    """宿主实现：把纯函数 check_permission 包装成 PermissionChecker 端口。"""

    def check(self, ctx, action, resource_type, resource_id,
              resource_permission="read", requires_approval=False, approved=None) -> PermissionDecision:
        return check_permission(ctx, action, resource_type, resource_id,
                                resource_permission, requires_approval, approved)


async def main() -> None:
    registry = PluginRegistry()
    registry.register_tool(DeleteAccountTool())

    llm = ScriptedLLM([
        plan("删除账号 u42"),
        tool_call("delete_account", {"user_id": "u42"}),
        finish("账号 u42 已删除。"),
    ])

    # 权限上下文：有 run:execute 功能权限 + 对 delete_account 的 allow 授权（但 admin 仍需审批）
    permission_context = PermissionContext(
        permission_codes={"run:execute"},
        grant_keys={("tool", "delete_account", "allow")},
    )
    checkpointer = InMemoryCheckpointer()
    deps = RuntimeDeps(
        llm=llm,
        permission_checker=BusinessPermissionManager(),
        permission_context=permission_context,
        checkpointer=checkpointer,
    )
    definition = AgentDefinition(model="mock-model", system_prompt="你是管理员助手", plugins=registry.all())

    rt = AgentRuntime()

    # 1. 首次运行：命中高危 → 暂停
    paused = await rt.run(definition, "删除账号 u42", RunContext(run_id="run-1"), deps)
    print("首次运行:", paused.status, "待审批:", paused.pending_approvals)

    # 2. 人工审批通过 → 在同一 run 续跑（resume 复用 checkpoint）
    resumed = await rt.resume(definition, "run-1", ["delete_account"], deps)
    print("审批后续跑:", resumed.status, "结果:", resumed.result)
    print("完整步骤:", [s.node for s in resumed.steps])


if __name__ == "__main__":
    asyncio.run(main())
