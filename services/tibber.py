"""Tibber energy service – prices and consumption via the Tibber GraphQL API."""

import time
from typing import Any

import requests

_GRAPHQL_URL = "https://api.tibber.com/v1-beta/gql"
_CACHE_TTL = 60  # seconds

_QUERY = """
{
  viewer {
    homes {
      currentSubscription {
        priceInfo {
          current {
            total
            energy
            tax
            startsAt
            currency
            level
          }
          today {
            total
            energy
            tax
            startsAt
            level
          }
        }
      }
      consumption(resolution: HOURLY, last: 24) {
        nodes {
          from
          to
          cost
          unitPrice
          unitPriceVAT
          consumption
          consumptionUnit
          currency
        }
      }
    }
  }
}
"""


class TibberService:
    """Fetches current electricity price and recent consumption from Tibber."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._cache: dict[str, Any] | None = None
        self._cache_ts: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return price and consumption info for the first registered home."""
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_ts) < _CACHE_TTL:
            return self._cache

        if not self._token:
            return {"error": "TIBBER_TOKEN not configured"}

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        resp = requests.post(
            _GRAPHQL_URL, json={"query": _QUERY}, headers=headers, timeout=10
        )
        resp.raise_for_status()
        raw = resp.json()

        homes = (
            raw.get("data", {}).get("viewer", {}).get("homes", [])
        )
        if not homes:
            self._cache = {}
            self._cache_ts = now
            return self._cache

        home = homes[0]
        price_info = (
            home.get("currentSubscription", {})
            .get("priceInfo", {})
        )
        consumption_nodes = (
            home.get("consumption", {}).get("nodes", [])
        )

        result: dict[str, Any] = {
            "current_price": price_info.get("current"),
            "today_prices": price_info.get("today", []),
            "consumption_24h": consumption_nodes,
        }
        self._cache = result
        self._cache_ts = now
        return result
