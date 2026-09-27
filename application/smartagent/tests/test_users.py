"""User administration and password rotation.

Covers the gap that made this feature necessary: before it, `admin`/`admin123` from Alembic
0002 was the only account in the system, and its password could only be changed with direct
database access.
"""

from fastapi.testclient import TestClient

from conftest import FakeSession, admin_principal, admin_permission_context
from smartagent.api.security import get_current_user, get_permission_context, hash_password
from smartagent.db.models import Role, User, UserRole
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import PermissionContext, Principal
from smartagent.main import app


def _admin_user() -> User:
    return User(
        id="u_admin", tenant_id="default", name="Admin", username="admin",
        password_hash=hash_password("admin123"), status="active",
    )


def _roles() -> list[Role]:
    return [
        Role(id="role_admin", tenant_id="default", name="admin", is_builtin=True),
        Role(id="role_operator", tenant_id="default", name="operator", is_builtin=True),
        Role(id="role_viewer", tenant_id="default", name="viewer", is_builtin=True),
    ]


def _install(db, principal=None, perm_ctx=None):
    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: principal or admin_principal()
    app.dependency_overrides[get_permission_context] = lambda: perm_ctx or admin_permission_context()


def _seeded(*extra) -> FakeSession:
    return FakeSession(_admin_user(), *_roles(), *extra)


# --------------------------------------------------------------------------- create
def test_create_user_binds_roles_and_hides_the_hash():
    db = _seeded()
    _install(db)
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/v1/users",
                json={"username": "alice", "password": "s3cret-pass", "roles": ["operator"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "alice"
    assert data["roles"] == ["operator"]
    assert data["status"] == "active"
    assert "password_hash" not in data and "password" not in data

    created = next(u for u in db.rows(User) if u.username == "alice")
    assert created.password_hash != "s3cret-pass"  # stored hashed, never in the clear
    assert [ur.role_id for ur in db.rows(UserRole) if ur.user_id == created.id] == ["role_operator"]


def test_create_user_rejects_unknown_role():
    """`roles.py::_bind_permissions` drops unresolved names silently; this must not — a typo
    would otherwise produce an account with fewer permissions than intended, with no signal."""
    db = _seeded()
    _install(db)
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/v1/users",
                json={"username": "bob", "password": "s3cret-pass", "roles": ["operatr"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 400
    assert "operatr" in resp.json()["error"]["message"]
    assert not [u for u in db.rows(User) if u.username == "bob"]


def test_create_user_rejects_short_password():
    db = _seeded()
    _install(db)
    try:
        with TestClient(app) as client:
            resp = client.post("/v1/users", json={"username": "bob", "password": "short"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_ARGUMENT"


# --------------------------------------------------------------------------- read / update
def test_cross_tenant_user_is_404_not_403():
    """403 would confirm the account exists in another tenant."""
    other = User(
        id="u_other", tenant_id="t2", name="Other", username="other",
        password_hash=hash_password("whatever1"), status="active",
    )
    db = _seeded(other)
    _install(db)
    try:
        with TestClient(app) as client:
            resp = client.get("/v1/users/u_other")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_update_replaces_the_whole_role_set():
    alice = User(
        id="u_alice", tenant_id="default", name="Alice", username="alice",
        password_hash=hash_password("s3cret-pass"), status="active",
    )
    db = _seeded(alice, UserRole(user_id="u_alice", role_id="role_operator"))
    _install(db)
    try:
        with TestClient(app) as client:
            resp = client.patch("/v1/users/u_alice", json={"roles": ["viewer"]})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    # Asserted against persisted state rather than the response body: rendering `roles` on read
    # goes through `rbac.load_user_role_names`, which is a JOIN, and FakeSession does not do
    # JOINs. The rows below are the real evidence anyway — the old binding is gone, not merely
    # shadowed by a new one.
    assert [ur.role_id for ur in db.rows(UserRole) if ur.user_id == "u_alice"] == ["role_viewer"]


def test_disabling_a_user_blocks_their_login():
    alice = User(
        id="u_alice", tenant_id="default", name="Alice", username="alice",
        password_hash=hash_password("s3cret-pass"), status="active",
    )
    db = _seeded(alice)
    _install(db)
    try:
        with TestClient(app) as client:
            assert client.patch("/v1/users/u_alice", json={"status": "disabled"}).status_code == 200
            # `login` filters on status == "active", so a disabled account cannot authenticate.
            login = client.post("/v1/auth/login", json={"username": "alice", "password": "s3cret-pass"})
    finally:
        app.dependency_overrides.clear()

    assert login.status_code == 401


def test_cannot_disable_your_own_account():
    """Self-lockout is unrecoverable without a second admin or database access."""
    db = _seeded()
    _install(db, principal=Principal(user_id="u_admin", tenant_id="default", roles=["admin"], is_admin=True))
    try:
        with TestClient(app) as client:
            resp = client.patch("/v1/users/u_admin", json={"status": "disabled"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 400
    assert "your own account" in resp.json()["error"]["message"]
    assert db.rows(User)[0].status == "active"


# --------------------------------------------------------------------------- passwords
def test_change_password_requires_the_current_one():
    db = _seeded()
    _install(db, principal=Principal(user_id="u_admin", tenant_id="default", roles=["admin"], is_admin=True))
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/v1/auth/change-password",
                json={"current_password": "wrong-one", "new_password": "brand-new-pass"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 401
    # Password unchanged: the old one still verifies.
    from smartagent.api.security import verify_password

    assert verify_password("admin123", db.rows(User)[0].password_hash)


def test_change_password_rotates_the_credential():
    db = _seeded()
    _install(db, principal=Principal(user_id="u_admin", tenant_id="default", roles=["admin"], is_admin=True))
    try:
        with TestClient(app) as client:
            changed = client.post(
                "/v1/auth/change-password",
                json={"current_password": "admin123", "new_password": "brand-new-pass"},
            )
            old = client.post("/v1/auth/login", json={"username": "admin", "password": "admin123"})
            new = client.post("/v1/auth/login", json={"username": "admin", "password": "brand-new-pass"})
    finally:
        app.dependency_overrides.clear()

    assert changed.status_code == 204
    assert old.status_code == 401       # the seeded default no longer works
    assert new.status_code == 200
    assert new.json()["access_token"]


def test_admin_reset_needs_no_current_password():
    """The only recovery path for a forgotten password — there is no email delivery."""
    alice = User(
        id="u_alice", tenant_id="default", name="Alice", username="alice",
        password_hash=hash_password("forgotten-one"), status="active",
    )
    db = _seeded(alice)
    _install(db)
    try:
        with TestClient(app) as client:
            resp = client.post("/v1/users/u_alice/password", json={"new_password": "reset-by-admin"})
            login = client.post("/v1/auth/login", json={"username": "alice", "password": "reset-by-admin"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert login.status_code == 200


# --------------------------------------------------------------------------- authorization
def test_user_management_requires_the_permission():
    db = _seeded()
    _install(
        db,
        principal=Principal(user_id="u_op", tenant_id="default", roles=["operator"], is_admin=False),
        perm_ctx=PermissionContext(is_admin=False, permission_codes={"run:execute"}, grant_keys=set()),
    )
    try:
        with TestClient(app) as client:
            resp = client.post("/v1/users", json={"username": "mallory", "password": "s3cret-pass"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"
    assert "permission.check" in db.audit_actions()  # the refusal is on the record


def test_user_management_is_delegable_without_admin():
    """The point of guarding with `user:manage` instead of `require_admin`: a non-admin role
    holding the code can administer users."""
    db = _seeded()
    _install(
        db,
        principal=Principal(user_id="u_op", tenant_id="default", roles=["useradmin"], is_admin=False),
        perm_ctx=PermissionContext(is_admin=False, permission_codes={"user:manage"}, grant_keys=set()),
    )
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/v1/users", json={"username": "carol", "password": "s3cret-pass", "roles": ["viewer"]}
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201
    assert resp.json()["roles"] == ["viewer"]
