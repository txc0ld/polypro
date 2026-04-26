"""Polymarket CLOB trade-side adapter.

What is implemented (and tested with mock transport):
  - L1 credential derivation: ``POST /auth/api-key``. Given a private key,
    derive ``{apiKey, secret, passphrase}``.
  - L2-authenticated reads: ``GET /orders``, ``GET /balance-allowances``.
  - Order *cancellation* with L2 auth.

What is *not* yet implemented (a clear placeholder is provided):
  - ``place_order`` — requires EIP-712 Order signing against the CTF
    Exchange contract address (and the neg-risk variant). The signer must
    use ``signatureType=1`` (POLY_PROXY) plus the ``funderAddress`` for
    proxy-wallet users. This is on the roadmap; until then ``place_order``
    raises ``NotImplementedError`` with the missing pieces enumerated.

Lazy-imports ``eth_account`` so the optional ``[trade]`` extra is only
required when this adapter is instantiated against a real network endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ..clob_auth import POLYGON_MAINNET_CHAIN_ID, l2_headers, sign_l1_auth
from ..secrets import Credentials
from ..types import OrderPayload, Position

_CLOB_BASE = "https://clob.polymarket.com"


@dataclass(frozen=True)
class DerivedCredentials:
    api_key: str
    secret: str
    passphrase: str


async def derive_api_credentials(
    *,
    private_key: str,
    base_url: str = _CLOB_BASE,
    chain_id: int = POLYGON_MAINNET_CHAIN_ID,
    client: httpx.AsyncClient | None = None,
) -> DerivedCredentials:
    """Sign the ClobAuth message with ``private_key`` and call /auth/api-key.

    Returns the L2 credentials. Mirrors ``client.createOrDeriveApiKey()`` from
    the official TS CLOB SDK.
    """
    headers = sign_l1_auth(private_key=private_key, chain_id=chain_id).as_dict()

    owns = client is None
    client = client or httpx.AsyncClient(timeout=15.0)
    try:
        resp = await client.post(f"{base_url.rstrip('/')}/auth/api-key", headers=headers)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns:
            await client.aclose()

    api_key = data.get("apiKey") or data.get("api_key")
    secret = data.get("secret")
    passphrase = data.get("passphrase")
    if not (api_key and secret and passphrase):
        raise RuntimeError(f"Polymarket /auth/api-key returned an unexpected payload: keys={list(data)}")
    return DerivedCredentials(api_key=api_key, secret=secret, passphrase=passphrase)


class PolymarketCLOBTradeAdapter:
    """Authenticated CLOB adapter. Place / cancel / read with L1 + L2 auth."""

    def __init__(
        self,
        *,
        credentials: Credentials,
        funder_address: str | None = None,
        signature_type: int = 1,  # 1 = POLY_PROXY, the standard Polymarket smart-wallet path
        base_url: str = _CLOB_BASE,
        chain_id: int = POLYGON_MAINNET_CHAIN_ID,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not credentials.has_trade_credentials:
            raise ValueError(
                "Trade adapter requires full credentials. Missing: "
                + ",".join(credentials.missing_for_trading())
            )
        self.credentials = credentials
        # Prefer an explicit constructor arg, then the credentials' funder_address,
        # then the wallet address as a self-funded fallback.
        self.funder_address = (
            funder_address
            or credentials.funder_address
            or credentials.wallet_address
        )
        self.signature_type = signature_type
        self._base_url = base_url.rstrip("/")
        self._chain_id = chain_id
        self._timeout = timeout_seconds
        self._client = client

    async def __aenter__(self) -> "PolymarketCLOBTradeAdapter":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ---- L2 helpers ----
    def _headers_for(self, *, method: str, path: str, body: Any | None = None) -> dict[str, str]:
        h = l2_headers(
            api_key=self.credentials.api_key or "",
            secret=self.credentials.api_secret or "",
            passphrase=self.credentials.api_passphrase or "",
            method=method,
            path=path,
            body_obj=body,
        )
        if self.credentials.wallet_address:
            h["POLY_ADDRESS"] = self.credentials.wallet_address
        return {k: v for k, v in h.items() if v}

    async def _request(
        self, method: str, path: str, *, body: Any | None = None
    ) -> Any:
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            req = client.build_request(
                method.upper(),
                f"{self._base_url}{path}",
                headers=self._headers_for(method=method, path=path, body=body),
                json=body if body is not None else None,
            )
            resp = await client.send(req)
            resp.raise_for_status()
            return resp.json()
        finally:
            if owns:
                await client.aclose()

    # ---- public API ----
    async def get_open_orders(self) -> list[dict]:
        return await self._request("GET", "/orders") or []

    async def get_positions(self) -> list[Position]:
        # Production reads positions from the Data API (see polymarket_user.py),
        # but the L2 endpoint is also available and is auth-checked.
        rows = await self._request("GET", "/positions")
        out: list[Position] = []
        for r in rows or []:
            try:
                out.append(
                    Position(
                        market_id=str(r.get("market_id") or r.get("marketId") or ""),
                        token_id=str(r.get("token_id") or r.get("tokenId") or ""),
                        outcome=r.get("outcome") or "YES",
                        size=float(r.get("size") or 0),
                        avg_price=float(r.get("avg_price") or r.get("avgPrice") or 0),
                    )
                )
            except (TypeError, ValueError, KeyError):
                continue
        return out

    async def cancel_order(self, exchange_order_id: str) -> bool:
        path = f"/orders/{exchange_order_id}"
        await self._request("DELETE", path)
        return True

    async def place_order(self, payload: OrderPayload, *, neg_risk: bool = False) -> dict:
        """Sign + submit an EIP-712 ``Order`` to the CLOB.

        Validates every invariant locally before signing — see ``order_signing.sign_order``.
        ``neg_risk`` selects the alternate Exchange contract for related-outcome markets.
        """
        from ..order_signing import OrderSide, SignatureType, sign_order

        if not self.credentials.private_key:
            raise RuntimeError("place_order requires POLY_PRIVATE_KEY")

        side = OrderSide.BUY if payload.side.value == "BUY" else OrderSide.SELL
        sig_type = SignatureType(self.signature_type)
        if sig_type is not SignatureType.EOA and not self.funder_address:
            raise RuntimeError(
                f"place_order with signatureType={sig_type.name} requires POLY_FUNDER_ADDRESS"
            )

        # Fee rate: pull off the market record at signal time and pin it on the payload's
        # ``maxPositionAfterFill`` is *not* the right field. Real production reads this
        # from the market metadata adjacent to the order. We default to 0 here and let
        # the runtime override on construction.
        fee_rate_bps = getattr(payload, "feeRateBps", 0)
        try:
            fee_rate_bps = int(fee_rate_bps)
        except (TypeError, ValueError):
            fee_rate_bps = 0

        signed = sign_order(
            private_key=self.credentials.private_key,
            token_id=payload.tokenID,
            side=side,
            price=payload.price,
            size=payload.size,
            fee_rate_bps=fee_rate_bps,
            signature_type=sig_type,
            funder_address=self.funder_address,
            chain_id=self._chain_id,
            neg_risk=neg_risk,
        )

        body = signed.to_request_body(
            owner_api_key=self.credentials.api_key or "",
            order_type=payload.orderType.value,
        )
        return await self._request("POST", "/order", body=body)

    # Compatibility with the runtime's CLOBAdapter protocol.
    async def get_token_balance(self, token_id: str) -> float:
        rows = await self._request("GET", "/balance-allowances")
        for r in rows or []:
            if str(r.get("token_id") or r.get("tokenId") or "") == token_id:
                try:
                    return float(r.get("balance") or 0)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    async def order_book(self, token_id: str) -> dict:
        return await self._request("GET", f"/book?token_id={token_id}")
