import pytest
from pydantic import ValidationError

from smartagent.api.schemas import GrantCreateRequest
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


def test_action_grant_allows_only_the_granted_action():
    ctx = PermissionContext(
        permission_codes={"run:execute"},
        grant_actions={("tool", "tool-1", "execute", "allow")},
    )
    assert pm.check(ctx, "execute", "tool", "tool-1", "read") is PermissionDecision.ALLOW
    assert pm.check(ctx, "read", "tool", "tool-1", "read") is PermissionDecision.DENY


def test_action_specific_deny_overrides_action_allow():
    ctx = PermissionContext(
        permission_codes={"run:execute"},
        grant_actions={
            ("tool", "tool-1", "execute", "allow"),
            ("tool", "tool-1", "execute", "deny"),
        },
    )
    assert pm.check(ctx, "execute", "tool", "tool-1", "read") is PermissionDecision.DENY


def test_action_grants_override_legacy_resource_grant():
    ctx = PermissionContext(
        permission_codes={"run:execute"},
        grant_keys={("tool", "tool-1", "allow")},
        grant_actions={("tool", "tool-1", "read", "allow")},
    )
    assert pm.check(ctx, "execute", "tool", "tool-1", "read") is PermissionDecision.DENY


def test_grant_api_only_accepts_currently_enforced_action():
    request = GrantCreateRequest(
        principal_type="user",
        principal_id="user-1",
        resource_type="tool",
        resource_id="tool-1",
    )
    assert request.action == "execute"

    with pytest.raises(ValidationError):
        GrantCreateRequest(
            principal_type="user",
            principal_id="user-1",
            resource_type="tool",
            resource_id="tool-1",
            action="write",
        )
