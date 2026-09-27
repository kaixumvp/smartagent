import os
import sys
from pathlib import Path

# Tests run without Redis or Postgres, so switch off the two startup paths that would reach
# for them. Must happen before any smartagent Settings instance is created (it is @lru_cache'd).
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["EVAL_SWEEP_ON_STARTUP"] = "false"

# Let pytest import the src packages without installing them (business + agent-core)
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CORE_SRC = ROOT / "ouroboros" / "src"
for path in (SRC, CORE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from sqlalchemy.sql import operators as sa_operators  # noqa: E402
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList, UnaryExpression  # noqa: E402
from sqlalchemy.sql.expression import Delete  # noqa: E402

from smartagent.db.models import AuditLog, Agent, Run, RunStep  # noqa: E402
from smartagent.iam.permission_manager import PermissionContext, Principal  # noqa: E402
from ouroboros.llm.base import LLMResponse, Usage  # noqa: E402
from ouroboros.plugins.registry import PluginRegistry  # noqa: E402
from ouroboros.tools.base import BaseTool, ToolResult  # noqa: E402
from ouroboros.tools.registry import ToolRegistry, build_default_registry  # noqa: E402


class MockLLMGateway:
    """Programmable mock LLM: pops preset responses in order."""

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self.responses: list[LLMResponse] = list(responses or [])
        self.calls: list[dict] = []

    async def chat(self, messages, model=None, tools=None) -> LLMResponse:
        self.calls.append({"messages": messages, "model": model, "tools": tools})
        if self.responses:
            return self.responses.pop(0)
        return LLMResponse(content="", usage=Usage())


class FakeBrain:
    """In-memory Working Brain so tests don't depend on Redis."""

    def __init__(self) -> None:
        self.history: dict[str, list[dict]] = {}

    async def get_history(self, session_id: str) -> list[dict]:
        return list(self.history.get(session_id, []))

    async def append(self, session_id: str, message: dict) -> None:
        self.history.setdefault(session_id, []).append(message)


class FakeMemoryManager:
    """In-memory MemoryManager facade (working history only; recall/consolidate are no-ops)."""

    def __init__(self) -> None:
        self.history: dict[str, list[dict]] = {}

    async def get_history(self, session_id: str) -> list[dict]:
        return list(self.history.get(session_id, []))

    async def write(self, session_id: str, message: dict) -> None:
        self.history.setdefault(session_id, []).append(message)

    async def recall(self, db, tenant_id, user_id, query, top_k=5):
        return []

    async def consolidate(self, db, session_id, tenant_id, user_id) -> int:
        return 0


def build_default_plugin_registry() -> PluginRegistry:
    """Wrap the builtin tools into a PluginRegistry for runtime tests."""
    registry = PluginRegistry()
    for tool in build_default_registry().all():
        registry.register_tool(tool)
    return registry


def admin_principal() -> Principal:
    return Principal(user_id="u_admin", tenant_id="default", roles=["admin"], is_admin=True)


def admin_permission_context() -> PermissionContext:
    return PermissionContext(is_admin=True, permission_codes=set(), grant_keys=set())


# --------------------------------------------------------------------------- HITL fixtures
class DeleteAccountTool(BaseTool):
    """High-risk builtin used to exercise the mid-run approval gate."""

    id = "tool_delete_account"
    name = "delete_account"
    description = "Delete a user account (high risk)"
    permission = "admin"
    parameters = {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
        "required": ["user_id"],
    }

    async def run(self, user_id: str) -> ToolResult:
        return ToolResult(success=True, output=f"deleted {user_id}")


def high_risk_tool_registry() -> ToolRegistry:
    registry = build_default_registry()
    registry.register(DeleteAccountTool())
    return registry


def operator_principal() -> Principal:
    """Non-admin caller. Admins bypass authorization outright (ouroboros.ports.check_permission),
    so approval flows can only be exercised as a non-admin."""
    return Principal(user_id="u_op", tenant_id="default", roles=["operator"], is_admin=False)


def operator_permission_context(granted: set[tuple[str, str]] = frozenset()) -> PermissionContext:
    """`granted` holds (resource_type, resource_id) pairs the operator has an allow-grant on.

    Without a grant a high-risk resource is DENY, not REQUIRE_APPROVAL — the approval gate
    only engages for resources the caller is otherwise entitled to use.
    """
    return PermissionContext(
        is_admin=False,
        permission_codes={"run:execute"},
        grant_keys={(rt, rid, "allow") for rt, rid in granted},
    )


# --------------------------------------------------------------------------- fake persistence
class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def one(self):
        return self._items[0]


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalars(self._items)

    def all(self):
        return self._items


def _bind_value(clause):
    return getattr(clause, "value", None)


def _matches(row, clause) -> bool:
    """Evaluate a WHERE clause against an in-memory object.

    Supports AND/OR of `==`, `!=` and `IN` — the shapes the routes actually use. Anything else
    is treated as matching rather than raising, so an unsupported clause shows up as extra rows
    in a test rather than an obscure crash.
    """
    if clause is None:
        return True
    if isinstance(clause, BooleanClauseList):
        results = [_matches(row, c) for c in clause.clauses]
        if clause.operator is sa_operators.or_:
            return any(results)
        return all(results)
    if isinstance(clause, BinaryExpression):
        name = getattr(clause.left, "key", None) or getattr(clause.left, "name", None)
        if name is None:
            return True
        actual = getattr(row, name, None)
        op = clause.operator
        if op is sa_operators.eq:
            return actual == _bind_value(clause.right)
        if op is sa_operators.ne:
            return actual != _bind_value(clause.right)
        if op is sa_operators.in_op:
            return actual in (_bind_value(clause.right) or [])
    return True


def _apply_order(rows: list, stmt) -> list:
    ordered = list(rows)
    for clause in reversed(getattr(stmt, "_order_by_clauses", ()) or ()):
        descending = isinstance(clause, UnaryExpression) and clause.modifier is sa_operators.desc_op
        column = clause.element if isinstance(clause, UnaryExpression) else clause
        name = getattr(column, "key", None) or getattr(column, "name", None)
        if name is None:
            continue
        ordered.sort(key=lambda r, n=name: (getattr(r, n, None) is None, getattr(r, n, None)), reverse=descending)
    return ordered


class FakeSession:
    """In-memory AsyncSession good enough for route and service tests.

    A real database is not an option here: the models use `JSONB` and pgvector `Vector`, which
    SQLite cannot compile. So this understands `select(Entity).where(...).order_by(...)` well
    enough for the queries the routes issue — see `_matches` for the supported operators.

    **Not supported: JOINs.** `rbac.load_user_role_names` joins Role to UserRole, so anything
    reading roles back through it returns an empty list here. Assert against the persisted
    `UserRole` rows instead of the response body when that matters.
    """

    def __init__(self, *seed):
        self._rows: dict[type, list] = {}
        for obj in seed:
            if obj is not None:
                self.add(obj)

    # rows by type, in insertion order
    def _bucket(self, model) -> list:
        return self._rows.setdefault(model, [])

    @property
    def agent(self) -> Agent | None:
        rows = self._rows.get(Agent, [])
        return rows[0] if rows else None

    @property
    def runs(self) -> list[Run]:
        return self._rows.get(Run, [])

    @property
    def steps(self) -> list[RunStep]:
        return sorted(self._rows.get(RunStep, []), key=lambda s: s.seq or 0)

    @property
    def audits(self) -> list[AuditLog]:
        return self._rows.get(AuditLog, [])

    def rows(self, model) -> list:
        return self._rows.get(model, [])

    async def get(self, model, ident):
        for row in self._rows.get(model, []):
            if getattr(row, "id", None) == ident:
                return row
        return None

    def add(self, obj):
        self._bucket(type(obj)).append(obj)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, obj):
        pass

    async def execute(self, stmt):
        # Core DELETE (e.g. `UserRole.__table__.delete().where(...)`) has no column_descriptions.
        # Without this branch it would fall through, delete nothing, and let "roles were
        # replaced" assertions pass while the old rows were still there.
        if isinstance(stmt, Delete):
            return _FakeResult(self._delete(stmt))

        descriptions = getattr(stmt, "column_descriptions", None) or []
        entity = descriptions[0].get("entity") if descriptions else None
        if entity is None:
            return _FakeResult([])
        rows = [r for r in self._rows.get(entity, []) if _matches(r, stmt.whereclause)]
        return _FakeResult(_apply_order(rows, stmt))

    def _delete(self, stmt) -> list:
        table_name = stmt.table.name
        for model, rows in self._rows.items():
            if getattr(model, "__tablename__", None) != table_name:
                continue
            removed = [r for r in rows if _matches(r, stmt.whereclause)]
            self._rows[model] = [r for r in rows if r not in removed]
            return removed
        return []

    async def delete(self, obj):
        bucket = self._rows.get(type(obj))
        if bucket and obj in bucket:
            bucket.remove(obj)

    async def flush(self):
        pass

    def audit_actions(self) -> list[str]:
        return [a.action for a in self.audits]


def session_factory_for(session: FakeSession):
    """Adapt a FakeSession into the `async with factory() as db` shape services expect."""

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    return lambda: _Ctx()
