"""Tests for the AtB / EnTur bus departure service."""

import time
from unittest.mock import MagicMock, patch

from services.atb import AtbService, _CACHE_TTL

SAMPLE_RESPONSE = {
    "data": {
        "stopPlace": {
            "id": "NSR:StopPlace:41613",
            "name": "Prinsens gate",
            "estimatedCalls": [
                {
                    "realtime": True,
                    "aimedDepartureTime": "2024-01-01T12:00:00+01:00",
                    "expectedDepartureTime": "2024-01-01T12:02:00+01:00",
                    "cancellation": False,
                    "destinationDisplay": {"frontText": "Lerkendal"},
                    "serviceJourney": {
                        "journeyPattern": {
                            "line": {"publicCode": "9", "transportMode": "bus"}
                        }
                    },
                },
                {
                    "realtime": False,
                    "aimedDepartureTime": "2024-01-01T12:05:00+01:00",
                    "expectedDepartureTime": "2024-01-01T12:05:00+01:00",
                    "cancellation": True,
                    "destinationDisplay": {"frontText": "Heimdal"},
                    "serviceJourney": {
                        "journeyPattern": {
                            "line": {"publicCode": "60", "transportMode": "bus"}
                        }
                    },
                },
            ],
        }
    }
}


def _make_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


class TestAtbService:
    def setup_method(self):
        self.svc = AtbService(stop_id="NSR:StopPlace:41613", number_of_departures=5)

    @patch("services.atb.requests.post")
    def test_get_departures_returns_list(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        result = self.svc.get_departures()

        assert isinstance(result, list)
        assert len(result) == 2

    @patch("services.atb.requests.post")
    def test_departure_fields_present(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        result = self.svc.get_departures()
        first = result[0]

        assert first["line"] == "9"
        assert first["destination"] == "Lerkendal"
        assert first["realtime"] is True
        assert first["cancelled"] is False

    @patch("services.atb.requests.post")
    def test_cancelled_departure_flagged(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        result = self.svc.get_departures()

        assert result[1]["cancelled"] is True

    @patch("services.atb.requests.post")
    def test_result_is_cached(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        self.svc.get_departures()
        self.svc.get_departures()

        assert mock_post.call_count == 1

    @patch("services.atb.requests.post")
    def test_cache_expires(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        self.svc.get_departures()
        self.svc._cache_ts = time.monotonic() - _CACHE_TTL - 1
        self.svc.get_departures()

        assert mock_post.call_count == 2

    @patch("services.atb.requests.post")
    def test_empty_stop_place_returns_empty_list(self, mock_post):
        mock_post.return_value = _make_response({"data": {"stopPlace": None}})

        result = self.svc.get_departures()

        assert result == []

    @patch("services.atb.requests.post")
    def test_et_client_name_header_sent(self, mock_post):
        mock_post.return_value = _make_response(SAMPLE_RESPONSE)

        self.svc.get_departures()

        _, kwargs = mock_post.call_args
        assert "ET-Client-Name" in kwargs["headers"]
