"""Tests for the Audi Connect car service."""

import time
from unittest.mock import MagicMock, call, patch

from services.audi import AudiService, _CACHE_TTL

TOKEN_RESPONSE = {
    "access_token": "test-access-token",
    "expires_in": 3600,
}

VEHICLES_RESPONSE = {
    "userVehicles": {
        "vehicle": ["WAUZZZF49RA012345"]
    }
}

STATUS_RESPONSE = {
    "StoredVehicleDataResponse": {
        "vehicleData": {
            "data": [
                {
                    "field": [
                        {"id": "0x0301030005", "value": "54321", "unit": "km"},
                        {"id": "0x0301030002", "value": "75", "unit": "%"},
                    ]
                }
            ]
        }
    }
}


def _make_response(data: dict, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    mock.status_code = status_code
    return mock


class TestAudiService:
    def setup_method(self):
        self.svc = AudiService(username="user@example.com", password="secret")

    @patch("services.audi.requests.get")
    @patch("services.audi.requests.post")
    def test_get_status_returns_vin(self, mock_post, mock_get):
        mock_post.return_value = _make_response(TOKEN_RESPONSE)
        mock_get.side_effect = [
            _make_response(VEHICLES_RESPONSE),
            _make_response(STATUS_RESPONSE),
        ]

        result = self.svc.get_status()

        assert result["vin"] == "WAUZZZF49RA012345"

    @patch("services.audi.requests.get")
    @patch("services.audi.requests.post")
    def test_get_status_returns_fields(self, mock_post, mock_get):
        mock_post.return_value = _make_response(TOKEN_RESPONSE)
        mock_get.side_effect = [
            _make_response(VEHICLES_RESPONSE),
            _make_response(STATUS_RESPONSE),
        ]

        result = self.svc.get_status()

        assert result["0x0301030005"] == "54321 km"
        assert result["0x0301030002"] == "75 %"

    @patch("services.audi.requests.get")
    @patch("services.audi.requests.post")
    def test_result_is_cached(self, mock_post, mock_get):
        mock_post.return_value = _make_response(TOKEN_RESPONSE)
        mock_get.side_effect = [
            _make_response(VEHICLES_RESPONSE),
            _make_response(STATUS_RESPONSE),
        ]

        self.svc.get_status()
        self.svc.get_status()  # should use cache

        assert mock_get.call_count == 2  # only called for first fetch

    @patch("services.audi.requests.get")
    @patch("services.audi.requests.post")
    def test_cache_expires(self, mock_post, mock_get):
        mock_post.return_value = _make_response(TOKEN_RESPONSE)
        mock_get.side_effect = [
            _make_response(VEHICLES_RESPONSE),
            _make_response(STATUS_RESPONSE),
            _make_response(VEHICLES_RESPONSE),
            _make_response(STATUS_RESPONSE),
        ]

        self.svc.get_status()
        self.svc._cache_ts = time.monotonic() - _CACHE_TTL - 1
        self.svc.get_status()

        assert mock_get.call_count == 4

    def test_no_credentials_returns_error(self):
        svc = AudiService(username="", password="")
        result = svc.get_status()
        assert "error" in result

    @patch("services.audi.requests.get")
    @patch("services.audi.requests.post")
    def test_no_vehicles_returns_error(self, mock_post, mock_get):
        mock_post.return_value = _make_response(TOKEN_RESPONSE)
        mock_get.return_value = _make_response(
            {"userVehicles": {"vehicle": []}}
        )

        result = self.svc.get_status()

        assert "error" in result
