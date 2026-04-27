"""CLOB authentication primitive tests.

We test the deterministic pieces (typed-data construction, L2 HMAC) and the
HTTP path (mocked transport). The L1 EIP-712 signing path is exercised via
``test_derive_api_credentials_e2e`` which uses a deterministic test private
key — no real wallets touched.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from polyflow.clob_auth import (
    CLOB_AUTH_MESSAGE,
    POLYGON_MAINNET_CHAIN_ID,
    build_clob_auth_typed_data,
    l2_headers,
    sign_l2,
)


# Deterministic test key (well-known Hardhat test account #0). NEVER a real key.
TEST_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


class TestTypedDataShape:
    def test_domain_and_types(self) -> None:
        td = build_clob_auth_typed_data(
            wallet_address=TEST_ADDRESS, timestamp="1714000000", nonce=0
        )
        assert td["primaryType"] == "ClobAuth"
        assert td["domain"]["name"] == "ClobAuthDomain"
        assert td["domain"]["chainId"] == POLYGON_MAINNET_CHAIN_ID
        assert td["message"]["address"] == TEST_ADDRESS
        assert td["message"]["message"] == CLOB_AUTH_MESSAGE
        # ClobAuth has 4 named fields.
        assert {f["name"] for f in td["types"]["ClobAuth"]} == {
            "address", "timestamp", "nonce", "message",
        }


class TestL2Signing:
    def test_hmac_signature_is_deterministic(self) -> None:
        # Plain ASCII secret path: bytes == utf-8 encoding (not base64).
        secret = "abc"  # not valid base64 padding → falls through to utf-8
        sig1 = sign_l2(secret=secret, timestamp="1", method="GET", path="/orders", body="")
        sig2 = sign_l2(secret=secret, timestamp="1", method="GET", path="/orders", body="")
        assert sig1 == sig2

    def test_method_case_does_not_change_signature(self) -> None:
        secret = "abc"
        a = sign_l2(secret=secret, timestamp="1", method="get", path="/x")
        b = sign_l2(secret=secret, timestamp="1", method="GET", path="/x")
        assert a == b

    def test_l2_headers_include_required_fields(self) -> None:
        h = l2_headers(
            api_key="k",
            secret="abc",
            passphrase="p",
            method="POST",
            path="/orders",
            body_obj={"a": 1},
            now_unix=1714000000,
        )
        assert h["POLY_API_KEY"] == "k"
        assert h["POLY_PASSPHRASE"] == "p"
        assert h["POLY_TIMESTAMP"] == "1714000000"
        assert h["POLY_SIGNATURE"]


# eth-account is an optional [trade] dependency. Skip the L1 signing test
# if it isn't installed in this environment.
ethaccount = pytest.importorskip("eth_account")


class TestL1Signing:
    def test_sign_l1_auth_produces_consistent_address(self) -> None:
        from polyflow.clob_auth import sign_l1_auth

        h = sign_l1_auth(
            private_key=TEST_PRIVATE_KEY,
            chain_id=POLYGON_MAINNET_CHAIN_ID,
            nonce=0,
            now_unix=1714000000,
        )
        assert h.POLY_ADDRESS.lower() == TEST_ADDRESS.lower()
        assert h.POLY_TIMESTAMP == "1714000000"
        assert h.POLY_NONCE == "0"
        # 65-byte ECDSA signature → 130 hex chars (with optional 0x prefix)
        sig_no_prefix = h.POLY_SIGNATURE.removeprefix("0x")
        assert len(sig_no_prefix) >= 130


@pytest.mark.asyncio
async def test_derive_api_credentials_existing_key() -> None:
    """GET /auth/derive-api-key returns 200 → use that response (existing key)."""
    from polyflow.adapters.polymarket_clob_trade import derive_api_credentials

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.setdefault("requests", []).append((request.method, request.url.path))
        seen["last_headers"] = dict(request.headers)
        if request.url.path == "/auth/derive-api-key":
            return httpx.Response(
                200,
                json={
                    "apiKey": "550e8400-e29b-41d4-a716-446655440000",
                    "secret": base64.urlsafe_b64encode(b"x" * 32).decode().rstrip("="),
                    "passphrase": "passphrase-string",
                },
            )
        return httpx.Response(500, json={"error": "should not reach"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        creds = await derive_api_credentials(private_key=TEST_PRIVATE_KEY, client=client)

    assert seen["requests"] == [("GET", "/auth/derive-api-key")]
    h = {k.lower(): v for k, v in seen["last_headers"].items()}
    assert h["poly_address"].lower() == TEST_ADDRESS.lower()
    assert h["poly_signature"].startswith("0x")
    assert h["poly_nonce"] == "0"
    assert creds.api_key.startswith("550e8400")
    assert creds.passphrase == "passphrase-string"


@pytest.mark.asyncio
async def test_derive_api_credentials_falls_back_to_create() -> None:
    """If derive returns 400 (no existing key), fall back to POST /auth/api-key."""
    from polyflow.adapters.polymarket_clob_trade import derive_api_credentials

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.setdefault("requests", []).append((request.method, request.url.path))
        if request.url.path == "/auth/derive-api-key":
            return httpx.Response(400, json={"error": "no key"})
        if request.url.path == "/auth/api-key" and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "apiKey": "abcdef12-3456-7890-abcd-ef1234567890",
                    "secret": base64.urlsafe_b64encode(b"y" * 32).decode().rstrip("="),
                    "passphrase": "new-pass",
                },
            )
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        creds = await derive_api_credentials(private_key=TEST_PRIVATE_KEY, client=client)

    assert seen["requests"] == [
        ("GET", "/auth/derive-api-key"),
        ("POST", "/auth/api-key"),
    ]
    assert creds.api_key.startswith("abcdef12")
