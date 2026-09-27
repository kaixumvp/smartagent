from smartagent.iam.permission_manager import PermissionContext, PermissionDecision, PermissionManager

pm = PermissionManager()


def _ctx(is_admin=False, codes=None, grants=None) -> PermissionContext:
    return PermissionContext(
        is_admin=is_admin,
        permission_codes=set(codes or []),
        grant_keys=set(grants or []),
    )


def test_admin_bypasses():
    assert pm.check(_ctx(is_admin=True), "execute", "tool", "x", "admin", True) is PermissionDecision.ALLOW


def test_read_tool_allowed_without_grant():
    assert pm.check(_ctx(codes={"run:execute"}), "execute", "tool", "calculator", "read", False) is PermissionDecision.ALLOW


def test_deny_wins_over_allow():
    ctx = _ctx(codes={"run:execute"}, grants={("tool", "db", "deny"), ("tool", "db", "allow")})
    assert pm.check(ctx, "execute", "tool", "db", "write", False) is PermissionDecision.DENY


def test_write_requires_grant():
    assert pm.check(_ctx(codes={"run:execute"}), "execute", "tool", "db", "write", False) is PermissionDecision.DENY


def test_write_allowed_with_grant():
    ctx = _ctx(codes={"run:execute"}, grants={("tool", "db", "allow")})
    assert pm.check(ctx, "execute", "tool", "db", "write", False) is PermissionDecision.ALLOW


def test_high_risk_requires_approval():
    ctx = _ctx(codes={"run:execute"}, grants={("tool", "db", "allow")})
    assert pm.check(ctx, "execute", "tool", "db", "admin", False) is PermissionDecision.REQUIRE_APPROVAL


def test_high_risk_allowed_after_approval():
    ctx = _ctx(codes={"run:execute"}, grants={("tool", "db", "allow")})
    assert pm.check(ctx, "execute", "tool", "db", "admin", False, approved={"db"}) is PermissionDecision.ALLOW


def test_missing_run_execute_denied():
    assert pm.check(_ctx(codes={}), "execute", "tool", "calculator", "read", False) is PermissionDecision.DENY
