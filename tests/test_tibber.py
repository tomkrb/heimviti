"""Tests for the Tibber energy service."""

import time
from unittest.mock import MagicMock, patch

from services.tibber import TibberService, _CACHE_TTL

SAMPLE_RESPONSE = {
    "data": {
        "viewer": {
            "homes": [
                {
                    "currentSubscription": {
                        "priceInfo": {
                            "current": {
                                "total": 1.2345,
                                "energy": 0.9,
                                "tax": 0.3345,
                                "startsAt": "2024-01-01T12:00:00+01:00",
                                "currency": "NOK",
                                "level": "NORMAL",
                            },
                            "today": [
                                {
                                    "total": 1.1,
                                    "energy": 0.8,
                                    "tax": 0.3,
                                    "startsAt": "2024-01-01T00:00:00+01:00",
                                    "level": "CHEAP",
                                }
                            ],
                        }
                    },
                    "consumption": {
                        "nodes": [
                            {
                                "from": "2024-01-01T11:00:00+01:00",
                                "to": "2024-01-01T12:00:00+01:00",
                                "cost": 2.5,
                                "unitPrice": 1.2,
                                "unitPriceVAT": 0.3,
                                "consumption": 2.08,
                                "consumptionUnit": "kWh",
                                "currency": "NOK",
                            }
                        ]
                    },
                }
            ]
        }
    }
}


def _make_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


class TestTibberService:
    def setup_method(self):
        self.svc = TibberService(token="fake-token")

    @patch("services.tibber.requests.post")
    def test_get_status_returns_current_price(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        result = self.svc.get_status()

        assert result["current_price"]["total"] == 1.2345
        assert result["current_price"]["currency"] == "NOK"

    @patch("services.tibber.requests.post")
    def test_get_status_returns_consumption(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        result = self.svc.get_status()

        assert len(result["consumption_24h"]) == 1
        assert result["consumption_24h"][0]["consumption"] == 2.08

    @patch("services.tibber.requests.post")
    def test_result_is_cached(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        self.svc.get_status()
        self.svc.get_status()

        assert mock_post.call_count == 1

    @patch("services.tibber.requests.post")
    def test_cache_expires(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        self.svc.get_status()
        self.svc._cache_ts = time.monotonic() - _CACHE_TTL - 1
        self.svc.get_status()

        assert mock_post.call_count == 2

    def test_no_token_returns_error(self):
        svc = TibberService(token="")
        result = svc.get_status()
        assert "error" in result

    @patch("services.tibber.requests.post")
    def test_bearer_token_in_header(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        self.svc.get_status()

        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer fake-token"

    @patch("services.tibber.requests.post")
    def test_empty_homes_returns_empty_dict(self, mock_post):
        mock_post.return_value = _make_response(
            {"data": {"viewer": {"homes": []}}}
        )

        result = self.svc.get_status()

        assert result == {}

    @patch("services.tibber.requests.post")
    def test_empty_homes_result_is_cached(self, mock_post):
        """Empty homes result must be cached so the API is not hit every call."""
        mock_post.return_value = _make_response(
            {"data": {"viewer": {"homes": []}}}
        )

        self.svc.get_status()
        self.svc.get_status()

        assert mock_post.call_count == 1
