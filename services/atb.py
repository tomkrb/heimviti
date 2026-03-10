"""Bus departures – fetches real-time data from the EnTur Journey Planner API.

AtB (Trondheim municipality transport) is exposed through the national
Norwegian public-transport aggregator at api.entur.io.
"""

import time
from typing import Any

import requests

_GRAPHQL_URL = "https://api.entur.io/journey-planner/v3/graphql"
_ET_CLIENT_NAME = "heimviti"
_CACHE_TTL = 30  # seconds – real-time departures change quickly

_QUERY = """
query Departures($stopId: String!, $numberOfDepartures: Int!) {
  stopPlace(id: $stopId) {
    id
    name
    estimatedCalls(
      numberOfDepartures: $numberOfDepartures
      arrivalDeparture: departures
      includeCancelledTrips: true
    ) {
      realtime
      expectedDepartureTime
      aimedDepartureTime
      cancellation
      destinationDisplay { frontText }
      serviceJourney {
        journeyPattern {
          line { publicCode transportMode }
        }
      }
    }
  }
}
"""


class AtbService:
    """Fetches upcoming bus departures for a given stop via the EnTur API."""

    def __init__(self, stop_id: str, number_of_departures: int = 5) -> None:
        self._stop_id = stop_id
        self._n = number_of_departures
        self._cache: list[dict[str, Any]] = []
        self._cache_ts: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_departures(self) -> list[dict[str, Any]]:
        """Return a list of upcoming departures (simplified dicts)."""
        now = time.monotonic()
        if self._cache and (now - self._cache_ts) < _CACHE_TTL:
            return self._cache

        payload = {
            "query": _QUERY,
            "variables": {
                "stopId": self._stop_id,
                "numberOfDepartures": self._n,
            },
        }
        headers = {
            "ET-Client-Name": _ET_CLIENT_NAME,
            "Content-Type": "application/json",
        }
        resp = requests.post(
            _GRAPHQL_URL, json=payload, headers=headers, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        stop_place = data.get("data", {}).get("stopPlace") or {}
        calls = stop_place.get("estimatedCalls", [])

        departures = []
        for call in calls:
            journey = (
                call.get("serviceJourney", {})
                .get("journeyPattern", {})
                .get("line", {})
            )
            departures.append(
                {
                    "line": journey.get("publicCode"),
                    "mode": journey.get("transportMode"),
                    "destination": (
                        call.get("destinationDisplay", {}) or {}
                    ).get("frontText"),
                    "aimed_departure": call.get("aimedDepartureTime"),
                    "expected_departure": call.get("expectedDepartureTime"),
                    "realtime": call.get("realtime", False),
                    "cancelled": call.get("cancellation", False),
                }
            )

        self._cache = departures
        self._cache_ts = now
        return departures
