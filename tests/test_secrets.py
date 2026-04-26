"""Credential loading + redaction tests.

These tests use synthetic values only. They never touch the real .env.local in
the project root.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from polyflow.secrets import (
    Credentials,
    credentials_summary,
    load_credentials,
    load_env,
)


def _write_env(tmp_path: Path, body: str) -> Path:
    env = tmp_path / ".env.local"
    env.write_text(body, encoding="utf-8")
    return env


def test_parser_accepts_colon_or_equals(tmp_path: Path) -> None:
    _write_env(
        tmp_path,
        "POLYAPIKEY:11111111-1111-1111-1111-111111111111\n"
        "POLY_API_SECRET=fake-secret-base64\n"
        "# comment\n"
        "POLY_API_PASSPHRASE: fake-passphrase\n",
    )
    env = load_env(project_root=tmp_path)
    assert env["POLYAPIKEY"].startswith("11111111")
    assert env["POLY_API_SECRET"] == "fake-secret-base64"
    assert env["POLY_API_PASSPHRASE"] == "fake-passphrase"


def test_load_credentials_short_form(tmp_path: Path) -> None:
    _write_env(
        tmp_path,
        "POLYAPIKEY:22222222-2222-2222-2222-222222222222\n"
        "POLYAPIADDRESS:0xabcdef0123456789abcdef0123456789abcdef01\n",
    )
    creds = load_credentials(project_root=tmp_path)
    assert creds.has_read_credentials
    assert not creds.has_trade_credentials
    missing = creds.missing_for_trading()
    assert "POLY_API_SECRET" in missing
    assert "POLY_API_PASSPHRASE" in missing
    assert "POLY_PRIVATE_KEY" in missing


def test_redaction_does_not_leak_secret(tmp_path: Path) -> None:
    creds = Credentials(
        api_key="11111111-1111-1111-1111-111111111111",
        api_secret="totally-secret-value",
        api_passphrase="hush",
        private_key="0xdeadbeef" + "0" * 56,
        wallet_address="0xabcdef0123456789abcdef0123456789abcdef01",
    )
    summary = credentials_summary(creds)
    # Each secret should appear only as a 4…4 fingerprint, not in the clear.
    for k in ("api_key", "api_secret", "api_passphrase", "private_key"):
        assert "…" in summary[k] or summary[k] == "<set>"
        assert "totally-secret-value" not in summary[k]
        assert "11111111-1111-1111-1111-111111111111" not in summary[k]


def test_summary_marks_full_trade_creds(tmp_path: Path) -> None:
    creds = Credentials(
        api_key="k", api_secret="s", api_passphrase="p", private_key="pk",
        wallet_address="0xabc",
    )
    s = credentials_summary(creds)
    assert s["has_trade_credentials"] == "True"
    assert s["missing_for_trading"] == "<none>"
