"""Polymarket CTF Exchange EIP-712 Order signing.

Constructs and signs an ``Order`` typed-data payload against the Polymarket
CTF Exchange contract. Two contract variants exist:

  - **CTF Exchange** (standard binary markets):
      0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E
  - **Neg-risk Exchange** (related-outcome basket markets):
      0xC5d563A36AE78145C45a50134d48A1215220f80a

The contract enforces these invariants on every order; we re-check them
locally so a malformed order never reaches the wire:

  - prices in (0, 1) with 6-decimal base-unit math
  - ``side`` in {0=BUY, 1=SELL}
  - ``signatureType`` in {0=EOA, 1=POLY_PROXY, 2=POLY_GNOSIS_SAFE}
  - ``maker == signer`` for EOA, otherwise ``maker == funder_address``
  - integer amounts agree with side and price (small rounding tolerance)

Lazy-imports ``eth-account``; the optional ``[trade]`` extra is required.
"""

from __future__ import annotations

import secrets as _pysecrets
from dataclasses import dataclass
from decimal import Decimal
from enum import IntEnum
from typing import Any


CTF_EXCHANGE_ADDRESS = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_EXCHANGE_ADDRESS = "0xC5d563A36AE78145C45a50134d48A1215220f80a"

POLYGON_CHAIN_ID = 137

USDC_DECIMALS = 6
OUTCOME_TOKEN_DECIMALS = 6  # Polymarket CTF outcome tokens use 6 decimals
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


class OrderSide(IntEnum):
    BUY = 0
    SELL = 1


class SignatureType(IntEnum):
    EOA = 0
    POLY_PROXY = 1
    POLY_GNOSIS_SAFE = 2


@dataclass(frozen=True)
class SignedOrder:
    """Final, ready-to-submit order body."""

    salt: str
    maker: str
    signer: str
    taker: str
    tokenId: str
    makerAmount: str
    takerAmount: str
    expiration: str
    nonce: str
    feeRateBps: str
    side: int
    signatureType: int
    signature: str

    def to_request_body(self, *, owner_api_key: str, order_type: str) -> dict[str, Any]:
        return {
            "order": {
                "salt": self.salt,
                "maker": self.maker,
                "signer": self.signer,
                "taker": self.taker,
                "tokenId": self.tokenId,
                "makerAmount": self.makerAmount,
                "takerAmount": self.takerAmount,
                "expiration": self.expiration,
                "nonce": self.nonce,
                "feeRateBps": self.feeRateBps,
                "side": self.side,
                "signatureType": self.signatureType,
                "signature": self.signature,
            },
            "owner": owner_api_key,
            "orderType": order_type,
        }


def _to_base_units(amount: float | str | Decimal, decimals: int) -> int:
    """Decimal → integer base units. Banker's rounding to avoid float drift."""
    d = Decimal(str(amount))
    scaled = (d * (Decimal(10) ** decimals)).to_integral_value()
    if scaled < 0:
        raise ValueError("amount must be >= 0")
    return int(scaled)


def _verify_amounts(
    *, side: OrderSide, price: Decimal, size: Decimal, makerAmount: int, takerAmount: int
) -> None:
    """Cross-check that integer amounts match (side, price, size) within 1 base-unit."""
    if not (Decimal("0") < price < Decimal("1")):
        raise ValueError("price must be in (0, 1)")
    if size <= 0:
        raise ValueError("size must be > 0")

    if side is OrderSide.BUY:
        # BUY YES: pay USDC → get outcome tokens
        expected_maker = _to_base_units(price * size, USDC_DECIMALS)
        expected_taker = _to_base_units(size, OUTCOME_TOKEN_DECIMALS)
    else:
        # SELL: give outcome tokens → receive USDC
        expected_maker = _to_base_units(size, OUTCOME_TOKEN_DECIMALS)
        expected_taker = _to_base_units(price * size, USDC_DECIMALS)

    if abs(expected_maker - makerAmount) > 1:
        raise ValueError(f"makerAmount mismatch: have {makerAmount}, expected ≈ {expected_maker}")
    if abs(expected_taker - takerAmount) > 1:
        raise ValueError(f"takerAmount mismatch: have {takerAmount}, expected ≈ {expected_taker}")


def build_typed_data(
    *,
    salt: int,
    maker: str,
    signer: str,
    taker: str,
    token_id: int | str,
    maker_amount: int,
    taker_amount: int,
    expiration: int,
    nonce: int,
    fee_rate_bps: int,
    side: OrderSide,
    signature_type: SignatureType,
    chain_id: int = POLYGON_CHAIN_ID,
    neg_risk: bool = False,
) -> dict[str, Any]:
    """Build the EIP-712 typed-data dict the wallet must sign."""
    verifying_contract = NEG_RISK_EXCHANGE_ADDRESS if neg_risk else CTF_EXCHANGE_ADDRESS
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "Order": [
                {"name": "salt", "type": "uint256"},
                {"name": "maker", "type": "address"},
                {"name": "signer", "type": "address"},
                {"name": "taker", "type": "address"},
                {"name": "tokenId", "type": "uint256"},
                {"name": "makerAmount", "type": "uint256"},
                {"name": "takerAmount", "type": "uint256"},
                {"name": "expiration", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "feeRateBps", "type": "uint256"},
                {"name": "side", "type": "uint8"},
                {"name": "signatureType", "type": "uint8"},
            ],
        },
        "primaryType": "Order",
        "domain": {
            "name": "Polymarket CTF Exchange",
            "version": "1",
            "chainId": chain_id,
            "verifyingContract": verifying_contract,
        },
        "message": {
            "salt": salt,
            "maker": maker,
            "signer": signer,
            "taker": taker,
            "tokenId": int(token_id),
            "makerAmount": maker_amount,
            "takerAmount": taker_amount,
            "expiration": expiration,
            "nonce": nonce,
            "feeRateBps": fee_rate_bps,
            "side": int(side),
            "signatureType": int(signature_type),
        },
    }


def sign_order(
    *,
    private_key: str,
    token_id: int | str,
    side: OrderSide,
    price: float | str | Decimal,
    size: float | str | Decimal,
    fee_rate_bps: int,
    signature_type: SignatureType = SignatureType.POLY_PROXY,
    funder_address: str | None = None,
    expiration: int = 0,
    nonce: int = 0,
    salt: int | None = None,
    chain_id: int = POLYGON_CHAIN_ID,
    neg_risk: bool = False,
) -> SignedOrder:
    """Sign and return a ``SignedOrder`` ready for ``POST /order``.

    Validates every invariant before signing — a malformed order is *never*
    produced.
    """
    try:
        from eth_account import Account  # type: ignore[import-not-found]
        from eth_account.messages import encode_typed_data  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "Order signing requires the 'trade' extra. Install with:\n"
            "    pip install -e \".[trade]\""
        ) from e

    account = Account.from_key(private_key)
    signer = account.address

    # Determine maker per signature_type
    if signature_type is SignatureType.EOA:
        maker = signer
    else:
        if not funder_address:
            raise ValueError(
                f"signature_type={signature_type.name} requires funder_address (the proxy "
                "or Gnosis Safe that holds the funds)."
            )
        maker = funder_address

    # Convert + validate amounts
    p = Decimal(str(price))
    s = Decimal(str(size))
    if side is OrderSide.BUY:
        maker_amount = _to_base_units(p * s, USDC_DECIMALS)
        taker_amount = _to_base_units(s, OUTCOME_TOKEN_DECIMALS)
    else:
        maker_amount = _to_base_units(s, OUTCOME_TOKEN_DECIMALS)
        taker_amount = _to_base_units(p * s, USDC_DECIMALS)
    _verify_amounts(
        side=side, price=p, size=s, makerAmount=maker_amount, takerAmount=taker_amount
    )

    if fee_rate_bps < 0 or fee_rate_bps > 10_000:
        raise ValueError("fee_rate_bps must be in [0, 10000]")

    # Salt: 256-bit random unless caller pinned it (for deterministic tests).
    salt_int = salt if salt is not None else _pysecrets.randbits(256)

    typed = build_typed_data(
        salt=salt_int,
        maker=maker,
        signer=signer,
        taker=ZERO_ADDRESS,
        token_id=token_id,
        maker_amount=maker_amount,
        taker_amount=taker_amount,
        expiration=expiration,
        nonce=nonce,
        fee_rate_bps=fee_rate_bps,
        side=side,
        signature_type=signature_type,
        chain_id=chain_id,
        neg_risk=neg_risk,
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

    return SignedOrder(
        salt=str(salt_int),
        maker=maker,
        signer=signer,
        taker=ZERO_ADDRESS,
        tokenId=str(token_id),
        makerAmount=str(maker_amount),
        takerAmount=str(taker_amount),
        expiration=str(expiration),
        nonce=str(nonce),
        feeRateBps=str(fee_rate_bps),
        side=int(side),
        signatureType=int(signature_type),
        signature=sig_hex,
    )
