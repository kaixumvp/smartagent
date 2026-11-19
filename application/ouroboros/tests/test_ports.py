from ouroboros.ports import (
    JudgeVerdict,
    MemoryEntry,
    PermissionContext,
    PermissionDecision,
    PluginManifest,
    Principal,
    check_permission,
    check_plugin_permission,
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


def test_action_specific_grants_are_enforced():
    ctx = PermissionContext(
        permission_codes={"run:execute"},
        grant_actions={("tool", "tool-1", "execute", "allow")},
    )
    assert check_permission(ctx, "execute", "tool", "tool-1", "read") is PermissionDecision.ALLOW
    assert check_permission(ctx, "read", "tool", "tool-1", "read") is PermissionDecision.DENY


def test_action_specific_deny_overrides_allow():
    ctx = PermissionContext(
        permission_codes={"run:execute"},
        grant_actions={
            ("tool", "tool-1", "execute", "allow"),
            ("tool", "tool-1", "execute", "deny"),
        },
    )
    assert check_permission(ctx, "execute", "tool", "tool-1", "read") is PermissionDecision.DENY


def test_plugin_permission_falls_back_to_legacy_name_grant():
    class Checker:
        resource_ids = []

        def check(self, ctx, action, resource_type, resource_id, **kwargs):
            self.resource_ids.append(resource_id)
            return check_permission(ctx, action, resource_type, resource_id, **kwargs)

    checker = Checker()
    ctx = PermissionContext(
        permission_codes={"run:execute"},
        grant_keys={("tool", "delete_account", "allow")},
    )
    manifest = PluginManifest(
        name="delete_account",
        resource_id="tool_delete_account",
        kind="tool",
        permission="admin",
    )
    assert check_plugin_permission(checker, ctx, manifest) is PermissionDecision.REQUIRE_APPROVAL
    assert check_plugin_permission(
        checker, ctx, manifest, approved={"tool_delete_account"}
    ) is PermissionDecision.ALLOW
    assert checker.resource_ids == ["delete_account", "delete_account"]


def test_stable_plugin_deny_is_not_overridden_by_legacy_name_allow():
    class Checker:
        def check(self, ctx, action, resource_type, resource_id, **kwargs):
            return check_permission(ctx, action, resource_type, resource_id, **kwargs)

    ctx = PermissionContext(
        permission_codes={"run:execute"},
        grant_keys={
            ("tool", "delete_account", "allow"),
            ("tool", "tool_delete_account", "deny"),
        },
    )
    manifest = PluginManifest(
        name="delete_account",
        resource_id="tool_delete_account",
        kind="tool",
    )
    assert check_plugin_permission(Checker(), ctx, manifest) is PermissionDecision.DENY


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
