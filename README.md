# heimviti
Home status dashboard including car, power, bus and weather.

## Overview

**Heimviti** is a Python/Flask web application deployed on **Google App Engine**
and protected by **Google Cloud IAP** (Identity-Aware Proxy).

It aggregates data from five sources into a single auto-refreshing dashboard:

| Widget | Source | API |
|--------|--------|-----|
| 🌤 Weather | yr.no / met.no | [Locationforecast 2.0](https://api.met.no/) |
| 🚌 Bus departures | AtB / EnTur | [Journey Planner v3 GraphQL](https://api.entur.io/) |
| ⚡ Energy prices & usage | Tibber | [Tibber GraphQL API](https://developer.tibber.com/) |
| 🚗 Car status | Audi Connect | myAudi Connect REST API |
| 📅 Calendar events | Google Calendar | [Calendar API v3](https://developers.google.com/calendar/api) |

## Project structure

```
heimviti/
├── main.py              # Flask app + JSON API routes
├── secret_loader.py     # Secret loader (Secret Manager / .env)
├── app.yaml             # Google App Engine config (no secrets here)
├── requirements.txt
├── .env.example         # Template for local .env (committed – no real values)
├── services/
│   ├── yr.py            # yr.no / api.met.no weather service
│   ├── atb.py           # AtB bus departures via EnTur
│   ├── tibber.py        # Tibber energy prices & consumption
│   ├── audi.py          # Audi Connect car status
│   └── calendar.py      # Google Calendar events
├── templates/
│   └── index.html       # Dashboard UI (auto-refreshes every 60 s)
├── static/
│   └── style.css
└── tests/
    ├── test_secret_loader.py
    ├── test_yr.py
    ├── test_atb.py
    ├── test_tibber.py
    ├── test_audi.py
    ├── test_calendar.py
    └── test_main.py
```

## Configuration

All sensitive values are kept **out of the repository** and loaded at runtime:

| Variable | Description |
|----------|-------------|
| `TIBBER_TOKEN` | Personal access token from [developer.tibber.com](https://developer.tibber.com/settings/access-token) |
| `AUDI_USERNAME` | myAudi account e-mail |
| `AUDI_PASSWORD` | myAudi account password |
| `HOME_STOP_ID` | NSR stop-place ID for your nearest bus stop (e.g. `NSR:StopPlace:43975` for Trollahaugen 10, Trondheim) |
| `YR_LAT` | Latitude of your location (e.g. `63.4305`) |
| `YR_LON` | Longitude of your location (e.g. `10.3951`) |
| `HOME_LAT` | Latitude of your home, used to determine whether the car is home (e.g. `63.4305`) |
| `HOME_LON` | Longitude of your home (e.g. `10.3951`) |
| `GOOGLE_API_KEY` | Google Calendar API key – create at [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials) (enable the Calendar API first) |
| `CALENDAR_IDS` | Comma-separated Google Calendar IDs to display (up to 5); find each ID under *Calendar settings → Integrate calendar* |

### Production – Google Cloud Secret Manager

Each variable above is stored as a **Secret Manager secret** in your GCP
project.  The app fetches them at startup via the Secret Manager API.

1. Enable the Secret Manager API and the Google Calendar API:
   ```bash
   gcloud services enable secretmanager.googleapis.com calendar-json.googleapis.com
   ```

2. Create each secret (repeat for every variable):
   ```bash
   echo -n "your-tibber-token" | \
     gcloud secrets create TIBBER_TOKEN --data-file=-

   echo -n "you@example.com" | \
     gcloud secrets create AUDI_USERNAME --data-file=-

   echo -n "your-audi-password" | \
     gcloud secrets create AUDI_PASSWORD --data-file=-

   echo -n "NSR:StopPlace:43975" | \
     gcloud secrets create HOME_STOP_ID --data-file=-

   echo -n "63.4305" | gcloud secrets create YR_LAT --data-file=-
   echo -n "10.3951" | gcloud secrets create YR_LON --data-file=-
   echo -n "63.4305" | gcloud secrets create HOME_LAT --data-file=-
   echo -n "10.3951" | gcloud secrets create HOME_LON --data-file=-

   echo -n "your-google-api-key" | \
     gcloud secrets create GOOGLE_API_KEY --data-file=-

   echo -n "cal1@group.calendar.google.com,cal2@group.calendar.google.com" | \
     gcloud secrets create CALENDAR_IDS --data-file=-
   ```

3. Grant the App Engine default service account read access:
   ```bash
   PROJECT=$(gcloud config get-value project)
   SA="${PROJECT}@appspot.gserviceaccount.com"

   for SECRET in TIBBER_TOKEN AUDI_USERNAME AUDI_PASSWORD HOME_STOP_ID \
                 YR_LAT YR_LON HOME_LAT HOME_LON GOOGLE_API_KEY CALENDAR_IDS; do
     gcloud secrets add-iam-policy-binding "$SECRET" \
       --member="serviceAccount:${SA}" \
       --role="roles/secretmanager.secretAccessor"
   done
   ```

### Local development – `.env` file

1. Copy the example file and fill in your real values:
   ```bash
   cp .env.example .env
   # edit .env with your favourite editor
   ```

2. The `.env` file is listed in `.gitignore` and will **never** be committed.

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env          # then edit .env with your real values
python main.py
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
