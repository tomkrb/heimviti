"""Heimviti – home-status web server.

Collects data from:
- yr.no / api.met.no  (weather)
- AtB / EnTur         (bus departures)
- Tibber              (electricity prices & consumption)
- Audi Connect        (car status)

Deployed on Google App Engine; protected by Google Cloud IAP.
"""

import logging
import os

from flask import Flask, jsonify, render_template

import secret_loader
from services.atb import AtbService
from services.audi import AudiService
from services.tibber import TibberService
from services.yr import YrService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Service singletons – constructed at startup (secrets loaded once here)
# ---------------------------------------------------------------------------

_yr = YrService(
    lat=float(secret_loader.get_secret("YR_LAT", "63.4305")),
    lon=float(secret_loader.get_secret("YR_LON", "10.3951")),
)

_atb = AtbService(
    stop_id=secret_loader.get_secret("HOME_STOP_ID", "NSR:StopPlace:43975"),
)

_tibber = TibberService(
    token=secret_loader.get_secret("TIBBER_TOKEN", ""),
)

_audi = AudiService(
    username=secret_loader.get_secret("AUDI_USERNAME", ""),
    password=secret_loader.get_secret("AUDI_PASSWORD", ""),
    home_lat=float(secret_loader.get_secret("HOME_LAT", "63.4305")),
    home_lon=float(secret_loader.get_secret("HOME_LON", "10.3951")),
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Main dashboard – renders all widgets."""
    return render_template("index.html")


@app.route("/api/weather")
def api_weather():
    """JSON endpoint – current weather from yr.no."""
    try:
        data = _yr.get_current()
        return jsonify({"ok": True, "data": data})
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Weather fetch failed")
        return jsonify({"ok": False, "error": str(exc)}), 502


@app.route("/api/bus")
def api_bus():
    """JSON endpoint – next bus departures from AtB / EnTur."""
    try:
        data = _atb.get_departures()
        return jsonify({"ok": True, "data": data})
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Bus fetch failed")
        return jsonify({"ok": False, "error": str(exc)}), 502


@app.route("/api/energy")
def api_energy():
    """JSON endpoint – current Tibber prices & today's consumption."""
    try:
        data = _tibber.get_status()
        return jsonify({"ok": True, "data": data})
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Tibber fetch failed")
        return jsonify({"ok": False, "error": str(exc)}), 502


@app.route("/api/car")
def api_car():
    """JSON endpoint – Audi Connect car status."""
    try:
        data = _audi.get_status()
        return jsonify({"ok": True, "data": data})
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Audi fetch failed")
        return jsonify({"ok": False, "error": str(exc)}), 502


@app.route("/healthz")
def healthz():
    """Health check used by App Engine / load balancer."""
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
