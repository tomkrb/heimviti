"""Audi Connect service – fetches car status via the myAudi Connect API.

The Audi Connect (myAudi) API is an undocumented REST API used by the
official mobile app.  This service uses the public OAuth2 flow that the
app itself uses.

Environment variables required:
  AUDI_USERNAME  – myAudi account e-mail
  AUDI_PASSWORD  – myAudi account password
"""

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Audi Connect API endpoints (market: "de" for generic European access)
# ---------------------------------------------------------------------------
_TOKEN_URL = "https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token"
_VEHICLE_URL = "https://msg.audi.de/fs-car/usermanagement/users/v1/Audi/DE/vehicles"
_STATUS_URL = "https://msg.audi.de/fs-car/bs/vsr/v1/Audi/DE/vehicles/{vin}/status"

_CACHE_TTL = 120  # seconds


class AudiService:
    """Fetches vehicle status from the myAudi Connect back-end."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._access_token: str = ""
        self._token_expiry: float = 0.0
        self._cache: dict[str, Any] = {}
        self._cache_ts: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return status dict for the first vehicle linked to the account."""
        if not self._username or not self._password:
            return {"error": "AUDI_USERNAME / AUDI_PASSWORD not configured"}

        now = time.monotonic()
        if self._cache and (now - self._cache_ts) < _CACHE_TTL:
            return self._cache

        try:
            token = self._get_token()
            vin = self._get_first_vin(token)
            if not vin:
                return {"error": "No vehicle found in account"}

            status = self._fetch_vehicle_status(token, vin)
            self._cache = status
            self._cache_ts = now
            return status
        except requests.HTTPError as exc:
            logger.warning("Audi API error: %s", exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        if self._access_token and time.monotonic() < self._token_expiry:
            return self._access_token

        payload = {
            "grant_type": "password",
            "username": self._username,
            "password": self._password,
            "client_id": "09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com",
            "scope": "openid profile address cars email birthdate phone",
        }
        resp = requests.post(_TOKEN_URL, data=payload, timeout=15)
        resp.raise_for_status()
        token_data = resp.json()
        self._access_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 3600))
        self._token_expiry = time.monotonic() + expires_in - 60
        return self._access_token

    def _get_first_vin(self, token: str) -> str:
        """Return the VIN of the first vehicle registered to the account."""
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(_VEHICLE_URL, headers=headers, timeout=10)
        resp.raise_for_status()
        vehicles = resp.json().get("userVehicles", {}).get("vehicle", [])
        return vehicles[0] if vehicles else ""

    def _fetch_vehicle_status(self, token: str, vin: str) -> dict[str, Any]:
        """Fetch and parse the vehicle status for *vin*."""
        headers = {"Authorization": f"Bearer {token}"}
        url = _STATUS_URL.format(vin=vin)
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        raw = resp.json()

        stored_fields = (
            raw.get("StoredVehicleDataResponse", {})
            .get("vehicleData", {})
            .get("data", [])
        )

        # Flatten all id→value pairs for easy consumption
        fields: dict[str, Any] = {"vin": vin}
        for group in stored_fields:
            for field in group.get("field", []):
                fid = field.get("id")
                value = field.get("value")
                unit = field.get("unit", "")
                if fid:
                    fields[fid] = f"{value} {unit}".strip() if unit else value

        return fields
