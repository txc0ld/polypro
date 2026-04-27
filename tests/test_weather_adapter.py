"""ASOS / NOAA weather adapter tests (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest

from polyflow.adapters.weather import (
    WeatherAdapter,
    c_to_f,
    trajectory_probability,
)


SAMPLE_METAR = [
    {
        "icaoId": "KJFK",
        "reportTime": "2026-04-27T15:00:00Z",
        "temp": "12.5",
        "dewp": "8.0",
        "wspd": "9",
        "rawOb": "KJFK 271500Z 24009KT 10SM SCT200 13/08 A3010",
    }
]


def test_c_to_f() -> None:
    assert c_to_f(0) == 32.0
    assert c_to_f(100) == 212.0
    assert c_to_f(20) == 68.0


@pytest.mark.asyncio
async def test_fetch_parses_temperature() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.params)
        return httpx.Response(200, json=SAMPLE_METAR)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = WeatherAdapter(client=client)
        obs = await adapter.fetch("KJFK")

    assert obs is not None
    assert obs.station_id == "KJFK"
    assert obs.temperature_c == pytest.approx(12.5)
    assert obs.temperature_f == pytest.approx(54.5)
    assert "ids=KJFK" in seen["query"]


@pytest.mark.asyncio
async def test_fetch_handles_404() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = WeatherAdapter(client=client)
        obs = await adapter.fetch("XXXX")
    assert obs is None


@pytest.mark.asyncio
async def test_fetch_handles_empty_array() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = WeatherAdapter(client=client)
        obs = await adapter.fetch("KJFK")
    assert obs is None


class TestTrajectoryProbability:
    def test_clear_above(self) -> None:
        # Currently 60F, threshold 50F, 1h to close, no drift → P(above) ≈ 1
        p = trajectory_probability(
            current_temp_f=60.0, threshold_f=50.0, direction="above",
            seconds_to_close=3600, rate_of_change_f_per_hour=0.0,
        )
        assert p > 0.99

    def test_clear_below(self) -> None:
        p = trajectory_probability(
            current_temp_f=40.0, threshold_f=50.0, direction="above",
            seconds_to_close=3600, rate_of_change_f_per_hour=0.0,
        )
        assert p < 0.01

    def test_drift_pushes_toward_threshold(self) -> None:
        # 40F currently, 1h to close, +5F/hour drift → expected 45F → still <50
        p = trajectory_probability(
            current_temp_f=40.0, threshold_f=50.0, direction="above",
            seconds_to_close=3600, rate_of_change_f_per_hour=5.0,
        )
        assert 0.0 < p < 0.5

    def test_already_resolved(self) -> None:
        p = trajectory_probability(
            current_temp_f=60.0, threshold_f=50.0, direction="above",
            seconds_to_close=0, rate_of_change_f_per_hour=0.0,
        )
        assert p == 0.5  # neutral when no time
