"""Tests for the Tibber energy service."""

import time
from unittest.mock import MagicMock, patch

from services.tibber import TibberService, _CACHE_TTL, _label_for_address

SAMPLE_RESPONSE = {
    "data": {
        "viewer": {
            "homes": [
                {
                    "address": {"address1": "Trollahaugen 24"},
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
                },
                {
                    "address": {"address1": "Trollahaugen 28"},
                    "currentSubscription": {
                        "priceInfo": {
                            "current": {
                                "total": 1.3456,
                                "energy": 1.0,
                                "tax": 0.3456,
                                "startsAt": "2024-01-01T12:00:00+01:00",
                                "currency": "NOK",
                                "level": "CHEAP",
                            },
                            "today": [
                                {
                                    "total": 1.2,
                                    "energy": 0.9,
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
                                "cost": 3.0,
                                "unitPrice": 1.3,
                                "unitPriceVAT": 0.3,
                                "consumption": 3.5,
                                "consumptionUnit": "kWh",
                                "currency": "NOK",
                            }
                        ]
                    },
                },
            ]
        }
    }
}


def _make_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


class TestLabelForAddress:
    def test_trollahaugen_24_returns_garasje(self):
        assert _label_for_address("Trollahaugen 24") == "Garasje"

    def test_trollahaugen_28_returns_heim(self):
        assert _label_for_address("Trollahaugen 28") == "Heim"

    def test_unknown_address_returns_address_itself(self):
        assert _label_for_address("Some Other Street 5") == "Some Other Street 5"


class TestTibberService:
    def setup_method(self):
        self.svc = TibberService(token="fake-token")

    @patch("services.tibber.requests.post")
    def test_get_status_returns_both_homes(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        result = self.svc.get_status()

        assert isinstance(result, list)
        assert len(result) == 2

    @patch("services.tibber.requests.post")
    def test_get_status_labels_homes(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        result = self.svc.get_status()

        assert result[0]["label"] == "Garasje"
        assert result[1]["label"] == "Heim"

    @patch("services.tibber.requests.post")
    def test_get_status_returns_current_price(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        result = self.svc.get_status()

        assert result[0]["current_price"]["total"] == 1.2345
        assert result[0]["current_price"]["currency"] == "NOK"

    @patch("services.tibber.requests.post")
    def test_get_status_returns_consumption(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        result = self.svc.get_status()

        assert len(result[0]["consumption_24h"]) == 1
        assert result[0]["consumption_24h"][0]["consumption"] == 2.08

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
    def test_empty_homes_returns_empty_list(self, mock_post):
        mock_post.return_value = _make_response(
            {"data": {"viewer": {"homes": []}}}
        )

        result = self.svc.get_status()

        assert result == []

    @patch("services.tibber.requests.post")
    def test_empty_homes_result_is_cached(self, mock_post):
        """Empty homes result must be cached so the API is not hit every call."""
        mock_post.return_value = _make_response(
            {"data": {"viewer": {"homes": []}}}
        )

        self.svc.get_status()
        self.svc.get_status()

        assert mock_post.call_count == 1
