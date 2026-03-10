"""Tests for the Google Calendar service."""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.calendar import CalendarService, _CACHE_TTL, _MAX_CALENDARS


# ---------------------------------------------------------------------------
# Sample API response fixture
# ---------------------------------------------------------------------------

_SAMPLE_EVENTS_RESPONSE = {
    "kind": "calendar#events",
    "items": [
        {
            "id": "abc123",
            "summary": "Team meeting",
            "description": "Monthly sync",
            "location": "Room 1",
            "start": {"dateTime": "2024-06-01T10:00:00+02:00"},
            "end": {"dateTime": "2024-06-01T11:00:00+02:00"},
        },
        {
            "id": "def456",
            "summary": "All-day event",
            "description": "",
            "location": "",
            "start": {"date": "2024-06-01"},
            "end": {"date": "2024-06-02"},
        },
    ],
}

_EMPTY_EVENTS_RESPONSE = {"kind": "calendar#events", "items": []}


def _make_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCalendarService:
    def setup_method(self):
        self.svc = CalendarService(
            calendar_ids=["cal1@group.calendar.google.com"],
            api_key="test-api-key",
        )

    @patch("services.calendar.requests.get")
    def test_get_events_returns_parsed_events(self, mock_get):
        mock_get.return_value = _make_response(_SAMPLE_EVENTS_RESPONSE)

        result = self.svc.get_events()

        assert len(result) == 2
        # All-day events (date-only start) sort before timed events on the same day
        summaries = {e["summary"] for e in result}
        assert "Team meeting" in summaries
        assert "All-day event" in summaries
        assert result[0]["calendar_id"] == "cal1@group.calendar.google.com"

    @patch("services.calendar.requests.get")
    def test_all_day_event_detected(self, mock_get):
        mock_get.return_value = _make_response(_SAMPLE_EVENTS_RESPONSE)

        result = self.svc.get_events()

        all_day = next(e for e in result if e["id"] == "def456")
        assert all_day["all_day"] is True
        assert all_day["start"] == "2024-06-01"

    @patch("services.calendar.requests.get")
    def test_empty_calendar_returns_empty_list(self, mock_get):
        mock_get.return_value = _make_response(_EMPTY_EVENTS_RESPONSE)

        result = self.svc.get_events()

        assert result == []

    @patch("services.calendar.requests.get")
    def test_results_are_cached(self, mock_get):
        mock_get.return_value = _make_response(_SAMPLE_EVENTS_RESPONSE)

        self.svc.get_events()
        self.svc.get_events()

        assert mock_get.call_count == 1

    @patch("services.calendar.requests.get")
    def test_cache_expires(self, mock_get):
        mock_get.return_value = _make_response(_SAMPLE_EVENTS_RESPONSE)

        self.svc.get_events()
        self.svc._cache_ts = time.monotonic() - _CACHE_TTL - 1
        self.svc.get_events()

        assert mock_get.call_count == 2

    @patch("services.calendar.requests.get")
    def test_api_key_included_in_request(self, mock_get):
        mock_get.return_value = _make_response(_SAMPLE_EVENTS_RESPONSE)

        self.svc.get_events()

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["key"] == "test-api-key"

    @patch("services.calendar.requests.get")
    def test_time_range_covers_today_and_tomorrow(self, mock_get):
        mock_get.return_value = _make_response(_EMPTY_EVENTS_RESPONSE)

        self.svc.get_events()

        _, kwargs = mock_get.call_args
        params = kwargs["params"]
        time_min = datetime.fromisoformat(params["timeMin"])
        time_max = datetime.fromisoformat(params["timeMax"])
        delta = time_max - time_min
        # Should span exactly 2 days (today + tomorrow)
        assert delta.days == 2

    def test_max_calendars_enforced(self):
        ids = [f"cal{i}@example.com" for i in range(10)]
        svc = CalendarService(calendar_ids=ids, api_key="key")
        assert len(svc._calendar_ids) == _MAX_CALENDARS

    @patch("services.calendar.requests.get")
    def test_multiple_calendars_merged(self, mock_get):
        mock_get.return_value = _make_response(_SAMPLE_EVENTS_RESPONSE)
        svc = CalendarService(
            calendar_ids=["cal1@example.com", "cal2@example.com"],
            api_key="key",
        )

        result = svc.get_events()

        # Both calendars return 2 events each → 4 total
        assert mock_get.call_count == 2
        assert len(result) == 4

    @patch("services.calendar.requests.get")
    def test_events_sorted_by_start_time(self, mock_get):
        response = {
            "items": [
                {
                    "id": "b",
                    "summary": "Later",
                    "start": {"dateTime": "2024-06-01T14:00:00+00:00"},
                    "end": {"dateTime": "2024-06-01T15:00:00+00:00"},
                },
                {
                    "id": "a",
                    "summary": "Earlier",
                    "start": {"dateTime": "2024-06-01T09:00:00+00:00"},
                    "end": {"dateTime": "2024-06-01T10:00:00+00:00"},
                },
            ]
        }
        mock_get.return_value = _make_response(response)

        result = self.svc.get_events()

        assert result[0]["summary"] == "Earlier"
        assert result[1]["summary"] == "Later"

    @patch("services.calendar.requests.get")
    def test_no_calendars_configured_returns_empty(self, mock_get):
        svc = CalendarService(calendar_ids=[], api_key="key")

        result = svc.get_events()

        assert result == []
        mock_get.assert_not_called()
