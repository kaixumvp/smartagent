"""Small, strict OIDC client for tenant-configured authorization-code flows."""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from urllib.parse import quote_plus, urlencode, urlsplit, urlunsplit

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken

from smartagent.config import Settings

_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"]


class OidcConfigurationError(ValueError):
    """Local OIDC settings are missing or unsafe."""


class OidcProviderError(ValueError):
    """The configured identity provider could not be safely used."""


@dataclass(frozen=True)
class OidcClaims:
    issuer: str
    subject: str
    email: str | None
    display_name: str | None


def _fernet(settings: Settings) -> Fernet:
    if not settings.oidc_encryption_key:
        raise OidcConfigurationError("OIDC_ENCRYPTION_KEY is required for OIDC")
    try:
        return Fernet(settings.oidc_encryption_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise OidcConfigurationError("OIDC_ENCRYPTION_KEY must be a valid Fernet key") from exc


def encrypt_secret(value: str, settings: Settings) -> str:
    if not value:
        raise OidcConfigurationError("OIDC client secret cannot be empty")
    return _fernet(settings).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str, settings: Settings) -> str:
    try:
        return _fernet(settings).decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError) as exc:
        raise OidcConfigurationError("OIDC secret cannot be decrypted; check OIDC_ENCRYPTION_KEY") from exc


def _allowed_host(hostname: str, settings: Settings) -> bool:
    host = hostname.lower().rstrip(".")
    return any(
        host == allowed.strip().lower().rstrip(".")
        or host.endswith(f".{allowed.strip().lower().rstrip('.')}")
        for allowed in settings.oidc_allowed_hosts
        if allowed.strip()
    )


def validate_issuer(issuer: str, settings: Settings) -> str:
    parsed = urlsplit(issuer)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not _allowed_host(parsed.hostname, settings)
    ):
        raise OidcConfigurationError(
            "OIDC issuer must be HTTPS and its hostname must match OIDC_ALLOWED_HOSTS"
        )
    try:
        if parsed.port not in (None, 443):
            raise OidcConfigurationError("OIDC issuer must use the standard HTTPS port")
    except ValueError as exc:
        raise OidcConfigurationError("OIDC issuer has an invalid port") from exc
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def callback_url(settings: Settings) -> str:
    parsed = urlsplit(settings.oidc_public_base_url.rstrip("/"))
    local_http = settings.debug and parsed.hostname in {"localhost", "127.0.0.1"}
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (parsed.scheme != "https" and not (parsed.scheme == "http" and local_http))
    ):
        raise OidcConfigurationError(
            "OIDC_PUBLIC_BASE_URL must be an HTTPS origin (HTTP localhost is allowed only in debug)"
        )
    return (
        f"{settings.oidc_public_base_url.rstrip('/')}"
        f"{settings.api_prefix.rstrip('/')}/auth/oidc/callback"
    )


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _discovery_url(issuer: str) -> str:
    parsed = urlsplit(issuer)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, f"{parsed.path.rstrip('/')}/.well-known/openid-configuration", "", "")
    )


def _validate_endpoint(value: object, settings: Settings) -> str:
    if not isinstance(value, str):
        raise OidcProviderError("OIDC discovery document is missing an endpoint")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or not _allowed_host(parsed.hostname, settings)
    ):
        raise OidcProviderError("OIDC endpoint must use an allowed HTTPS hostname")
    try:
        if parsed.port not in (None, 443):
            raise OidcProviderError("OIDC endpoint must use the standard HTTPS port")
    except ValueError as exc:
        raise OidcProviderError("OIDC endpoint has an invalid port") from exc
    return value


async def discover(issuer: str, settings: Settings) -> dict:
    safe_issuer = validate_issuer(issuer, settings)
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False, trust_env=False) as client:
            response = await client.get(_discovery_url(safe_issuer))
            response.raise_for_status()
            document = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcProviderError("OIDC discovery request failed") from exc

    if not isinstance(document, dict) or document.get("issuer") != safe_issuer:
        raise OidcProviderError("OIDC discovery issuer does not match configured issuer")
    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        document[field] = _validate_endpoint(document.get(field), settings)
    return document


def authorization_url(
    metadata: dict,
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    challenge: str,
    scopes: list[str],
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    endpoint = urlsplit(metadata["authorization_endpoint"])
    combined_query = f"{endpoint.query}&{query}" if endpoint.query else query
    return urlunsplit((endpoint.scheme, endpoint.netloc, endpoint.path, combined_query, endpoint.fragment))


async def exchange_and_verify(
    *,
    metadata: dict,
    issuer: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    verifier: str,
    expected_nonce_hash: str,
) -> OidcClaims:
    methods = metadata.get("token_endpoint_auth_methods_supported") or ["client_secret_basic"]
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    headers: dict[str, str] = {}
    if "client_secret_basic" in methods:
        credentials = f"{quote_plus(client_id, safe='')}:{quote_plus(client_secret, safe='')}".encode("utf-8")
        headers["Authorization"] = f"Basic {base64.b64encode(credentials).decode('ascii')}"
    elif "client_secret_post" in methods:
        form.update({"client_id": client_id, "client_secret": client_secret})
    else:
        raise OidcProviderError("OIDC provider must support client_secret_basic or client_secret_post")

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False, trust_env=False) as client:
            response = await client.post(metadata["token_endpoint"], data=form, headers=headers)
            response.raise_for_status()
            token_response = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcProviderError("OIDC token exchange failed") from exc
    if not isinstance(token_response, dict) or not isinstance(token_response.get("id_token"), str):
        raise OidcProviderError("OIDC token response did not contain an ID token")

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False, trust_env=False) as client:
            response = await client.get(metadata["jwks_uri"])
            response.raise_for_status()
            jwks = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcProviderError("OIDC signing keys could not be fetched") from exc
    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
        raise OidcProviderError("OIDC JWKS document is invalid")

    try:
        header = jwt.get_unverified_header(token_response["id_token"])
        if header.get("alg") not in _ALGORITHMS or not isinstance(header.get("kid"), str):
            raise OidcProviderError("OIDC ID token uses an unsupported signing algorithm")
        key_data = next(
            key
            for key in jwks["keys"]
            if isinstance(key, dict) and key.get("kid") == header["kid"] and key.get("use", "sig") == "sig"
        )
        signing_key = jwt.PyJWK.from_dict(key_data).key
        claims = jwt.decode(
            token_response["id_token"],
            signing_key,
            algorithms=_ALGORITHMS,
            audience=client_id,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud", "nonce"]},
            leeway=60,
        )
    except (jwt.PyJWTError, StopIteration, KeyError, TypeError, ValueError) as exc:
        raise OidcProviderError("OIDC ID token validation failed") from exc

    nonce = claims.get("nonce")
    if not isinstance(nonce, str) or not hmac.compare_digest(hash_secret(nonce), expected_nonce_hash):
        raise OidcProviderError("OIDC ID token nonce does not match the login transaction")
    audiences = claims.get("aud")
    if isinstance(audiences, list) and len(audiences) > 1 and claims.get("azp") != client_id:
        raise OidcProviderError("OIDC ID token authorized party does not match the client")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise OidcProviderError("OIDC ID token subject is invalid")
    email = claims.get("email") if claims.get("email_verified") is True else None
    name = claims.get("name") or claims.get("preferred_username")
    return OidcClaims(
        issuer=claims["iss"],
        subject=subject,
        email=email[:320] if isinstance(email, str) else None,
        display_name=name[:128] if isinstance(name, str) else None,
    )
