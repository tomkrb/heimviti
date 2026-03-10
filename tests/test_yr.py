"""Tests for the yr.no weather service."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from services.yr import YrService, _CACHE_TTL


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_RESPONSE = {
    "properties": {
        "timeseries": [
            {
                "time": "2024-01-01T12:00:00Z",
                "data": {
                    "instant": {
                        "details": {
                            "air_temperature": -3.2,
                            "wind_speed": 5.1,
                            "wind_from_direction": 180.0,
                            "relative_humidity": 78.0,
                        }
                    },
                    "next_1_hours": {
                        "summary": {"symbol_code": "snow"},
                        "details": {"precipitation_amount": 0.5},
                    },
                },
            }
        ]
    }
}


def _make_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestYrService:
    def setup_method(self):
        self.svc = YrService(lat=63.43, lon=10.39)

    @patch("services.yr.requests.get")
    def test_get_current_returns_expected_fields(self, mock_get):
        mock_get.return_value = _make_response(SAMPLE_RESPONSE)

        result = self.svc.get_current()

        assert result["air_temperature"] == -3.2
        assert result["wind_speed"] == 5.1
        assert result["symbol_code"] == "snow"
        assert result["time"] == "2024-01-01T12:00:00Z"

    @patch("services.yr.requests.get")
    def test_result_is_cached(self, mock_get):
        mock_get.return_value = _make_response(SAMPLE_RESPONSE)

        self.svc.get_current()
        self.svc.get_current()

        # Second call should NOT trigger a new HTTP request
        assert mock_get.call_count == 1

    @patch("services.yr.requests.get")
    def test_cache_expires(self, mock_get):
        mock_get.return_value = _make_response(SAMPLE_RESPONSE)

        self.svc.get_current()
        # Backdate the cache timestamp so it looks stale
        self.svc._cache_ts = time.monotonic() - _CACHE_TTL - 1
        self.svc.get_current()

        assert mock_get.call_count == 2

    @patch("services.yr.requests.get")
    def test_empty_timeseries_returns_empty_dict(self, mock_get):
        mock_get.return_value = _make_response({"properties": {"timeseries": []}})

        result = self.svc.get_current()

        assert result == {}

    @patch("services.yr.requests.get")
    def test_user_agent_header_sent(self, mock_get):
        mock_get.return_value = _make_response(SAMPLE_RESPONSE)

        self.svc.get_current()

        _, kwargs = mock_get.call_args
        assert "User-Agent" in kwargs["headers"]
        assert "heimviti" in kwargs["headers"]["User-Agent"]
