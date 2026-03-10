"""Weather service – fetches current conditions from api.met.no (yr.no)."""

import time
from typing import Any

import requests

_API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
_USER_AGENT = "heimviti/1.0 github.com/heimviti"
_CACHE_TTL = 300  # seconds (met.no recommends at least 5 min)


class YrService:
    """Thin wrapper around the MET Norway Locationforecast 2.0 API."""

    def __init__(self, lat: float, lon: float) -> None:
        self._lat = lat
        self._lon = lon
        self._cache: dict[str, Any] = {}
        self._cache_ts: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_current(self) -> dict[str, Any]:
        """Return a flat dict with the most relevant current-hour values."""
        raw = self._fetch()
        timeseries = raw.get("properties", {}).get("timeseries", [])
        if not timeseries:
            return {}

        entry = timeseries[0]
        instant = entry.get("data", {}).get("instant", {}).get("details", {})
        next_1h = (
            entry.get("data", {})
            .get("next_1_hours", {})
            .get("summary", {})
        )

        return {
            "time": entry.get("time"),
            "air_temperature": instant.get("air_temperature"),
            "wind_speed": instant.get("wind_speed"),
            "wind_from_direction": instant.get("wind_from_direction"),
            "relative_humidity": instant.get("relative_humidity"),
            "symbol_code": next_1h.get("symbol_code"),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._cache and (now - self._cache_ts) < _CACHE_TTL:
            return self._cache

        params = {"lat": self._lat, "lon": self._lon}
        headers = {"User-Agent": _USER_AGENT}
        resp = requests.get(_API_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        self._cache = resp.json()
        self._cache_ts = now
        return self._cache
