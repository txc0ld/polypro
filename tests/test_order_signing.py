"""EIP-712 Order signing tests.

The signer must:
  - reject malformed inputs *before* signing,
  - produce deterministic outputs given a fixed salt,
  - recover the signer address from the signature (round-trip).
"""

from __future__ import annotations

import pytest

from polyflow.order_signing import (
    CTF_EXCHANGE_ADDRESS,
    NEG_RISK_EXCHANGE_ADDRESS,
    OrderSide,
    SignatureType,
    build_typed_data,
    sign_order,
)

ethaccount = pytest.importorskip("eth_account")

# Hardhat account #0 — public test key. Never use a real key in tests.
TEST_PK = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_ADDR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
FUNDER = "0x1111111111111111111111111111111111111111"


class TestTypedData:
    def test_ctf_domain(self) -> None:
        td = build_typed_data(
            salt=1, maker=TEST_ADDR, signer=TEST_ADDR, taker="0x" + "00" * 20,
            token_id=42, maker_amount=10_000, taker_amount=20_000,
            expiration=0, nonce=0, fee_rate_bps=200,
            side=OrderSide.BUY, signature_type=SignatureType.EOA,
        )
        assert td["domain"]["verifyingContract"] == CTF_EXCHANGE_ADDRESS

    def test_neg_risk_domain(self) -> None:
        td = build_typed_data(
            salt=1, maker=TEST_ADDR, signer=TEST_ADDR, taker="0x" + "00" * 20,
            token_id=42, maker_amount=10_000, taker_amount=20_000,
            expiration=0, nonce=0, fee_rate_bps=200,
            side=OrderSide.BUY, signature_type=SignatureType.EOA,
            neg_risk=True,
        )
        assert td["domain"]["verifyingContract"] == NEG_RISK_EXCHANGE_ADDRESS

    def test_order_type_has_12_fields(self) -> None:
        td = build_typed_data(
            salt=1, maker=TEST_ADDR, signer=TEST_ADDR, taker="0x" + "00" * 20,
            token_id=42, maker_amount=10_000, taker_amount=20_000,
            expiration=0, nonce=0, fee_rate_bps=200,
            side=OrderSide.BUY, signature_type=SignatureType.EOA,
        )
        assert len(td["types"]["Order"]) == 12


class TestSignOrder:
    def test_buy_eoa(self) -> None:
        order = sign_order(
            private_key=TEST_PK,
            token_id=42,
            side=OrderSide.BUY,
            price="0.55",
            size="10",
            fee_rate_bps=200,
            signature_type=SignatureType.EOA,
            salt=12345,
        )
        assert order.signer.lower() == TEST_ADDR.lower()
        assert order.maker.lower() == TEST_ADDR.lower()
        assert order.side == int(OrderSide.BUY)
        assert order.signatureType == int(SignatureType.EOA)
        # 10 outcome tokens at 0.55 → 5.5 USDC = 5_500_000 base units
        assert order.makerAmount == "5500000"
        # 10 outcome tokens × 1e6 = 10_000_000
        assert order.takerAmount == "10000000"

    def test_buy_proxy_uses_funder_as_maker(self) -> None:
        order = sign_order(
            private_key=TEST_PK,
            token_id=42,
            side=OrderSide.BUY,
            price="0.55",
            size="10",
            fee_rate_bps=200,
            signature_type=SignatureType.POLY_PROXY,
            funder_address=FUNDER,
            salt=12345,
        )
        assert order.maker.lower() == FUNDER.lower()
        assert order.signer.lower() == TEST_ADDR.lower()

    def test_proxy_without_funder_raises(self) -> None:
        with pytest.raises(ValueError):
            sign_order(
                private_key=TEST_PK, token_id=42, side=OrderSide.BUY,
                price="0.55", size="10", fee_rate_bps=200,
                signature_type=SignatureType.POLY_PROXY,
                funder_address=None,
            )

    def test_invalid_price_rejected(self) -> None:
        for bad in ("0.0", "1.0", "-0.1", "1.5"):
            with pytest.raises(ValueError):
                sign_order(
                    private_key=TEST_PK, token_id=42, side=OrderSide.BUY,
                    price=bad, size="10", fee_rate_bps=200,
                    signature_type=SignatureType.EOA,
                )

    def test_negative_size_rejected(self) -> None:
        with pytest.raises(ValueError):
            sign_order(
                private_key=TEST_PK, token_id=42, side=OrderSide.BUY,
                price="0.55", size="-1", fee_rate_bps=200,
                signature_type=SignatureType.EOA,
            )

    def test_signature_recovers_to_signer(self) -> None:
        from eth_account import Account
        from eth_account.messages import encode_typed_data

        order = sign_order(
            private_key=TEST_PK, token_id=42, side=OrderSide.BUY,
            price="0.55", size="10", fee_rate_bps=200,
            signature_type=SignatureType.POLY_PROXY,
            funder_address=FUNDER, salt=12345,
        )
        td = build_typed_data(
            salt=int(order.salt), maker=order.maker, signer=order.signer,
            taker=order.taker, token_id=int(order.tokenId),
            maker_amount=int(order.makerAmount), taker_amount=int(order.takerAmount),
            expiration=int(order.expiration), nonce=int(order.nonce),
            fee_rate_bps=int(order.feeRateBps),
            side=OrderSide(order.side), signature_type=SignatureType(order.signatureType),
        )
        signable = encode_typed_data(full_message=td)
        recovered = Account.recover_message(signable, signature=order.signature)
        assert recovered.lower() == TEST_ADDR.lower()

    def test_deterministic_with_pinned_salt(self) -> None:
        kwargs = dict(
            private_key=TEST_PK, token_id=42, side=OrderSide.BUY,
            price="0.55", size="10", fee_rate_bps=200,
            signature_type=SignatureType.EOA, salt=999,
        )
        a = sign_order(**kwargs)
        b = sign_order(**kwargs)
        assert a.signature == b.signature
