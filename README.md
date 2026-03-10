# heimviti
Home status dashboard including car, power, bus and weather.

## Overview

**Heimviti** is a Python/Flask web application deployed on **Google App Engine**
and protected by **Google Cloud IAP** (Identity-Aware Proxy).

It aggregates data from four sources into a single auto-refreshing dashboard:

| Widget | Source | API |
|--------|--------|-----|
| 🌤 Weather | yr.no / met.no | [Locationforecast 2.0](https://api.met.no/) |
| 🚌 Bus departures | AtB / EnTur | [Journey Planner v3 GraphQL](https://api.entur.io/) |
| ⚡ Energy prices & usage | Tibber | [Tibber GraphQL API](https://developer.tibber.com/) |
| 🚗 Car status | Audi Connect | myAudi Connect REST API |

## Project structure

```
heimviti/
├── main.py              # Flask app + JSON API routes
├── app.yaml             # Google App Engine config
├── requirements.txt
├── services/
│   ├── yr.py            # yr.no / api.met.no weather service
│   ├── atb.py           # AtB bus departures via EnTur
│   ├── tibber.py        # Tibber energy prices & consumption
│   └── audi.py          # Audi Connect car status
├── templates/
│   └── index.html       # Dashboard UI (auto-refreshes every 60 s)
├── static/
│   └── style.css
└── tests/
    ├── test_yr.py
    ├── test_atb.py
    ├── test_tibber.py
    ├── test_audi.py
    └── test_main.py
```

## Configuration

Set the following environment variables (in `app.yaml` or via Google Cloud
Secret Manager / environment):

| Variable | Description |
|----------|-------------|
| `TIBBER_TOKEN` | Personal access token from [developer.tibber.com](https://developer.tibber.com/settings/access-token) |
| `AUDI_USERNAME` | myAudi account e-mail |
| `AUDI_PASSWORD` | myAudi account password |
| `HOME_STOP_ID` | NSR stop-place ID for your nearest bus stop (e.g. `NSR:StopPlace:41613`) |
| `YR_LAT` | Latitude of your location (default: 63.4305 – Trondheim) |
| `YR_LON` | Longitude of your location (default: 10.3951 – Trondheim) |

## Running locally

```bash
pip install -r requirements.txt
TIBBER_TOKEN=xxx AUDI_USERNAME=me@example.com AUDI_PASSWORD=secret \
  HOME_STOP_ID=NSR:StopPlace:41613 python main.py
```

Browse to http://localhost:8080.

## Deploying to Google App Engine

```bash
# Enable IAP in Google Cloud Console first, then:
gcloud app deploy
```

Access control is handled by Google Cloud IAP – only users explicitly granted
access via the Cloud Console can reach the application.

## Running tests

```bash
pip install pytest
pytest tests/ -v
```
