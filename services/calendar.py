"""Google Calendar service – fetches events for today and tomorrow.

Uses the Google Calendar API v3 (public read-only access via API key).
Up to five calendar IDs may be configured; events are merged and sorted
by start time.
"""

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

_API_BASE = "https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
_CACHE_TTL = 300  # seconds (5 minutes)
_MAX_CALENDARS = 5


class CalendarService:
    """Aggregates Google Calendar events across multiple calendars."""

    def __init__(self, calendar_ids: list[str], api_key: str) -> None:
        self._calendar_ids = calendar_ids[:_MAX_CALENDARS]
        self._api_key = api_key
        self._cache: list[dict[str, Any]] | None = None
        self._cache_ts: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_events(self) -> list[dict[str, Any]]:
        """Return events for today and tomorrow, sorted by start time.

        Results are cached for *_CACHE_TTL* seconds to avoid hammering
        the Calendar API on every dashboard refresh.
        """
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_ts) < _CACHE_TTL:
            return self._cache

        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_of_tomorrow = today + timedelta(days=2)

        events: list[dict[str, Any]] = []
        for cal_id in self._calendar_ids:
            events.extend(self._fetch_calendar(cal_id, today, end_of_tomorrow))

        events.sort(key=lambda e: e.get("start") or "")

        self._cache = events
        self._cache_ts = now
        return events

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_calendar(
        self, cal_id: str, time_min: datetime, time_max: datetime
    ) -> list[dict[str, Any]]:
        """Fetch events from a single calendar between *time_min* and *time_max*."""
        url = _API_BASE.format(cal_id=requests.utils.quote(cal_id, safe=""))
        params: dict[str, Any] = {
            "key": self._api_key,
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 50,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        result: list[dict[str, Any]] = []
        for item in data.get("items", []):
            start = item.get("start", {})
            end = item.get("end", {})
            start_val = start.get("dateTime") or start.get("date", "")
            end_val = end.get("dateTime") or end.get("date", "")
            result.append(
                {
                    "id": item.get("id", ""),
                    "summary": item.get("summary", ""),
                    "description": item.get("description", ""),
                    "location": item.get("location", ""),
                    "start": start_val,
                    "end": end_val,
                    "all_day": "date" in start and "dateTime" not in start,
                    "calendar_id": cal_id,
                }
            )
        return result
