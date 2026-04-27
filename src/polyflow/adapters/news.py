"""Public RSS/Atom news adapter for strategy automation.

This adapter consumes only public feeds. It does not use private, leaked, or
outcome-influencing sources, and it emits conservative directional nudges for
the news repricing strategy to validate against market prices and risk gates.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Protocol

import httpx

from ..strategies.news_repricing import PublicSourceEvent, hash_body
from ..types import Market


class NewsAdapter(Protocol):
    async def events_for_market(self, market: Market) -> list[PublicSourceEvent]: ...


@dataclass(frozen=True)
class NewsItem:
    source_name: str
    source_url: str
    title: str
    summary: str
    published_at: datetime


class RSSNewsAdapter:
    """Fetches public RSS/Atom feeds and matches items to market text."""

    def __init__(
        self,
        *,
        feed_urls: list[str],
        max_items_per_feed: int = 20,
        timeout_seconds: float = 8.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._feed_urls = feed_urls
        self._max_items_per_feed = max_items_per_feed
        self._timeout = timeout_seconds
        self._client = client

    async def events_for_market(self, market: Market) -> list[PublicSourceEvent]:
        if not self._feed_urls:
            return []
        items = await self._fetch_items()
        terms = _market_terms(market)
        if not terms:
            return []
        out: list[PublicSourceEvent] = []
        for item in items:
            haystack = f"{item.title} {item.summary}".lower()
            if not _matches_terms(haystack, terms):
                continue
            direction = _direction_from_text(haystack, market)
            if direction == 0.0:
                continue
            body = f"{item.title}\n{item.summary}"
            out.append(
                PublicSourceEvent(
                    source_name=item.source_name,
                    source_url=item.source_url,
                    body_hash=hash_body(body),
                    fetched_at=item.published_at,
                    reliability=_source_reliability(item.source_name),
                    direction=direction,
                    integrity_flags=(),
                    settlement_match=True,
                )
            )
        return out

    async def _fetch_items(self) -> list[NewsItem]:
        client = self._client or httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        owns = self._client is None
        try:
            items: list[NewsItem] = []
            for feed_url in self._feed_urls:
                try:
                    resp = await client.get(feed_url)
                    resp.raise_for_status()
                except httpx.HTTPError:
                    continue
                items.extend(_parse_feed(resp.text, feed_url)[: self._max_items_per_feed])
            return items
        finally:
            if owns:
                await client.aclose()


def _parse_feed(body: str, feed_url: str) -> list[NewsItem]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    source = _clean_text(_first_text(root, ["./channel/title", "./{*}title"]) or feed_url)
    raw_items = root.findall("./channel/item") or root.findall("./{*}entry")
    out: list[NewsItem] = []
    for item in raw_items:
        title = _clean_text(_first_text(item, ["title", "{*}title"]) or "")
        summary = _clean_text(
            _first_text(item, ["description", "summary", "{*}summary", "{*}content"]) or ""
        )
        link = _first_text(item, ["link", "guid", "{*}id"]) or feed_url
        atom_link = item.find("{*}link")
        if atom_link is not None and atom_link.attrib.get("href"):
            link = atom_link.attrib["href"]
        published = _parse_dt(
            _first_text(item, ["pubDate", "published", "updated", "{*}published", "{*}updated"])
        )
        if title:
            out.append(
                NewsItem(
                    source_name=source,
                    source_url=link,
                    title=title,
                    summary=summary,
                    published_at=published,
                )
            )
    return out


def _first_text(node: ET.Element, paths: list[str]) -> str | None:
    for path in paths:
        found = node.find(path)
        if found is not None and found.text:
            return found.text
    return None


def _clean_text(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", unescape(value))
    return " ".join(no_tags.split())


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        value = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _market_terms(market: Market) -> set[str]:
    text = f"{market.question} {market.category or ''}".lower()
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", text)
        if len(token) >= 4 and token not in _STOPWORDS
    }
    aliases: set[str] = set()
    if "manchester" in tokens or "united" in tokens:
        aliases.update({"manchester", "united", "man utd"})
    if "atalanta" in tokens:
        aliases.add("atalanta")
    if "pistons" in tokens or "magic" in tokens:
        aliases.update({"pistons", "magic"})
    return tokens | aliases


def _matches_terms(haystack: str, terms: set[str]) -> bool:
    hits = sum(1 for term in terms if term in haystack)
    return hits >= 2 or any(" " in term and term in haystack for term in terms)


def _direction_from_text(text: str, market: Market) -> float:
    positive = ("win", "wins", "beat", "beats", "lead", "leads", "confirmed", "starts")
    negative = ("lose", "loses", "lost", "injury", "injured", "out", "doubt", "suspended")
    yes_terms = _market_terms(market)
    has_market_term = any(term in text for term in yes_terms)
    if not has_market_term:
        return 0.0
    pos = any(term in text for term in positive)
    neg = any(term in text for term in negative)
    if pos and not neg:
        return 0.04
    if neg and not pos:
        return -0.04
    return 0.0


def _source_reliability(source_name: str) -> float:
    name = source_name.lower()
    if any(term in name for term in ("reuters", "associated press", "bbc")):
        return 0.90
    if any(term in name for term in ("espn", "coindesk")):
        return 0.82
    return 0.75


_STOPWORDS = {
    "will", "with", "this", "that", "from", "have", "after", "before",
    "market", "above", "below", "over", "under", "2025", "2026", "2027",
}
