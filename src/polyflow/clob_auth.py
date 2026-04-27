"""Polymarket CLOB authentication primitives.

Two layers exist in the Polymarket auth model:

  L1 (EIP-712 wallet signature) — used to *derive* the L2 key set from a
  private key. One call to ``POST /auth/api-key`` returns ``apiKey``,
  ``secret``, and ``passphrase``.

  L2 (HMAC + headers) — used on every subsequent CLOB request once the L2 key
  set is known. Signature = base64(HMAC-SHA256(secret, timestamp + method +
  path + body)).

This module owns the message construction + header building. The actual
private-key signing requires ``eth-account``; we import it lazily so the rest
of POLYFLOW does not depend on it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any


CLOB_AUTH_DOMAIN_NAME = "ClobAuthDomain"
CLOB_AUTH_VERSION = "1"
CLOB_AUTH_MESSAGE = "This message attests that I control the given wallet"

POLYGON_MAINNET_CHAIN_ID = 137


@dataclass(frozen=True)
class L1AuthHeaders:
    """The four headers POLYFLOW attaches to ``POST /auth/api-key``."""

    POLY_ADDRESS: str
    POLY_SIGNATURE: str
    POLY_TIMESTAMP: str
    POLY_NONCE: str

    def as_dict(self) -> dict[str, str]:
        return {
            "POLY_ADDRESS": self.POLY_ADDRESS,
            "POLY_SIGNATURE": self.POLY_SIGNATURE,
            "POLY_TIMESTAMP": self.POLY_TIMESTAMP,
            "POLY_NONCE": self.POLY_NONCE,
        }


def build_clob_auth_typed_data(
    *,
    wallet_address: str,
    timestamp: str,
    nonce: int = 0,
    chain_id: int = POLYGON_MAINNET_CHAIN_ID,
) -> dict[str, Any]:
    """Construct the EIP-712 typed-data payload that the wallet must sign.

    Mirrors the structure used by ``@polymarket/clob-client-v2``.
    """
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
            ],
            "ClobAuth": [
                {"name": "address", "type": "address"},
                {"name": "timestamp", "type": "string"},
                {"name": "nonce", "type": "uint256"},
                {"name": "message", "type": "string"},
            ],
        },
        "primaryType": "ClobAuth",
        "domain": {
            "name": CLOB_AUTH_DOMAIN_NAME,
            "version": CLOB_AUTH_VERSION,
            "chainId": chain_id,
        },
        "message": {
            "address": wallet_address,
            "timestamp": timestamp,
            "nonce": nonce,
            "message": CLOB_AUTH_MESSAGE,
        },
    }


def sign_l1_auth(
    *,
    private_key: str,
    chain_id: int = POLYGON_MAINNET_CHAIN_ID,
    nonce: int = 0,
    now_unix: int | None = None,
) -> L1AuthHeaders:
    """Sign the ClobAuth message and produce the four POLY_* headers.

    Lazy-imports ``eth_account`` so the rest of the runtime does not require
    it. Raises ``ImportError`` with an actionable message if the optional
    ``[trade]`` extra is not installed.
    """
    try:
        from eth_account import Account  # type: ignore[import-not-found]
        from eth_account.messages import encode_typed_data  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "L1 auth signing requires the 'trade' extra. Install with:\n"
            "    pip install -e \".[trade]\""
        ) from e

    timestamp = str(int(now_unix if now_unix is not None else time.time()))
    account = Account.from_key(private_key)
    typed = build_clob_auth_typed_data(
        wallet_address=account.address,
        timestamp=timestamp,
        nonce=nonce,
        chain_id=chain_id,
    )
    signable = encode_typed_data(full_message=typed)
    signed = account.sign_message(signable)
    sig_hex = (
        signed.signature.hex()
        if isinstance(signed.signature, bytes)
        else str(signed.signature)
    )
    if not sig_hex.startswith("0x"):
        sig_hex = "0x" + sig_hex
    return L1AuthHeaders(
        POLY_ADDRESS=account.address,
        POLY_SIGNATURE=sig_hex,
        POLY_TIMESTAMP=timestamp,
        POLY_NONCE=str(nonce),
    )


# ---- L2 signing -----------------------------------------------------------


def sign_l2(
    *,
    secret: str,
    timestamp: str,
    method: str,
    path: str,
    body: str = "",
) -> str:
    """HMAC-SHA256(secret, timestamp + METHOD + path + body), base64url-encoded.

    Polymarket's CLOB derives the secret as a url-safe base64 string; we decode
    it (with padding repair) before keying the HMAC. The output keeps the
    standard ``=`` padding — py-clob-client keeps it and Polymarket validates
    against that exact form.
    """
    try:
        secret_bytes = base64.urlsafe_b64decode(secret + "=" * (-len(secret) % 4))
    except (ValueError, TypeError):
        secret_bytes = secret.encode("utf-8")
    msg = (timestamp + method.upper() + path + (body or "")).encode("utf-8")
    digest = hmac.new(secret_bytes, msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def l2_headers(
    *,
    api_key: str,
    secret: str,
    passphrase: str,
    method: str,
    path: str,
    body_obj: Any | None = None,
    now_unix: int | None = None,
) -> dict[str, str]:
    """Build the headers for an authenticated L2 request."""
    body = json.dumps(body_obj, separators=(",", ":")) if body_obj is not None else ""
    timestamp = str(int(now_unix if now_unix is not None else time.time()))
    sig = sign_l2(
        secret=secret, timestamp=timestamp, method=method, path=path, body=body
    )
    return {
        "POLY_ADDRESS": "",  # filled by caller if needed (some endpoints want it)
        "POLY_API_KEY": api_key,
        "POLY_PASSPHRASE": passphrase,
        "POLY_SIGNATURE": sig,
        "POLY_TIMESTAMP": timestamp,
    }
