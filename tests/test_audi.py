"""Tests for the Audi Connect car service."""

import time
from unittest.mock import MagicMock, call, patch

from services.audi import AudiService, _CACHE_TTL, _haversine_km, _HOME_LAT, _HOME_LON

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

STATUS_RESPONSE_AT_HOME = {
    "StoredVehicleDataResponse": {
        "vehicleData": {
            "data": [
                {
                    "field": [
                        {"id": "0x0301030005", "value": "54321", "unit": "km"},
                        # GPS position at home (within 500 m)
                        {"id": "0x0301061001", "value": str(_HOME_LAT), "unit": ""},
                        {"id": "0x0301061002", "value": str(_HOME_LON), "unit": ""},
                    ]
                }
            ]
        }
    }
}

STATUS_RESPONSE_AWAY = {
    "StoredVehicleDataResponse": {
        "vehicleData": {
            "data": [
                {
                    "field": [
                        {"id": "0x0301030005", "value": "54321", "unit": "km"},
                        # GPS position far away (Oslo)
                        {"id": "0x0301061001", "value": "59.9139", "unit": ""},
                        {"id": "0x0301061002", "value": "10.7522", "unit": ""},
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


class TestHaversine:
    def test_same_point_is_zero(self):
        assert _haversine_km(63.4305, 10.3951, 63.4305, 10.3951) == 0.0

    def test_known_distance(self):
        # Straight-line distance Trondheim to Oslo is ~391 km
        dist = _haversine_km(63.4305, 10.3951, 59.9139, 10.7522)
        assert 380 < dist < 410

    def test_short_distance(self):
        # ~111 m north
        dist = _haversine_km(63.4305, 10.3951, 63.4315, 10.3951)
        assert dist < 0.2


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

    # ------------------------------------------------------------------
    # Location status tests
    # ------------------------------------------------------------------

    @patch("services.audi.requests.get")
    @patch("services.audi.requests.post")
    def test_location_status_heime_legacy(self, mock_post, mock_get):
        """Car at home coordinates → location_status == 'Heime'."""
        mock_post.return_value = _make_response(TOKEN_RESPONSE)
        mock_get.side_effect = [
            _make_response(VEHICLES_RESPONSE),
            _make_response(STATUS_RESPONSE_AT_HOME),
        ]

        result = self.svc.get_status()

        assert result["location_status"] == "Heime"

    @patch("services.audi.requests.get")
    @patch("services.audi.requests.post")
    def test_location_status_borte_legacy(self, mock_post, mock_get):
        """Car in Oslo → location_status == 'Borte'."""
        mock_post.return_value = _make_response(TOKEN_RESPONSE)
        mock_get.side_effect = [
            _make_response(VEHICLES_RESPONSE),
            _make_response(STATUS_RESPONSE_AWAY),
        ]

        result = self.svc.get_status()

        assert result["location_status"] == "Borte"

    @patch("services.audi.requests.get")
    @patch("services.audi.requests.post")
    def test_location_status_none_when_no_gps(self, mock_post, mock_get):
        """No GPS fields → location_status is None."""
        mock_post.return_value = _make_response(TOKEN_RESPONSE)
        mock_get.side_effect = [
            _make_response(VEHICLES_RESPONSE),
            _make_response(STATUS_RESPONSE),
        ]

        result = self.svc.get_status()

        assert result["location_status"] is None

    def test_location_status_cariad_heime(self):
        """Cariad BFF format with car at home → location_status == 'Heime'."""
        raw = {
            "parking": {
                "parkingPosition": {
                    "value": {
                        "carCoordinate": {
                            "latitude": _HOME_LAT,
                            "longitude": _HOME_LON,
                        }
                    }
                }
            }
        }
        fields = self.svc._flatten_vehicle_data("TESTVIN", raw)
        assert fields["location_status"] == "Heime"

    def test_location_status_cariad_borte(self):
        """Cariad BFF format with car far away → location_status == 'Borte'."""
        raw = {
            "parking": {
                "parkingPosition": {
                    "value": {
                        "carCoordinate": {
                            "latitude": 59.9139,  # Oslo
                            "longitude": 10.7522,
                        }
                    }
                }
            }
        }
        fields = self.svc._flatten_vehicle_data("TESTVIN", raw)
        assert fields["location_status"] == "Borte"

    def test_location_status_none_cariad_no_parking(self):
        """Cariad BFF format without parking data → location_status is None."""
        raw = {
            "access": {
                "accessStatus": {"value": {"overallStatus": "safe"}}
            }
        }
        fields = self.svc._flatten_vehicle_data("TESTVIN", raw)
        assert fields["location_status"] is None
