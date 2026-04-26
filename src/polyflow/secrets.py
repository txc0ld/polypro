"""Environment + credential loader.

The runtime never imports raw env values. Everything goes through
``Credentials``, which loads from the OS env first and falls back to a
``.env.local`` file in the project root. The loader accepts either ``KEY=VAL``
or ``KEY:VAL`` per line — values containing ``:`` after the first separator
are preserved.

Hard rule: secret values are never logged, printed, or returned in error
messages. The CLI's ``show-credentials`` command prints presence + a 4-char
prefix only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_env_file(path: Path) -> dict[str, str]:
    """Tolerant parser. Skips comments and blank lines."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Split on the first '=' or ':' — accept either.
        sep = -1
        for i, ch in enumerate(line):
            if ch in ("=", ":"):
                sep = i
                break
        if sep < 0:
            continue
        key = line[:sep].strip()
        val = line[sep + 1 :].strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def load_env(*, project_root: Path | str | None = None) -> dict[str, str]:
    """Return the merged env: OS environment shadows any .env.local entries."""
    root = Path(project_root) if project_root else Path.cwd()
    file_env = _parse_env_file(root / ".env.local")
    return {**file_env, **{k: v for k, v in os.environ.items() if k in file_env or k.startswith("POLY")}}


@dataclass(frozen=True)
class Credentials:
    """Polymarket CLOB credentials.

    Order placement requires *all four* of:
      - api_key        (L2 API key UUID)
      - api_secret     (HMAC base64; CLOB sets this when you derive the key)
      - api_passphrase (set during key derivation)
      - private_key    (Polygon EOA private key for L1 signing)

    Plus, for proxy-wallet users (the standard Polymarket flow,
    ``signatureType=POLY_PROXY``):
      - funder_address (the proxy contract that holds USDC + outcome tokens)

    The wallet address is derivable from the private key and is exposed here for
    convenience (display + bankroll lookup) but is *not itself a credential*.
    """

    api_key: str | None
    api_secret: str | None
    api_passphrase: str | None
    private_key: str | None
    wallet_address: str | None
    funder_address: str | None = None

    @property
    def has_read_credentials(self) -> bool:
        """Do we have enough to identify the operator (address)?"""
        return bool(self.wallet_address)

    @property
    def has_trade_credentials(self) -> bool:
        """Do we have everything required to *sign* orders?"""
        return all((self.api_key, self.api_secret, self.api_passphrase, self.private_key))

    def missing_for_trading(self) -> list[str]:
        missing: list[str] = []
        if not self.api_key:
            missing.append("POLY_API_KEY")
        if not self.api_secret:
            missing.append("POLY_API_SECRET")
        if not self.api_passphrase:
            missing.append("POLY_API_PASSPHRASE")
        if not self.private_key:
            missing.append("POLY_PRIVATE_KEY")
        return missing


def _redact(value: str | None) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 8:
        return "<set>"
    return f"{value[:4]}…{value[-4:]}"


def load_credentials(*, project_root: Path | str | None = None) -> Credentials:
    """Load Polymarket credentials from env. Accepts the project's existing
    ``POLYAPIKEY`` / ``POLYAPIADDRESS`` short-form names alongside the canonical
    ``POLY_API_KEY`` / ``POLY_WALLET_ADDRESS``.
    """
    env = load_env(project_root=project_root)

    def first(*names: str) -> str | None:
        for n in names:
            v = env.get(n) or os.environ.get(n)
            if v:
                return v
        return None

    return Credentials(
        api_key=first("POLY_API_KEY", "POLYAPIKEY"),
        api_secret=first("POLY_API_SECRET", "POLYAPISECRET"),
        api_passphrase=first("POLY_API_PASSPHRASE", "POLYAPIPASSPHRASE"),
        private_key=first("POLY_PRIVATE_KEY", "POLYPRIVATEKEY"),
        wallet_address=first("POLY_WALLET_ADDRESS", "POLYAPIADDRESS"),
        funder_address=first("POLY_FUNDER_ADDRESS", "POLYFUNDERADDRESS"),
    )


def credentials_summary(creds: Credentials) -> dict[str, str]:
    """Return a redacted summary safe to print or log."""
    return {
        "api_key": _redact(creds.api_key),
        "api_secret": _redact(creds.api_secret),
        "api_passphrase": _redact(creds.api_passphrase),
        "private_key": _redact(creds.private_key),
        "wallet_address": _redact(creds.wallet_address),
        "funder_address": _redact(creds.funder_address),
        "has_read_credentials": str(creds.has_read_credentials),
        "has_trade_credentials": str(creds.has_trade_credentials),
        "missing_for_trading": ",".join(creds.missing_for_trading()) or "<none>",
    }
