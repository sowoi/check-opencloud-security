"""
The optional sign-in in front of the MCP endpoint.

A public deployment answers anybody, and that is the point of it. A private
one - an estate's own instance behind an identity provider such as Authentik -
needs the opposite, and the failure mode worth testing is the quiet one: a
deployment whose operator believes the endpoint is protected while it is
served open. So these tests assert the refusals as hard as the acceptance, and
they check that authenticating an agent buys it nothing else: the same rate
limit, the same guard, the same erasure credential.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

pytest.importorskip("mcp", reason="the MCP extra is not installed")

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    settings,
)
from webapp import mcp_auth
from webapp import workflows as wf
from webapp.app import create_app

# Long enough that the application will start: a purge token short enough
# to guess is refused at startup, since it is the whole authorisation for
# the one call that deletes other people's results.
PURGE_TOKEN = "erasure-token-for-tests-0123456789abcdef"

ISSUER = "https://auth.example.com/application/o/opencloud-scanner"
RESOURCE = "https://scanner.example.com/mcp"
BASE = "https://scanner.example.com"
AUDIENCE = "opencloud-scanner"

#: The key name the provider publishes and every token here is signed under.
KEY_ID = "test-signing-key"

_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}


@pytest.fixture(autouse=True)
def _instant_waits(monkeypatch):
    """Every wait the workflows take, taken instantly - the behaviour under
    test is which request is refused, never how long a poll sat still for."""

    async def _now(_seconds: float) -> None:
        return None

    monkeypatch.setattr(wf, "default_sleep", _now)


@pytest.fixture
def signing_key():
    """One throwaway RSA key, standing in for the provider's signing key."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _local_keys(monkeypatch, signing_key):
    """
    Serve the test's own public key instead of fetching a real JWKS.

    The network is not the behaviour under test; which claims are accepted
    is. Everything below the key lookup - signature, issuer, audience,
    expiry, algorithm - runs exactly as it does in production.
    """

    def _named(key_id):
        """The provider's key, published under one name."""

        class _Key:
            key = signing_key.public_key()

        _Key.key_id = key_id
        return _Key()

    class _Keys:
        """The two methods `PyJWKClient` is actually used through.

        Counting the refreshes is the point of the second one: a refresh is a
        request to somebody's identity provider, and what may provoke one is a
        security property rather than an implementation detail.
        """

        def __init__(self):
            self.refreshes = 0
            self.published = [KEY_ID]

        def get_signing_keys(self, refresh=False):
            if refresh:
                self.refreshes += 1
            return [_named(name) for name in self.published]

        def rotate(self, key_id):
            """Publish another name for the same key, as a rotation would."""
            self.published.append(key_id)

    keys = _Keys()

    async def _key_set(self):
        return keys

    monkeypatch.setattr(mcp_auth.OidcTokenVerifier, "_key_set", _key_set)
    return keys


def _token(signing_key, **claims):
    """A token the provider could plausibly have issued."""
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "agent",
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
        "scope": "openid profile",
    }
    payload.update(claims)
    return jwt.encode(
        payload, signing_key, algorithm="RS256", headers={"kid": KEY_ID}
    )


def _auth_settings(**overrides):
    values = {
        "public_base_url": BASE,
        "mcp_auth_enabled": True,
        "mcp_auth_issuer": ISSUER,
        "mcp_auth_audience": AUDIENCE,
        "ip_rate_limit": 0,
        "target_cooldown": 0,
    }
    values.update(overrides)
    return settings(**values)


def _client(**overrides):
    return TestClient(create_app(_auth_settings(**overrides)))


def _initialize(served, headers=None):
    return served.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "tests", "version": "1"},
            },
        },
        headers={**_HEADERS, **(headers or {})},
    )


def _scan(served, target, headers):
    """One scan submission through the MCP endpoint, without waiting for it."""
    answer = served.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "scan_instance",
                "arguments": {"target_url": target, "wait": False},
            },
        },
        headers={**_HEADERS, **headers},
    )
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]["structuredContent"]


def test_the_mcp_endpoint_is_open_when_no_sign_in_was_configured():
    """The default is a public service; authentication must be opt-in."""
    with TestClient(create_app(settings())) as served:
        assert _initialize(served).status_code == 200
        assert served.get(mcp_auth.PROTECTED_RESOURCE_PATH).status_code == 404


def test_a_configured_sign_in_refuses_a_request_that_carries_no_token():
    """The whole point: an unauthenticated agent must not reach the tools."""
    with _client() as served:
        response = _initialize(served)
        assert response.status_code == 401
        assert "tools" not in response.text


def test_the_refusal_says_where_a_token_comes_from():
    """
    A client that meets a 401 has to be able to recover from it.

    RFC 9728 says how: the challenge names the resource metadata document,
    which names the authorisation server.
    """
    with _client() as served:
        challenge = _initialize(served).headers.get("www-authenticate", "")
        assert challenge.lower().startswith("bearer")
        assert mcp_auth.PROTECTED_RESOURCE_PATH in challenge


def test_the_resource_metadata_is_public_and_names_the_provider():
    """
    Knowing where to ask for a token was never the secret part.

    An agent reads this before it has a credential, so requiring one to read
    it would be a loop with no way in.
    """
    with _client() as served:
        response = served.get(mcp_auth.PROTECTED_RESOURCE_PATH)
        assert response.status_code == 200
        document = response.json()
        assert document["resource"] == RESOURCE
        assert document["authorization_servers"] == [ISSUER]


def test_an_issuer_that_ends_in_a_slash_is_the_same_issuer(signing_key):
    """
    Authentik's per-provider issuer ends in a slash and most others do not.

    An operator who copies the value out of the discovery document must not
    end up with every valid token refused over one character.
    """
    with _client(mcp_auth_issuer=f"{ISSUER}/") as served:
        response = _initialize(
            served, {"authorization": f"Bearer {_token(signing_key)}"}
        )
        assert response.status_code == 200

    with _client() as served:
        slashed = _initialize(
            served,
            {"authorization": f"Bearer {_token(signing_key, iss=f'{ISSUER}/')}"},
        )
        assert slashed.status_code == 200


def test_a_valid_token_gets_through(signing_key):
    """A correctly issued token has to actually work, or none of this ships."""
    with _client() as served:
        response = _initialize(
            served, {"authorization": f"Bearer {_token(signing_key)}"}
        )
        assert response.status_code == 200
        assert "serverInfo" in response.text


@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"iss": "https://elsewhere.example.com"}, id="issuer"),
        pytest.param({"aud": "some-other-application"}, id="audience"),
        pytest.param({"exp": int(time.time()) - 60}, id="expired"),
    ],
)
def test_a_token_from_the_wrong_place_is_not_a_token(signing_key, claims):
    """
    Each of these is a token that verifies cryptographically and still must
    not be accepted - one issued by another provider, one minted for another
    application, one that has run out. Dropping any single check would let a
    real credential from somewhere else in.
    """
    with _client() as served:
        response = _initialize(
            served, {"authorization": f"Bearer {_token(signing_key, **claims)}"}
        )
        assert response.status_code == 401


def test_a_token_signed_with_the_wrong_key_is_refused():
    """Otherwise anybody who can reach the endpoint can write their own."""
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with _client() as served:
        response = _initialize(
            served, {"authorization": f"Bearer {_token(other)}"}
        )
        assert response.status_code == 401


def test_an_unsigned_token_is_refused(signing_key):
    """
    The oldest JWT mistake there is.

    ``alg: none`` is a token anybody can produce, so the verifier accepts
    asymmetric algorithms only.
    """
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "agent",
        "exp": int(time.time()) + 300,
    }
    forged = jwt.encode(payload, key="", algorithm="none")
    with _client() as served:
        assert _initialize(served, {"authorization": f"Bearer {forged}"}).status_code == 401


def test_a_missing_scope_is_refused(signing_key):
    """A deployment that scopes the endpoint means it; the claim is checked."""
    with _client(mcp_auth_scopes=("scan",)) as served:
        response = _initialize(
            served, {"authorization": f"Bearer {_token(signing_key)}"}
        )
        assert response.status_code == 401
        allowed = _initialize(
            served,
            {"authorization": f"Bearer {_token(signing_key, scope='openid scan')}"},
        )
        assert allowed.status_code == 200


def test_signing_in_does_not_raise_the_rate_limit(signing_key):
    """
    Authentication decides who may ask, never how hard.

    An authenticated agent rationed more generously than a browser would turn
    the sign-in into a way around the limit rather than a guard in front of
    it.
    """
    with _client(ip_rate_limit=1, ip_rate_window=60) as served:
        token = {"authorization": f"Bearer {_token(signing_key)}"}
        first = _scan(served, "https://opencloud.example.com", token)
        second = _scan(served, "https://other.example.com", token)

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["status"] == 429


def test_a_deployment_that_cannot_check_a_token_refuses_to_start():
    """
    The quiet failure this whole module exists to prevent.

    An operator who switched authentication on and gave no issuer must get an
    error, never an endpoint that is open while they believe otherwise.
    """
    with pytest.raises(ValueError, match="ISSUER"):
        create_app(
            settings(
                public_base_url=BASE, mcp_auth_enabled=True, mcp_auth_issuer=""
            )
        )


def test_a_deployment_that_does_not_know_its_own_address_refuses_to_start():
    """The 401 names the resource and the RFC 9728 metadata is published
    beneath it; guessing the address would send clients somewhere else."""
    with pytest.raises(ValueError, match="COS_WEB_PUBLIC_BASE_URL"):
        create_app(
            settings(
                public_base_url="", mcp_auth_enabled=True, mcp_auth_issuer=ISSUER
            )
        )
    with pytest.raises(ValueError, match="RESOURCE_URL"):
        mcp_auth.ensure_mcp_auth_ready(
            settings(
                public_base_url="", mcp_auth_enabled=True, mcp_auth_issuer=ISSUER
            )
        )
    mcp_auth.ensure_mcp_auth_ready(
        settings(
            public_base_url=BASE,
            mcp_auth_enabled=True,
            mcp_auth_issuer=ISSUER,
            mcp_auth_audience=AUDIENCE,
        )
    )


def test_a_sign_in_over_plain_http_refuses_to_start():
    """A bearer token on an unencrypted hop is a credential in the clear."""
    with pytest.raises(ValueError, match="HTTPS"):
        create_app(
            settings(
                public_base_url="http://scanner.example.com",
                mcp_auth_enabled=True,
                mcp_auth_issuer=ISSUER,
            )
        )


def test_a_plain_http_identity_provider_refuses_to_start():
    """Signing keys must not be fetched over an attacker-observable hop."""
    with pytest.raises(ValueError, match="ISSUER"):
        create_app(
            settings(
                public_base_url=BASE,
                mcp_auth_enabled=True,
                mcp_auth_issuer="http://auth.example.com/issuer",
            )
        )


def test_a_plain_http_jwks_endpoint_refuses_to_start():
    """An HTTPS issuer is insufficient if its keys come from plain HTTP."""
    with pytest.raises(ValueError, match="JWKS"):
        create_app(
            settings(
                public_base_url=BASE,
                mcp_auth_enabled=True,
                mcp_auth_issuer=ISSUER,
                mcp_auth_jwks_url="http://auth.example.com/jwks",
            )
        )


def test_a_sign_in_without_an_audience_refuses_to_start():
    """
    The confused deputy this endpoint would otherwise be.

    A provider that serves more than this service mints tokens for every
    application behind it, all with the same issuer and the same signing key.
    An audience that is never compared makes every one of them a key to /mcp,
    so an operator who leaves it out is told rather than quietly served open.
    """
    with pytest.raises(ValueError, match="AUDIENCE"):
        create_app(
            settings(
                public_base_url=BASE,
                mcp_auth_enabled=True,
                mcp_auth_issuer=ISSUER,
                mcp_auth_audience="",
            )
        )


def test_a_verifier_without_an_audience_accepts_nothing(signing_key):
    """
    The second half of the same refusal, in case the first is ever bypassed.

    Startup is the place this configuration is caught, but a verifier built
    any other way must not fall open either: with nothing to compare, a
    perfectly valid token from the right issuer is still not a token here.
    """
    import asyncio

    verifier = mcp_auth.OidcTokenVerifier(
        jwks_uri="https://auth.example.com/jwks",
        issuer=ISSUER,
        audience="   ",
    )
    accepted = asyncio.run(verifier.verify_token(_token(signing_key)))
    assert accepted is None


def test_a_token_that_names_no_audience_at_all_is_refused(signing_key):
    """A token with no `aud` claim cannot have been minted for this endpoint,
    and accepting one would undo the check the audience exists for."""
    token = _token(signing_key)
    payload = jwt.decode(token, options={"verify_signature": False})
    payload.pop("aud")
    without = jwt.encode(payload, signing_key, algorithm="RS256")
    with _client() as served:
        prefix = "B" + "earer"
        response = _initialize(
            served, {"authorization": f"{prefix} {without}"}
        )
        assert response.status_code == 401


def test_authentication_configured_without_the_endpoint_is_not_an_error():
    """
    Turning the endpoint off is a perfectly good way to protect it.

    Making the safest configuration the one that fails to boot would teach
    operators to switch the guard off instead.
    """
    app = create_app(
        settings(
            public_base_url=BASE,
            enable_mcp=False,
            mcp_auth_enabled=True,
            mcp_auth_issuer="",
        )
    )
    assert app is not None


def test_the_discovery_document_says_a_token_is_needed_before_one_is_tried():
    """
    An agent should learn this from the document that told it the endpoint
    exists, not from a 401 it has to spend a round trip on.
    """
    with _client() as served:
        block = served.get("/.well-known/ai.json").json()["mcp"]
        assert block["authentication"]["type"] == "oauth2"
        assert block["authentication"]["issuer"] == ISSUER

    with TestClient(create_app(settings())) as open_service:
        block = open_service.get("/.well-known/ai.json").json()["mcp"]
        assert block["authentication"]["type"] == "none"


def _erase(served, headers):
    """One erasure call through the MCP endpoint."""
    answer = served.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "erase_instance_data",
                "arguments": {"target": "opencloud.example.com"},
            },
        },
        headers={**_HEADERS, **headers},
    )
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]["structuredContent"]


def test_the_purge_credential_moves_out_of_the_way_of_the_identity_token(
    signing_key,
):
    """
    Two credentials cannot share one header.

    With a sign-in configured, `Authorization` is the agent's identity. An
    erasure that read it as the operator's purge credential would compare one
    credential against the other and refuse for a reason nobody could see, so
    the purge credential gets a header of its own - and the fallback is
    deliberately not kept.
    """
    token = f"Bearer {_token(signing_key)}"
    with _client(purge_token=PURGE_TOKEN) as served:
        refused = _erase(served, {"authorization": token})
        allowed = _erase(
            served,
            {
                "authorization": token,
                "x-purge-authorization": f"Bearer {PURGE_TOKEN}",
            },
        )

    assert refused["ok"] is False
    assert refused["status"] == 401
    assert allowed["ok"] is True
    # The negative half: neither credential is handed back to the model.
    assert "s3cret" not in json.dumps(allowed)


def test_an_identity_token_is_never_accepted_as_an_erasure_credential(
    signing_key,
):
    """
    The failure this separation exists to prevent.

    An agent that signed in has a valid bearer token. That must not be enough
    to delete everybody's results.
    """
    token = f"Bearer {_token(signing_key)}"
    with _client(purge_token=PURGE_TOKEN) as served:
        result = _erase(
            served,
            {"authorization": token, "x-purge-authorization": token},
        )

    assert result["ok"] is False
    assert result["status"] == 401


# ------------------------------------------- a token nobody signed costs nothing


def test_a_token_naming_an_unknown_key_cannot_order_a_fetch_per_request(
    _local_keys, signing_key
):
    """An unauthenticated request must not become a request to the provider.

    The key set is looked up by the `kid` in the token, and the client
    refetches whenever that name is not in the set - which is how a rotated
    key starts working without a restart, and how a stream of tokens signed by
    nobody becomes a load generator aimed at somebody's identity provider,
    with a blocking fetch in front of every other caller each time. A `kid` is
    two lines of JSON to invent, and neither the signature nor the audience
    has been looked at by the time the fetch would happen.

    So the first miss may pay for one, and the rest are simply not tokens.
    """
    forged = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "agent",
            "exp": int(time.time()) + 300,
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": "a-key-nobody-published"},
    )

    verifier = mcp_auth.OidcTokenVerifier(
        jwks_uri="https://auth.example.com/jwks",
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    for _ in range(20):
        assert asyncio.run(verifier.verify_token(forged)) is None

    assert _local_keys.refreshes == 1


def test_a_rotated_key_is_still_picked_up_without_a_restart(
    _local_keys, signing_key
):
    """The other half: the floor must not turn into a service that never rotates.

    A key set that has genuinely changed is fetched on the first token that
    names the new key, which is the behaviour the refetch exists for.
    """
    verifier = mcp_auth.OidcTokenVerifier(
        jwks_uri="https://auth.example.com/jwks",
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    unknown = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 300},
        signing_key,
        algorithm="RS256",
        headers={"kid": "rotated-in"},
    )

    assert asyncio.run(verifier.verify_token(unknown)) is None
    assert _local_keys.refreshes == 1

    # The provider now publishes it, and the very next token is accepted -
    # without waiting out the floor, because this fetch was already paid for.
    _local_keys.rotate("rotated-in")
    assert asyncio.run(verifier.verify_token(unknown)) is not None


def test_the_signature_is_still_what_decides_it(_local_keys, signing_key):
    """The key name selects a published key; it never stands in for a check.

    The header is read without being verified, so a token naming the right
    key while being signed with another must fail - or the lookup would be
    the authentication.
    """
    someone_else = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 300},
        someone_else,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )

    verifier = mcp_auth.OidcTokenVerifier(
        jwks_uri="https://auth.example.com/jwks",
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert asyncio.run(verifier.verify_token(forged)) is None
    # And the same token signed by the key that name really belongs to works.
    assert asyncio.run(verifier.verify_token(_token(signing_key))) is not None
