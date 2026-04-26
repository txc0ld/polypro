"""Polymarket data + execution adapters.

These are deliberately thin async interfaces. Production replaces the stubs
with the official Polymarket TypeScript CLOB client (over a sidecar) or a
Python port. The deterministic core never imports network code directly —
everything flows through these adapters.
"""
