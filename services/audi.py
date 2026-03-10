"""Audi Connect service – fetches car status via the myAudi Connect API.

The Audi Connect (myAudi) API is an undocumented REST API used by the
official mobile app.  This service uses the public OAuth2 flow that the
app itself uses.

Environment variables required:
  AUDI_USERNAME  – myAudi account e-mail
  AUDI_PASSWORD  – myAudi account password
"""

import base64
import hmac
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Cache TTL for status responses
_CACHE_TTL = 120  # seconds

# ---------------------------------------------------------------------------
# Audi Connect API endpoints (market: "de" for generic European access)
# ---------------------------------------------------------------------------
_TOKEN_URL = "https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token"
_VEHICLE_URL = "https://msg.volkswagen.de/fs-car/usermanagement/users/v1/Audi/DE/vehicles"
_STATUS_URL = "https://msg.volkswagen.de/fs-car/bs/vsr/v1/Audi/DE/vehicles/{vin}/status"

_HDR_XAPP_VERSION = "4.31.0"
_HDR_USER_AGENT = "Android/4.31.0 (Build 800341641.root project 'myaudi_android'.ext.buildTime) Android/13"
_DEFAULT_CLIENT_ID = "09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com"


class AudiService:
    """Fetches vehicle status using direct requests to the myAudi API.

    This implementation prefers an `AUDI_ACCESS_TOKEN` from the
    environment (or `.env`) and falls back to the password grant flow.
    """

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._token_expiry: float = 0.0
        self._country = os.environ.get("AUDI_COUNTRY", "DE")
        self._language = None
        self._token_bundle: dict[str, Any] = {}
        self._cache: dict[str, Any] = {}
        self._cache_ts: float = 0.0

    def get_status(self) -> dict[str, Any]:
        """Return status dict for the first vehicle linked to the account."""
        if not self._username or not self._password:
            return {"error": "AUDI_USERNAME / AUDI_PASSWORD not configured"}

        now = time.monotonic()
        if self._cache and (now - self._cache_ts) < _CACHE_TTL:
            return self._cache

        # First attempt: direct token + requests flow (compatible with tests)
        try:
            token = self._get_token()
            vin = self._get_first_vin(token)
            if not vin:
                return {"error": "No vehicle found in account"}

            status = self._fetch_vehicle_status(token, vin)
            self._cache = status
            self._cache_ts = now
            return status
        except Exception as exc:
            logger.warning("Audi API error: %s", exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Direct requests-based implementation (keeps unit tests stable)
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        # Allow using a pre-obtained access token via env
        env_token = os.environ.get("AUDI_ACCESS_TOKEN")
        if env_token:
            return env_token

        if self._access_token and time.monotonic() < self._token_expiry:
            return self._access_token
        payload = {
            "grant_type": "password",
            "username": self._username,
            "password": self._password,
            "client_id": _DEFAULT_CLIENT_ID,
            "scope": "openid profile address cars email birthdate phone",
        }
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'okhttp/2.7.4',
            'X-App-ID': 'de.audi.mmiapp',
            'X-App-Name': 'MMIconnect',
            'X-App-Version': '2.8.3',
            'X-Brand': 'audi',
            'X-Country-Id': 'DE',
            'X-Language-Id': 'de',
            'X-Platform': 'google',
        }
        try:
            resp = requests.post(_TOKEN_URL, data=payload, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.warning(
                    "Audi token endpoint returned %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                resp.raise_for_status()
            token_data = resp.json()
            token = token_data.get("access_token")
            if not token:
                raise requests.HTTPError("No access_token in token response")
            expires_in = int(token_data.get("expires_in", 3600))
            self._access_token = token
            self._token_expiry = time.monotonic() + max(0, expires_in - 60)
            return token
        except Exception:
            # If password grant fails, try the PKCE/IDK flow
            token, expires_in = self._login_pkce()
            self._access_token = token
            self._token_expiry = time.monotonic() + max(0, expires_in - 60)
            return token
        if resp.status_code != 200:
            logger.warning(
                "Audi token endpoint returned %s: %s",
                resp.status_code,
                resp.text[:200],
            )
            resp.raise_for_status()
        token_data = resp.json()
        token = token_data.get("access_token")
        if not token:
            raise requests.HTTPError("No access_token in token response")
        return token

    def _get_first_vin(self, token: str) -> str:
        """Return the VIN of the first vehicle registered to the account."""
        headers = self._auth_headers(token)
        resp = None
        try:
            resp = requests.get(_VEHICLE_URL, headers=headers, timeout=10)
            resp.raise_for_status()
            vehicles = resp.json().get("userVehicles", {}).get("vehicle", [])
            return vehicles[0] if vehicles else ""
        except requests.HTTPError as exc:
            if resp is not None and resp.status_code in (401, 403) and self._token_bundle.get("audi"):
                return self._get_first_vin_graphql()
            raise exc

    def _fetch_vehicle_status(self, token: str, vin: str) -> dict[str, Any]:
        """Fetch and parse the vehicle status for *vin*."""
        headers = self._auth_headers(token)
        url = _STATUS_URL.format(vin=vin)
        resp = None
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            raw = resp.json()
            return self._flatten_vehicle_data(vin, raw)
        except requests.HTTPError as exc:
            if resp is not None and resp.status_code in (401, 403) and self._token_bundle.get("bearer"):
                return self._fetch_vehicle_status_cariad(vin)
            raise exc

    def _auth_headers(self, token: str) -> dict[str, str]:
        headers = self._base_headers()
        headers.update({"Authorization": f"Bearer {token}"})
        return headers

    # ------------------------------------------------------------------
    # PKCE/IDK-based authentication flow (from audi_connect_ha patterns)
    # ------------------------------------------------------------------

    def _login_pkce(self) -> tuple[str, int]:
        session = requests.Session()

        markets = session.get(
            "https://content.app.my.audi.com/service/mobileapp/configurations/markets",
            headers=self._base_headers(),
            timeout=20,
        ).json()
        country_specs = markets.get("countries", {}).get("countrySpecifications", {})
        if self._country.upper() not in country_specs:
            raise requests.HTTPError("Country not found in market config")
        language = country_specs[self._country.upper()].get("defaultLanguage", "de")
        self._language = language

        marketcfg_url = (
            "https://content.app.my.audi.com/service/mobileapp/configurations/market/"
            f"{self._country}/{language}?v=4.23.1"
        )
        marketcfg = session.get(marketcfg_url, headers=self._base_headers(), timeout=20).json()

        client_id = marketcfg.get("idkClientIDAndroidLive", _DEFAULT_CLIENT_ID)
        authorization_server_base = marketcfg.get(
            "myAudiAuthorizationServerProxyServiceURLProduction",
            self._get_cariad_url("/login/v1/audi"),
        )
        mbboauth_base = marketcfg.get(
            "mbbOAuthBaseURLLive",
            "https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth",
        )

        openidcfg_url = self._get_cariad_url("/login/v1/idk/openid-configuration")
        openidcfg = session.get(openidcfg_url, headers=self._base_headers(), timeout=20).json()
        authorization_endpoint = openidcfg.get(
            "authorization_endpoint", "https://identity.vwgroup.io/oidc/v1/authorize"
        )
        token_endpoint = openidcfg.get("token_endpoint", self._get_cariad_url("/login/v1/idk/token"))

        code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8").strip("=")
        code_challenge = base64.urlsafe_b64encode(
            sha256(code_verifier.encode("ascii", "ignore")).digest()
        ).decode("utf-8").strip("=")

        state = str(uuid.uuid4())
        nonce = str(uuid.uuid4())
        idk_params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "myaudi:///",
            "scope": "address profile badge birthdate birthplace nationalIdentifier nationality profession email vin phone nickname name picture mbb gallery openid",
            "state": state,
            "nonce": nonce,
            "prompt": "login",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "ui_locales": "de-de de",
        }

        idk_rsp = session.get(
            authorization_endpoint,
            headers=self._base_headers(),
            params=idk_params,
            allow_redirects=True,
            timeout=30,
        )
        submit_data = self._extract_hidden_inputs(idk_rsp.text, {"email": self._username})
        submit_url = self._get_form_action(idk_rsp.text, idk_rsp.url)

        email_rsp = session.post(
            submit_url,
            data=submit_data,
            headers=self._base_headers(),
            allow_redirects=True,
            timeout=30,
        )

        regex_res = re.findall('"hmac"\\s*:\\s*"[0-9a-fA-F]+"', email_rsp.text)
        if regex_res:
            submit_url = submit_url.replace("identifier", "authenticate")
            submit_data["hmac"] = regex_res[0].split(":")[1].strip('"')
            submit_data["password"] = self._password
        else:
            submit_data = self._extract_hidden_inputs(email_rsp.text, {"password": self._password})
            submit_url = self._get_form_action(email_rsp.text, submit_url)

        pw_rsp = session.post(
            submit_url,
            data=submit_data,
            headers=self._base_headers(),
            allow_redirects=False,
            timeout=30,
        )
        if "Location" not in pw_rsp.headers:
            raise requests.HTTPError("Login flow failed: missing redirect")

        fwd1 = session.get(pw_rsp.headers["Location"], headers=self._base_headers(), allow_redirects=False, timeout=30)
        fwd2 = session.get(fwd1.headers["Location"], headers=self._base_headers(), allow_redirects=False, timeout=30)
        codeauth = session.get(fwd2.headers["Location"], headers=self._base_headers(), allow_redirects=False, timeout=30)

        location = codeauth.headers.get("Location", "")
        if location.startswith("myaudi:///?"):
            location = location[len("myaudi:///?") :]
        parsed = urlparse(location)
        query = parsed.query or parsed.path
        params = parse_qs(query)
        code = params.get("code", [None])[0]
        if not code:
            raise requests.HTTPError("Authorization code not found")

        token_headers = {
            "Accept": "application/json",
            "Accept-Charset": "utf-8",
            "X-QMAuth": self._calculate_xqmauth(),
            "User-Agent": _HDR_USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        tokenreq_data = {
            "client_id": client_id,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "myaudi:///",
            "response_type": "token id_token",
            "code_verifier": code_verifier,
        }
        bearer_token_rsp = session.post(
            token_endpoint,
            data=tokenreq_data,
            headers=token_headers,
            allow_redirects=False,
            timeout=30,
        )
        bearer_token_json = bearer_token_rsp.json()

        azs_headers = {
            "Accept": "application/json",
            "Accept-Charset": "utf-8",
            "X-App-Version": _HDR_XAPP_VERSION,
            "X-App-Name": "myAudi",
            "User-Agent": _HDR_USER_AGENT,
            "Content-Type": "application/json; charset=utf-8",
        }
        azs_data = {
            "token": bearer_token_json["access_token"],
            "grant_type": "id_token",
            "stage": "live",
            "config": "myaudi",
        }
        azs_rsp = session.post(
            authorization_server_base + "/token",
            data=json.dumps(azs_data),
            headers=azs_headers,
            allow_redirects=False,
            timeout=30,
        )
        azs_token_json = {}
        try:
            azs_token_json = azs_rsp.json()
        except Exception:
            azs_token_json = {}

        reg_headers = {
            "Accept": "application/json",
            "Accept-Charset": "utf-8",
            "User-Agent": _HDR_USER_AGENT,
            "Content-Type": "application/json; charset=utf-8",
        }
        reg_data = {
            "client_name": "SM-A405FN",
            "platform": "google",
            "client_brand": "Audi",
            "appName": "myAudi",
            "appVersion": _HDR_XAPP_VERSION,
            "appId": "de.myaudi.mobile.assistant",
        }
        reg_rsp = session.post(
            mbboauth_base + "/mobile/register/v1",
            data=json.dumps(reg_data),
            headers=reg_headers,
            allow_redirects=False,
            timeout=30,
        )
        reg_json = reg_rsp.json()
        xclient_id = reg_json["client_id"]

        mbb_headers = {
            "Accept": "application/json",
            "Accept-Charset": "utf-8",
            "User-Agent": _HDR_USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Client-ID": xclient_id,
        }
        mbb_auth_data = {
            "grant_type": "id_token",
            "token": bearer_token_json["id_token"],
            "scope": "sc2:fal",
        }
        mbb_auth_rsp = session.post(
            mbboauth_base + "/mobile/oauth2/v1/token",
            data=mbb_auth_data,
            headers=mbb_headers,
            allow_redirects=False,
            timeout=30,
        )
        mbb_auth_json = mbb_auth_rsp.json()

        mbb_refresh_data = {
            "grant_type": "refresh_token",
            "token": mbb_auth_json["refresh_token"],
            "scope": "sc2:fal",
        }
        mbb_refresh_rsp = session.post(
            mbboauth_base + "/mobile/oauth2/v1/token",
            data=mbb_refresh_data,
            headers=mbb_headers,
            allow_redirects=False,
            timeout=30,
        )
        vw_token = mbb_refresh_rsp.json()
        access_token = vw_token.get("access_token")
        if not access_token:
            raise requests.HTTPError("No access_token in mbboauth response")
        expires_in = int(vw_token.get("expires_in", 3600))
        self._token_bundle = {
            "vw": vw_token,
            "bearer": bearer_token_json,
            "audi": azs_token_json,
        }
        return access_token, expires_in

    def _get_cariad_url(self, path_and_query: str) -> str:
        region = "emea" if self._country.upper() != "US" else "na"
        base = f"https://{region}.bff.cariad.digital"
        return base.rstrip("/") + "/" + path_and_query.lstrip("/")

    def _base_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Accept-Charset": "utf-8",
            "X-App-Version": _HDR_XAPP_VERSION,
            "X-App-Name": "myAudi",
            "User-Agent": _HDR_USER_AGENT,
        }

    def _extract_hidden_inputs(self, html: str, defaults: dict[str, str]) -> dict[str, str]:
        data = dict(defaults)
        soup = BeautifulSoup(html, "html.parser")
        for form_input in soup.find_all("input", attrs={"type": "hidden"}):
            name = form_input.get("name")
            value = form_input.get("value")
            if name is not None:
                data[name] = value
        return data

    def _get_form_action(self, html: str, base_url: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        form_tag = soup.find("form")
        if not form_tag or not form_tag.get("action"):
            raise requests.HTTPError("No form action found in login flow")
        action = form_tag.get("action")
        if action.startswith("http"):
            return action
        if action.startswith("/"):
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{action}"
        raise requests.HTTPError("Unknown form action in login flow")

    def _calculate_xqmauth(self) -> str:
        gmtime_100sec = int((datetime.utcnow() - datetime(1970, 1, 1)).total_seconds() / 100)
        xqmauth_secret = bytes(
            [
                26, 256 - 74, 256 - 103, 37, 256 - 84, 23, 256 - 102, 256 - 86,
                78, 256 - 125, 256 - 85, 256 - 26, 113, 256 - 87, 71, 109,
                23, 100, 24, 256 - 72, 91, 256 - 41, 6, 256 - 15, 67, 108,
                256 - 95, 91, 256 - 26, 71, 256 - 104, 256 - 100,
            ]
        )
        xqmauth_val = hmac.new(
            xqmauth_secret, str(gmtime_100sec).encode("ascii", "ignore"), digestmod="sha256"
        ).hexdigest()
        return "v1:01da27b0:" + xqmauth_val

    def _get_first_vin_graphql(self) -> str:
        audi_token = self._token_bundle.get("audi", {})
        access = audi_token.get("access_token")
        if not access:
            raise requests.HTTPError("No audi token available for GraphQL")
        language = self._language or "de"
        graphql_url = (
            "https://app-api.my.aoa.audi.com/vgql/v1/graphql"
            if self._country.upper() == "US"
            else "https://app-api.live-my.audi.com/vgql/v1/graphql"
        )
        headers = {
            "Accept": "application/json",
            "Accept-Charset": "utf-8",
            "X-App-Name": "myAudi",
            "X-App-Version": _HDR_XAPP_VERSION,
            "Accept-Language": f"{language}-{self._country.upper()}",
            "X-User-Country": self._country.upper(),
            "User-Agent": _HDR_USER_AGENT,
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json; charset=utf-8",
        }
        query = {
            "query": "query vehicleList {\n userVehicles {\n vin\n mappingVin\n vehicle { core { modelYear\n }\n media { shortName\n longName }\n }\n csid\n commissionNumber\n type\n devicePlatform\n mbbConnect\n userRole {\n role\n }\n vehicle {\n classification {\n driveTrain\n }\n }\n nickname\n }\n}"
        }
        resp = requests.post(graphql_url, headers=headers, data=json.dumps(query), timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            raise requests.HTTPError(f"GraphQL errors: {payload['errors']}")
        vehicles = payload.get("data", {}).get("userVehicles", [])
        if not vehicles:
            return ""
        return vehicles[0].get("vin", "")

    def _fetch_vehicle_status_cariad(self, vin: str) -> dict[str, Any]:
        bearer = self._token_bundle.get("bearer", {})
        access = bearer.get("access_token")
        if not access:
            raise requests.HTTPError("No bearer token available for status")
        jobs = [
            "access",
            "activeVentilation",
            "auxiliaryHeating",
            "batteryChargingCare",
            "batterySupport",
            "charging",
            "chargingProfiles",
            "chargingTimers",
            "climatisation",
            "climatisationTimers",
            "departureProfiles",
            "departureTimers",
            "fuelStatus",
            "honkAndFlash",
            "hybridCarAuxiliaryHeating",
            "lvBattery",
            "measurements",
            "oilLevel",
            "readiness",
            "vehicleHealthInspection",
            "vehicleHealthWarnings",
            "vehicleLights",
        ]
        region = "emea" if self._country.upper() != "US" else "na"
        url = (
            f"https://{region}.bff.cariad.digital/vehicle/v1/vehicles/{vin}/selectivestatus"
            f"?jobs={','.join(jobs)}"
        )
        headers = self._base_headers()
        headers["Authorization"] = f"Bearer {access}"
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        raw = resp.json()
        return self._flatten_vehicle_data(vin, raw)

    def _flatten_vehicle_data(self, vin: str, raw: dict[str, Any]) -> dict[str, Any]:
        stored_fields = (
            raw.get("StoredVehicleDataResponse", {})
            .get("vehicleData", {})
            .get("data", [])
        )
        # Some endpoints return top-level `data`
        if not stored_fields and isinstance(raw.get("data"), list):
            stored_fields = raw.get("data", [])
        fields: dict[str, Any] = {"vin": vin}
        if stored_fields:
            for group in stored_fields:
                for field in group.get("field", []):
                    fid = field.get("id")
                    value = field.get("value")
                    unit = field.get("unit", "")
                    if fid:
                        fields[fid] = f"{value} {unit}".strip() if unit else value
            return fields

        # Cariad BFF format: top-level sections with nested `value` fields
        for section_key, section_val in raw.items():
            if not isinstance(section_val, dict):
                continue
            for key, val in section_val.items():
                if isinstance(val, dict) and "value" in val:
                    fields[f"{section_key}.{key}"] = val.get("value")
        return fields

    # ------------------------------------------------------------------
    # Vendor-based fallback implementation
    # ------------------------------------------------------------------

    def _vendor_get_status(self) -> dict[str, Any]:
        captured: list[dict[str, Any]] = []
        try:
            _ensure_vendor_on_path()
            from audiapi.API import API
            from audiapi.Services import LogonService, CarService, VehicleStatusReportService

            # Instrument requests to capture requests/responses for diagnostics
            orig_post = requests.post
            orig_get = requests.get

            def _capture_post(url, data=None, json=None, **kwargs):
                resp = orig_post(url, data=data, json=json, **kwargs)
                try:
                    body = resp.text
                except Exception:
                    body = '<unreadable body>'
                captured.append({
                    'method': 'POST',
                    'url': url,
                    'status': getattr(resp, 'status_code', None),
                    'response': body[:1000],
                    'request_data': data if data is not None else json,
                    'request_headers': kwargs.get('headers') or getattr(resp, 'request', None) and getattr(resp.request, 'headers', None),
                })
                return resp

            def _capture_get(url, **kwargs):
                resp = orig_get(url, **kwargs)
                try:
                    body = resp.text
                except Exception:
                    body = '<unreadable body>'
                captured.append({
                    'method': 'GET',
                    'url': url,
                    'status': getattr(resp, 'status_code', None),
                    'response': body[:1000],
                    'request_headers': kwargs.get('headers') or getattr(resp, 'request', None) and getattr(resp.request, 'headers', None),
                })
                return resp

            requests.post = _capture_post
            requests.get = _capture_get

            api = API()
            logon = LogonService(api)

            # If a persisted token file from tests exists (token.json),
            # ignore it for live auth attempts to avoid using test tokens.
            token_path = os.path.join(os.getcwd(), 'token.json')
            token_backup = None
            if os.path.exists(token_path):
                try:
                    token_backup = token_path + '.bak'
                    os.replace(token_path, token_backup)
                except Exception:
                    token_backup = None

            try:
                # Force a fresh login rather than using possibly stale/test token
                logon.login(self._username, self._password)
            finally:
                # Restore any backed-up token file
                if token_backup is not None:
                    try:
                        os.replace(token_backup, token_path)
                    except Exception:
                        pass

            car_service = CarService(api)
            vehicles = car_service.get_vehicles()
            vin = None
            vehicle_obj = None
            if hasattr(vehicles, 'vehicles') and vehicles.vehicles:
                vehicle_obj = vehicles.vehicles[0]
                vin = vehicle_obj.vin
            else:
                items = getattr(vehicles, 'vehicle', None) or getattr(vehicles, 'userVehicles', None)
                if items:
                    vehicle_obj = items[0]
                    vin = getattr(vehicle_obj, 'vin', None)

            if not vin or not vehicle_obj:
                return {"error": "No vehicle found in account", 'diag': captured}

            vsr = VehicleStatusReportService(api, vehicle_obj)
            data = vsr.get_stored_vehicle_data()
            if hasattr(data, 'raw'):
                return data.raw
            return data.__dict__
        except Exception as exc:
            logger.warning("Vendor audiapi fallback failed: %s", exc)
            return {"error": str(exc), 'diag': captured}
        finally:
            # Restore original functions
            try:
                requests.post = orig_post
                requests.get = orig_get
            except Exception:
                pass
