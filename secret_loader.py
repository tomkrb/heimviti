"""Secret loading for heimviti.

Production (Google App Engine / Cloud Run)
------------------------------------------
Secrets are fetched at startup from **Google Cloud Secret Manager**.
The application's service account must have the
``roles/secretmanager.secretAccessor`` IAM role, and the
``GOOGLE_CLOUD_PROJECT`` environment variable must be set to the GCP
project ID.  App Engine and Cloud Run set this variable automatically;
do **not** override it with an empty string in ``app.yaml``.

Local development
-----------------
Values are loaded from a ``.env`` file in the project root (via
``python-dotenv``).  Copy ``.env.example`` to ``.env`` and fill in your
real values.  The ``.env`` file is git-ignored and must **never** be
committed.
"""

import logging
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detect whether we are running on Google Cloud (App Engine / Cloud Run)
# ---------------------------------------------------------------------------
_IS_GCP = bool(
    os.environ.get("GAE_APPLICATION")   # App Engine standard
    or os.environ.get("GAE_SERVICE")    # App Engine flex
    or os.environ.get("K_SERVICE")      # Cloud Run
)

# ---------------------------------------------------------------------------
# Local development: load .env if present
# ---------------------------------------------------------------------------
if not _IS_GCP:
    try:
        from dotenv import load_dotenv

        load_dotenv()
        logger.debug("Loaded .env file for local development")
    except ImportError:
        logger.debug("python-dotenv not installed; relying on shell environment")


# ---------------------------------------------------------------------------
# Secret Manager client (initialised lazily)
# ---------------------------------------------------------------------------
_sm_client = None


def _get_sm_client():
    """Return a cached Secret Manager client (production only)."""
    global _sm_client  # pylint: disable=global-statement
    if _sm_client is None:
        from google.cloud import secretmanager  # pylint: disable=import-outside-toplevel

        _sm_client = secretmanager.SecretManagerServiceClient()
    return _sm_client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_secret(name: str, default: str = "") -> str:
    """Return the value for *name*.

    In production the value is fetched from Google Cloud Secret Manager
    (``projects/<project>/secrets/<name>/versions/latest``).

    Locally the value is taken from the process environment, which is
    populated from the ``.env`` file.

    Parameters
    ----------
    name:
        The secret / environment-variable name, e.g. ``"TIBBER_TOKEN"``.
    default:
        Fallback value when the secret cannot be retrieved.
    """
    if _IS_GCP:
        return _from_secret_manager(name, default)
    value = os.environ.get(name, default)
    if not value and not default:
        logger.warning("Secret '%s' is not set in .env or environment", name)
    return value


def _from_secret_manager(name: str, default: str = "") -> str:
    """Fetch *name* from Google Cloud Secret Manager (latest version)."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if not project_id:
        logger.error(
            "GOOGLE_CLOUD_PROJECT is not set; cannot fetch secret '%s'", name
        )
        return default

    secret_path = f"projects/{project_id}/secrets/{name}/versions/latest"
    try:
        client = _get_sm_client()
        response = client.access_secret_version(request={"name": secret_path})
        return response.payload.data.decode("utf-8").strip()
    except Exception as exc:  # pylint: disable=broad-except
        logger.error(
            "Failed to fetch secret '%s' from Secret Manager: %s", name, exc
        )
        return default
