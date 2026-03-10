"""Tibber energy service – prices and consumption via the Tibber GraphQL API."""

import time
from typing import Any

import requests

_GRAPHQL_URL = "https://api.tibber.com/v1-beta/gql"
_CACHE_TTL = 60  # seconds

# Map address fragments to friendly labels
_HOME_LABELS: dict[str, str] = {
    "Trollahaugen 24": "Garasje",
    "Trollahaugen 28": "Heim",
}

_QUERY = """
{
  viewer {
    homes {
      address {
        address1
      }
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


def _label_for_address(address1: str) -> str:
    """Return a friendly label for a home address, or the address itself as fallback."""
    for fragment, label in _HOME_LABELS.items():
        if fragment in address1:
            return label
    return address1


class TibberService:
    """Fetches current electricity price and recent consumption from Tibber."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._cache: list[dict[str, Any]] | None = None
        self._cache_ts: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_status(self) -> list[dict[str, Any]] | dict[str, Any]:
        """Return price and consumption info for all registered homes."""
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
            self._cache = []
            self._cache_ts = now
            return self._cache

        result: list[dict[str, Any]] = []
        for home in homes:
            address1 = home.get("address", {}).get("address1", "")
            label = _label_for_address(address1)
            price_info = (
                home.get("currentSubscription", {})
                .get("priceInfo", {})
            )
            consumption_nodes = (
                home.get("consumption", {}).get("nodes", [])
            )
            result.append({
                "label": label,
                "current_price": price_info.get("current"),
                "today_prices": price_info.get("today", []),
                "consumption_24h": consumption_nodes,
            })

        self._cache = result
        self._cache_ts = now
        return result
