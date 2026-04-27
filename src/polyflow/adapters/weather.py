"""ASOS / NOAA Aviation Weather adapter.

Free public source for current conditions at ~1900 US airport stations.
The ASOS network underlies most Polymarket weather market resolutions
(Wunderground itself reads ASOS for major airports).

Endpoint:
    https://aviationweather.gov/api/data/metar?ids=KJFK&format=json

Returns the current METAR observation for a station including temperature
in Celsius. We convert to Fahrenheit (Polymarket questions are typically
F-denominated for US markets).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

_BASE = "https://aviationweather.gov/api/data/metar"


@dataclass(frozen=True)
class WeatherObservation:
    station_id: str
    observed_at: datetime
    temperature_f: float
    temperature_c: float
    dewpoint_c: float | None
    wind_kt: float | None
    raw_metar: str


def c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


class WeatherAdapter:
    """Async pull of the latest METAR for one or more ASOS stations."""

    def __init__(
        self,
        *,
        base_url: str = _BASE,
        timeout_seconds: float = 8.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    async def __aenter__(self) -> "WeatherAdapter":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch(self, station_id: str) -> WeatherObservation | None:
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            try:
                resp = await client.get(
                    self._base_url,
                    params={"ids": station_id, "format": "json"},
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError):
                return None
        finally:
            if owns:
                await client.aclose()

        if not isinstance(data, list) or not data:
            return None
        record = data[0]
        try:
            temp_c = float(record["temp"])
        except (KeyError, TypeError, ValueError):
            return None

        observed_at = _parse_observed(record)
        return WeatherObservation(
            station_id=station_id.upper(),
            observed_at=observed_at,
            temperature_f=c_to_f(temp_c),
            temperature_c=temp_c,
            dewpoint_c=_safe_float(record.get("dewp")),
            wind_kt=_safe_float(record.get("wspd")),
            raw_metar=str(record.get("rawOb") or ""),
        )


def _safe_float(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _parse_observed(record: dict) -> datetime:
    raw = record.get("reportTime") or record.get("obsTime")
    if raw is None:
        return datetime.now(timezone.utc)
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    try:
        if isinstance(raw, str) and raw.endswith("Z"):
            raw = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return datetime.now(timezone.utc)


def trajectory_probability(
    *,
    current_temp_f: float,
    threshold_f: float,
    direction: str,                  # 'above' or 'below'
    seconds_to_close: float,
    rate_of_change_f_per_hour: float,
    sigma_f: float = 1.5,
) -> float:
    """Closed-form probability of finishing above/below threshold given a
    drift + Gaussian-noise temperature model.

    Useful as a starting prior for the Bayesian updater on weather markets.
    """
    if seconds_to_close <= 0:
        return 0.5
    hours = seconds_to_close / 3600.0
    expected_temp = current_temp_f + rate_of_change_f_per_hour * hours
    std = max(sigma_f * (hours ** 0.5), 1e-6)
    # P(end > threshold) under Normal(expected_temp, std)
    from math import erf, sqrt
    z = (threshold_f - expected_temp) / (std * sqrt(2))
    p_above = 0.5 * (1 - erf(z))
    return p_above if direction == "above" else 1.0 - p_above
