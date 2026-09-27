from src.ports import (
    JudgeVerdict,
    MemoryEntry,
    PermissionContext,
    PermissionDecision,
    Principal,
    check_permission,
)


def _ctx(is_admin=False, codes=None, grants=None) -> PermissionContext:
    return PermissionContext(
        is_admin=is_admin,
        permission_codes=set(codes or []),
        grant_keys=set(grants or []),
    )


def test_admin_bypasses():
    assert check_permission(_ctx(is_admin=True), "execute", "tool", "x", "admin", True) is PermissionDecision.ALLOW


def test_read_tool_allowed_without_grant():
    assert check_permission(_ctx(codes={"run:execute"}), "execute", "tool", "calculator", "read", False) is PermissionDecision.ALLOW


def test_deny_wins_over_allow():
    ctx = _ctx(codes={"run:execute"}, grants={("tool", "db", "deny"), ("tool", "db", "allow")})
    assert check_permission(ctx, "execute", "tool", "db", "write", False) is PermissionDecision.DENY


def test_write_requires_grant():
    assert check_permission(_ctx(codes={"run:execute"}), "execute", "tool", "db", "write", False) is PermissionDecision.DENY


def test_write_allowed_with_grant():
    ctx = _ctx(codes={"run:execute"}, grants={("tool", "db", "allow")})
    assert check_permission(ctx, "execute", "tool", "db", "write", False) is PermissionDecision.ALLOW


def test_high_risk_requires_approval():
    ctx = _ctx(codes={"run:execute"}, grants={("tool", "db", "allow")})
    assert check_permission(ctx, "execute", "tool", "db", "admin", False) is PermissionDecision.REQUIRE_APPROVAL


def test_high_risk_allowed_after_approval():
    ctx = _ctx(codes={"run:execute"}, grants={("tool", "db", "allow")})
    assert check_permission(ctx, "execute", "tool", "db", "admin", False, approved={"db"}) is PermissionDecision.ALLOW


def test_missing_run_execute_denied():
    assert check_permission(_ctx(codes={}), "execute", "tool", "calculator", "read", False) is PermissionDecision.DENY


def test_principal_defaults():
    p = Principal(user_id="u1", tenant_id="t1")
    assert p.roles == []
    assert p.is_admin is False


def test_memory_entry_defaults():
    m = MemoryEntry(id="m1", tenant_id="t1", content="hi")
    assert m.importance == 0.5
    assert m.confidence == 0.5
    assert m.source == "vector"
    assert m.similarity is None


def test_permission_decision_values():
    assert PermissionDecision.ALLOW.value == "allow"
    assert PermissionDecision.DENY.value == "deny"
    assert PermissionDecision.REQUIRE_APPROVAL.value == "require_approval"


def test_judge_verdict_defaults():
    v = JudgeVerdict()
    assert v.score == 0.0
    assert v.passed is False
    assert v.reason == ""
