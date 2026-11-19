import json
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.adapters.audit import write_audit
from smartagent.api.security import (
    create_access_token,
    get_current_user,
    require_admin,
    verify_password,
)
from smartagent.api.schemas import (
    OidcProviderCreateRequest,
    OidcLinkRequest,
    OidcProviderOut,
    OidcProviderUpdateRequest,
    PublicOidcProviderOut,
)
from smartagent.authn.oidc import (
    OidcConfigurationError,
    OidcProviderError,
    authorization_url,
    callback_url,
    decrypt_secret,
    discover,
    encrypt_secret,
    exchange_and_verify,
    hash_secret,
    new_pkce_pair,
    new_secret,
    validate_issuer,
)
from smartagent.config import Settings, get_settings
from smartagent.db.models import ExternalIdentity, IdentityProvider, OidcTransaction, User
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal
from smartagent.util import new_id, utcnow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/oidc", tags=["oidc"])
_TRANSACTION_TTL = timedelta(minutes=10)


def _http_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _provider_out(
    provider: IdentityProvider,
    settings: Settings,
    linked_user_count: int = 0,
) -> OidcProviderOut:
    return OidcProviderOut(
        id=provider.id,
        tenant_id=provider.tenant_id,
        provider_key=provider.provider_key,
        display_name=provider.display_name,
        issuer=provider.issuer,
        client_id=provider.client_id,
        scopes=provider.scopes,
        status=provider.status,
        callback_url=callback_url(settings),
        linked_user_count=linked_user_count,
    )


def _browser_cookie_name(transaction_id: str) -> str:
    return f"oidc_{transaction_id}"


def _popup_response(message: dict, settings: Settings, *, status_code: int = 200) -> HTMLResponse:
    parsed = urlsplit(settings.oidc_public_base_url)
    target_origin = f"{parsed.scheme}://{parsed.netloc}"
    serialized = json.dumps(message, separators=(",", ":"), ensure_ascii=True)
    serialized = serialized.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    body = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><title>SmartAgent sign-in</title>
<body><p>Completing sign-in…</p><script>
const result = {serialized};
if (window.opener) {{
  window.opener.postMessage(result, {json.dumps(target_origin)});
  window.close();
}} else {{
  document.body.textContent = result.error || "Sign-in complete. You can close this window.";
}}
</script></body></html>"""
    return HTMLResponse(
        body,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
            "Referrer-Policy": "no-referrer",
        },
        status_code=status_code,
    )


async def _begin_auth(
    *,
    provider: IdentityProvider,
    db: AsyncSession,
    settings: Settings,
    link_user_id: str | None,
    browser_binding: str | None,
) -> tuple[str, str, str]:
    try:
        redirect_uri = callback_url(settings)
        metadata = await discover(provider.issuer, settings)
        verifier, challenge = new_pkce_pair()
        transaction_id = new_id("oidctx")
        state = f"{transaction_id}.{new_secret()}"
        nonce = new_secret()
        browser_secret = browser_binding or new_secret()
        transaction = OidcTransaction(
            id=transaction_id,
            provider_id=provider.id,
            state_hash=hash_secret(state),
            nonce_hash=hash_secret(nonce),
            pkce_verifier_encrypted=encrypt_secret(verifier, settings),
            browser_binding_hash=hash_secret(browser_secret),
            link_user_id=link_user_id,
            expires_at=utcnow() + _TRANSACTION_TTL,
        )
        await db.execute(delete(OidcTransaction).where(OidcTransaction.expires_at <= utcnow()))
        db.add(transaction)
        await db.commit()
        target = authorization_url(
            metadata,
            client_id=provider.client_id,
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
            challenge=challenge,
            scopes=provider.scopes,
        )
    except OidcConfigurationError as exc:
        raise _http_error(503, "OIDC_NOT_CONFIGURED", str(exc)) from exc
    except OidcProviderError as exc:
        logger.warning("OIDC discovery failed: provider_id=%s", provider.id)
        raise _http_error(502, "OIDC_PROVIDER_UNAVAILABLE", str(exc)) from exc
    return target, transaction_id, browser_secret


def _set_browser_cookie(response: Response, transaction_id: str, value: str, settings: Settings) -> None:
    redirect_uri = callback_url(settings)
    response.set_cookie(
        key=_browser_cookie_name(transaction_id),
        value=value,
        max_age=int(_TRANSACTION_TTL.total_seconds()),
        path=urlsplit(redirect_uri).path,
        secure=urlsplit(redirect_uri).scheme == "https",
        httponly=True,
        samesite="lax",
    )


@router.get("/providers/{tenant_id}", response_model=list[PublicOidcProviderOut])
async def list_public_providers(tenant_id: str, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(IdentityProvider).where(
                IdentityProvider.tenant_id == tenant_id,
                IdentityProvider.status == "active",
            )
        )
    ).scalars().all()
    return [
        PublicOidcProviderOut(id=row.id, provider_key=row.provider_key, display_name=row.display_name)
        for row in rows
    ]


@router.get("/providers", response_model=list[OidcProviderOut])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    rows = (
        await db.execute(
            select(IdentityProvider).where(IdentityProvider.tenant_id == principal.tenant_id)
        )
    ).scalars().all()
    linked_counts = (
        await db.execute(
            select(
                ExternalIdentity.provider_id,
                func.count(func.distinct(ExternalIdentity.user_id)),
            )
            .where(ExternalIdentity.tenant_id == principal.tenant_id)
            .group_by(ExternalIdentity.provider_id)
        )
    ).all()
    linked_users_by_provider = {provider_id: count for provider_id, count in linked_counts}
    try:
        return [
            _provider_out(row, settings, linked_users_by_provider.get(row.id, 0))
            for row in rows
        ]
    except OidcConfigurationError as exc:
        raise _http_error(503, "OIDC_NOT_CONFIGURED", str(exc)) from exc


@router.post("/providers", response_model=OidcProviderOut, status_code=201)
async def create_provider(
    body: OidcProviderCreateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    if (
        "openid" not in body.scopes
        or any(not scope.strip() for scope in body.scopes)
        or len(body.scopes) != len(set(body.scopes))
    ):
        raise _http_error(400, "INVALID_ARGUMENT", "scopes must contain openid and no duplicates or blanks")
    try:
        issuer = validate_issuer(body.issuer, settings)
    except OidcConfigurationError as exc:
        raise _http_error(400, "INVALID_OIDC_CONFIGURATION", str(exc)) from exc
    try:
        callback_url(settings)
        encrypted_secret = encrypt_secret(body.client_secret, settings)
    except OidcConfigurationError as exc:
        raise _http_error(503, "OIDC_NOT_CONFIGURED", str(exc)) from exc

    provider = IdentityProvider(
        id=new_id("idp"),
        tenant_id=principal.tenant_id,
        provider_key=body.provider_key,
        display_name=body.display_name,
        issuer=issuer,
        client_id=body.client_id,
        client_secret_encrypted=encrypted_secret,
        scopes=body.scopes,
        created_by=principal.user_id,
    )
    db.add(provider)
    try:
        await db.commit()
        await db.refresh(provider)
    except IntegrityError as exc:
        await db.rollback()
        raise _http_error(409, "OIDC_PROVIDER_EXISTS", "provider_key is already in use") from exc
    await write_audit(
        db,
        tenant_id=principal.tenant_id,
        action="auth.oidc.provider.create",
        result="allow",
        actor=principal.user_id,
        trace_id=None,
        resource_type="oidc_provider",
        resource_id=provider.id,
        detail={"provider_key": provider.provider_key, "issuer": provider.issuer},
    )
    return _provider_out(provider, settings)


@router.patch("/providers/{provider_id}", response_model=OidcProviderOut)
async def update_provider(
    provider_id: str,
    body: OidcProviderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    provider = await db.get(IdentityProvider, provider_id)
    if provider is None or provider.tenant_id != principal.tenant_id:
        raise _http_error(404, "RESOURCE_NOT_FOUND", "OIDC provider not found")
    try:
        callback_url(settings)
    except OidcConfigurationError as exc:
        raise _http_error(503, "OIDC_NOT_CONFIGURED", str(exc)) from exc
    updates = body.model_dump(exclude_unset=True)
    if any(value is None for value in updates.values()):
        raise _http_error(400, "INVALID_ARGUMENT", "OIDC provider fields cannot be null")
    if "scopes" in updates:
        scopes = updates["scopes"]
        if not scopes or any(not scope.strip() for scope in scopes) or "openid" not in scopes or len(scopes) != len(set(scopes)):
            raise _http_error(400, "INVALID_ARGUMENT", "scopes must contain openid and no duplicates")
    if "client_secret" in updates:
        try:
            updates["client_secret_encrypted"] = encrypt_secret(updates.pop("client_secret"), settings)
        except OidcConfigurationError as exc:
            raise _http_error(503, "OIDC_NOT_CONFIGURED", str(exc)) from exc
    for field, value in updates.items():
        setattr(provider, field, value)
    await db.commit()
    await db.refresh(provider)
    await write_audit(
        db,
        tenant_id=principal.tenant_id,
        action="auth.oidc.provider.update",
        result="allow",
        actor=principal.user_id,
        resource_type="oidc_provider",
        resource_id=provider.id,
        detail={"provider_key": provider.provider_key, "updated_fields": sorted(updates)},
    )
    return _provider_out(provider, settings)


@router.delete("/providers/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: Principal = Depends(require_admin),
):
    provider = await db.get(IdentityProvider, provider_id)
    if provider is None or provider.tenant_id != principal.tenant_id:
        raise _http_error(404, "RESOURCE_NOT_FOUND", "OIDC provider not found")
    await db.delete(provider)
    await db.commit()
    await write_audit(
        db,
        tenant_id=principal.tenant_id,
        action="auth.oidc.provider.delete",
        result="allow",
        actor=principal.user_id,
        resource_type="oidc_provider",
        resource_id=provider_id,
    )


@router.get("/{provider_id}/authorize")
async def authorize(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.auth_enabled:
        raise _http_error(503, "OIDC_DISABLED", "OIDC requires AUTH_ENABLED=true")
    provider = await db.get(IdentityProvider, provider_id)
    if provider is None or provider.status != "active":
        raise _http_error(404, "RESOURCE_NOT_FOUND", "OIDC provider not found")
    target, transaction_id, browser_secret = await _begin_auth(
        provider=provider,
        db=db,
        settings=settings,
        link_user_id=None,
        browser_binding=None,
    )
    response = RedirectResponse(target, status_code=302)
    _set_browser_cookie(response, transaction_id, browser_secret, settings)
    return response


@router.post("/{provider_id}/link")
async def link_identity(
    provider_id: str,
    body: OidcLinkRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    if not settings.auth_enabled or principal.user_id == "system":
        raise _http_error(403, "PERMISSION_DENIED", "account linking requires an authenticated user")
    user = await db.get(User, principal.user_id)
    if user is None or user.status != "active" or not verify_password(body.current_password, user.password_hash):
        raise _http_error(401, "UNAUTHORIZED", "current password is incorrect")
    provider = await db.get(IdentityProvider, provider_id)
    if provider is None or provider.tenant_id != principal.tenant_id or provider.status != "active":
        raise _http_error(404, "RESOURCE_NOT_FOUND", "OIDC provider not found")
    target, transaction_id, browser_secret = await _begin_auth(
        provider=provider,
        db=db,
        settings=settings,
        link_user_id=principal.user_id,
        browser_binding=None,
    )
    _set_browser_cookie(response, transaction_id, browser_secret, settings)
    return {"authorization_url": target}


@router.get("/callback", response_model=None)
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    transaction_id = state.partition(".")[0] if state else ""
    transaction = (
        await db.execute(
            select(OidcTransaction)
            .where(
                OidcTransaction.id == transaction_id,
                OidcTransaction.state_hash == hash_secret(state or ""),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    cookie = request.cookies.get(_browser_cookie_name(transaction_id)) if transaction else None
    if (
        transaction is None
        or not cookie
        or not secrets.compare_digest(hash_secret(cookie), transaction.browser_binding_hash)
        or transaction.consumed_at is not None
        or transaction.expires_at <= utcnow()
    ):
        raise _http_error(400, "INVALID_AUTH_TRANSACTION", "OIDC login transaction is invalid or expired")
    transaction.consumed_at = utcnow()
    await db.commit()

    if error or not code:
        return _popup_response(
            {"type": "smartagent-oidc-error", "error": "Provider sign-in was not completed."},
            settings,
        )
    provider = await db.get(IdentityProvider, transaction.provider_id)
    if provider is None or provider.status != "active":
        return _popup_response(
            {"type": "smartagent-oidc-error", "error": "This sign-in provider is unavailable."},
            settings,
        )

    try:
        metadata = await discover(provider.issuer, settings)
        claims = await exchange_and_verify(
            metadata=metadata,
            issuer=provider.issuer,
            client_id=provider.client_id,
            client_secret=decrypt_secret(provider.client_secret_encrypted, settings),
            code=code,
            redirect_uri=callback_url(settings),
            verifier=decrypt_secret(transaction.pkce_verifier_encrypted, settings),
            expected_nonce_hash=transaction.nonce_hash,
        )
    except OidcConfigurationError as exc:
        logger.error("OIDC configuration error during callback: provider_id=%s", provider.id)
        return _popup_response(
            {"type": "smartagent-oidc-error", "error": "Sign-in is temporarily unavailable."},
            settings,
            status_code=503,
        )
    except OidcProviderError as exc:
        logger.warning("OIDC callback validation failed: provider_id=%s", provider.id)
        return _popup_response(
            {"type": "smartagent-oidc-error", "error": "Identity provider authentication failed."},
            settings,
            status_code=401,
        )

    identity_stmt = select(ExternalIdentity).where(
        ExternalIdentity.provider_id == provider.id,
        ExternalIdentity.issuer == claims.issuer,
        ExternalIdentity.subject == claims.subject,
    )
    identity = (await db.execute(identity_stmt)).scalar_one_or_none()
    if transaction.link_user_id:
        user = await db.get(User, transaction.link_user_id)
        if user is None or user.tenant_id != provider.tenant_id or user.status != "active":
            return _popup_response(
                {"type": "smartagent-oidc-error", "error": "The local account is unavailable."},
                settings,
            )
        if identity is not None and identity.user_id != user.id:
            return _popup_response(
                {"type": "smartagent-oidc-error", "error": "This identity is linked to another account."},
                settings,
                status_code=409,
            )
        if identity is None:
            identity = ExternalIdentity(
                id=new_id("extid"),
                tenant_id=provider.tenant_id,
                provider_id=provider.id,
                issuer=claims.issuer,
                subject=claims.subject,
                user_id=user.id,
                email_snapshot=claims.email,
                display_name_snapshot=claims.display_name,
            )
            db.add(identity)
        else:
            identity.email_snapshot = claims.email
            identity.display_name_snapshot = claims.display_name
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            logger.warning("OIDC identity link conflict: provider_id=%s", provider.id)
            return _popup_response(
                {"type": "smartagent-oidc-error", "error": "This identity is already linked."},
                settings,
                status_code=409,
            )
        await write_audit(
            db,
            tenant_id=provider.tenant_id,
            action="auth.oidc.link",
            result="allow",
            actor=user.id,
            trace_id=getattr(request.state, "trace_id", None),
            detail={"provider_key": provider.provider_key},
        )
        result = _popup_response({"type": "smartagent-oidc-linked"}, settings)
    else:
        if identity is None or identity.status != "active" or identity.tenant_id != provider.tenant_id:
            await write_audit(
                db,
                tenant_id=provider.tenant_id,
                action="auth.oidc.login",
                result="deny",
                trace_id=getattr(request.state, "trace_id", None),
                detail={"provider_key": provider.provider_key, "reason": "identity_not_linked"},
            )
            return _popup_response(
                {
                    "type": "smartagent-oidc-error",
                    "error": "This identity is not linked. Sign in with your local account and link it first.",
                },
                settings,
                status_code=403,
            )
        user = await db.get(User, identity.user_id)
        if user is None or user.status != "active" or user.tenant_id != provider.tenant_id:
            return _popup_response(
                {"type": "smartagent-oidc-error", "error": "The local account is unavailable."},
                settings,
            )
        identity.last_login_at = utcnow()
        await db.commit()
        await write_audit(
            db,
            tenant_id=provider.tenant_id,
            action="auth.oidc.login",
            result="allow",
            actor=user.id,
            trace_id=getattr(request.state, "trace_id", None),
            detail={"provider_key": provider.provider_key},
        )
        token = create_access_token(user.id, user.tenant_id)
        result = _popup_response(
            {
                "type": "smartagent-oidc-login",
                "access_token": token,
                "token_type": "bearer",
                "expires_in": settings.jwt_expire_seconds,
            },
            settings,
        )

    result.delete_cookie(
        key=_browser_cookie_name(transaction.id),
        path=urlsplit(callback_url(settings)).path,
        secure=urlsplit(callback_url(settings)).scheme == "https",
        httponly=True,
        samesite="lax",
    )
    return result
