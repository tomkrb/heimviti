"""Integration tests for Flask application routes."""

import json
from unittest.mock import MagicMock, patch

import pytest

import main


@pytest.fixture()
def client():
    main.app.config["TESTING"] = True
    with main.app.test_client() as c:
        yield c


class TestHealthz:
    def test_healthz_returns_ok(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.data == b"OK"


class TestApiWeather:
    @patch.object(main._yr, "get_current", return_value={"air_temperature": 5.0})
    def test_weather_success(self, mock_weather, client):
        resp = client.get("/api/weather")
        data = json.loads(resp.data)
        assert resp.status_code == 200
        assert data["ok"] is True
        assert data["data"]["air_temperature"] == 5.0

    @patch.object(main._yr, "get_current", side_effect=Exception("timeout"))
    def test_weather_error(self, mock_weather, client):
        resp = client.get("/api/weather")
        data = json.loads(resp.data)
        assert resp.status_code == 502
        assert data["ok"] is False


class TestApiBus:
    @patch.object(
        main._atb,
        "get_departures",
        return_value=[{"line": "9", "destination": "Lerkendal"}],
    )
    def test_bus_success(self, mock_bus, client):
        resp = client.get("/api/bus")
        data = json.loads(resp.data)
        assert resp.status_code == 200
        assert data["ok"] is True
        assert data["data"][0]["line"] == "9"

    @patch.object(main._atb, "get_departures", side_effect=Exception("network"))
    def test_bus_error(self, mock_bus, client):
        resp = client.get("/api/bus")
        data = json.loads(resp.data)
        assert resp.status_code == 502
        assert data["ok"] is False


class TestApiEnergy:
    @patch.object(
        main._tibber,
        "get_status",
        return_value={"current_price": {"total": 1.23, "currency": "NOK"}},
    )
    def test_energy_success(self, mock_tibber, client):
        resp = client.get("/api/energy")
        data = json.loads(resp.data)
        assert resp.status_code == 200
        assert data["ok"] is True

    @patch.object(main._tibber, "get_status", side_effect=Exception("auth"))
    def test_energy_error(self, mock_tibber, client):
        resp = client.get("/api/energy")
        data = json.loads(resp.data)
        assert resp.status_code == 502
        assert data["ok"] is False


class TestApiCar:
    @patch.object(
        main._audi,
        "get_status",
        return_value={"vin": "WAUZZZF49RA012345"},
    )
    def test_car_success(self, mock_audi, client):
        resp = client.get("/api/car")
        data = json.loads(resp.data)
        assert resp.status_code == 200
        assert data["ok"] is True
        assert data["data"]["vin"] == "WAUZZZF49RA012345"

    @patch.object(main._audi, "get_status", side_effect=Exception("conn"))
    def test_car_error(self, mock_audi, client):
        resp = client.get("/api/car")
        data = json.loads(resp.data)
        assert resp.status_code == 502
        assert data["ok"] is False


class TestApiCalendar:
    @patch.object(
        main._calendar,
        "get_events",
        return_value=[{"summary": "Team meeting", "start": "2024-06-01T10:00:00+00:00"}],
    )
    def test_calendar_success(self, mock_cal, client):
        resp = client.get("/api/calendar")
        data = json.loads(resp.data)
        assert resp.status_code == 200
        assert data["ok"] is True
        assert data["data"][0]["summary"] == "Team meeting"

    @patch.object(main._calendar, "get_events", side_effect=Exception("api error"))
    def test_calendar_error(self, mock_cal, client):
        resp = client.get("/api/calendar")
        data = json.loads(resp.data)
        assert resp.status_code == 502
        assert data["ok"] is False


class TestIndex:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Heimviti" in resp.data
