import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet

from smartagent.authn.oidc import (
    OidcConfigurationError,
    authorization_url,
    callback_url,
    decrypt_secret,
    encrypt_secret,
    new_pkce_pair,
    _discovery_url,
    validate_issuer,
)
from smartagent.config import Settings


def _settings(**overrides) -> Settings:
    values = {
        "oidc_encryption_key": Fernet.generate_key().decode("ascii"),
        "oidc_allowed_hosts": ["idp.example.com"],
        "oidc_public_base_url": "https://agents.example.com",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_oidc_secret_encryption_and_key_rotation_failure():
    settings = _settings()
    ciphertext = encrypt_secret("client-secret", settings)

    assert ciphertext != "client-secret"
    assert decrypt_secret(ciphertext, settings) == "client-secret"

    with pytest.raises(OidcConfigurationError):
        decrypt_secret(ciphertext, _settings(oidc_encryption_key=Fernet.generate_key().decode("ascii")))


def test_issuer_must_be_https_and_inside_operator_host_allowlist():
    settings = _settings()

    assert validate_issuer("https://login.idp.example.com/tenant/", settings) == (
        "https://login.idp.example.com/tenant"
    )
    with pytest.raises(OidcConfigurationError):
        validate_issuer("http://idp.example.com", settings)
    with pytest.raises(OidcConfigurationError):
        validate_issuer("https://idp.example.com.attacker.test", settings)
    with pytest.raises(OidcConfigurationError):
        validate_issuer("https://idp.example.com:8443", settings)


def test_callback_uses_configured_public_origin_not_request_host():
    settings = _settings(oidc_public_base_url="https://agents.example.com/platform")

    assert callback_url(settings) == (
        "https://agents.example.com/platform/v1/auth/oidc/callback"
    )


def test_discovery_url_appends_well_known_path_to_issuer():
    assert _discovery_url("https://idp.example.com/tenant") == (
        "https://idp.example.com/tenant/.well-known/openid-configuration"
    )


def test_authorization_url_includes_state_nonce_and_pkce():
    settings = _settings()
    verifier, challenge = new_pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
    url = authorization_url(
        {"authorization_endpoint": "https://login.idp.example.com/authorize"},
        client_id="client",
        redirect_uri=callback_url(settings),
        state="tx.secret",
        nonce="nonce",
        challenge=challenge,
        scopes=["openid", "email"],
    )
    query = parse_qs(urlsplit(url).query)

    assert challenge == expected
    assert query["code_challenge"] == [expected]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == ["tx.secret"]
    assert query["nonce"] == ["nonce"]
    assert query["scope"] == ["openid email"]
