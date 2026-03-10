"""Tests for the secret_loader module."""

import importlib
import sys
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_secret_loader(gcp_env: bool = False):
    """Reload the secret_loader module under a controlled environment.

    Removes cached module state so each test starts fresh.
    """
    for mod_name in list(sys.modules.keys()):
        if mod_name in ("secret_loader",) or mod_name.startswith("secret_loader."):
            del sys.modules[mod_name]

    gae_env = {"GAE_APPLICATION": "t~test-project"} if gcp_env else {}
    with patch.dict("os.environ", gae_env, clear=False):
        import secret_loader as s

        importlib.reload(s)
    return s


# ---------------------------------------------------------------------------
# Local (non-GCP) behaviour
# ---------------------------------------------------------------------------


class TestLocalSecrets:
    def test_get_secret_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("TIBBER_TOKEN", "local-token-123")
        import secret_loader as s

        # Force local mode
        monkeypatch.setattr(s, "_IS_GCP", False)

        assert s.get_secret("TIBBER_TOKEN") == "local-token-123"

    def test_get_secret_returns_default_when_missing(self, monkeypatch):
        monkeypatch.delenv("SOME_MISSING_VAR", raising=False)
        import secret_loader as s

        monkeypatch.setattr(s, "_IS_GCP", False)

        assert s.get_secret("SOME_MISSING_VAR", "fallback") == "fallback"

    def test_get_secret_empty_default(self, monkeypatch):
        monkeypatch.delenv("SOME_MISSING_VAR", raising=False)
        import secret_loader as s

        monkeypatch.setattr(s, "_IS_GCP", False)

        assert s.get_secret("SOME_MISSING_VAR") == ""


# ---------------------------------------------------------------------------
# Production (GCP) behaviour
# ---------------------------------------------------------------------------


class TestProductionSecrets:
    def _make_sm_response(self, value: str) -> MagicMock:
        response = MagicMock()
        response.payload.data = value.encode("utf-8")
        return response

    def test_get_secret_fetches_from_secret_manager(self, monkeypatch):
        import secret_loader as s

        monkeypatch.setattr(s, "_IS_GCP", True)
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
        monkeypatch.setattr(s, "_sm_client", None)

        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = self._make_sm_response(
            "prod-token-xyz"
        )

        with patch("secret_loader._get_sm_client", return_value=mock_client):
            result = s.get_secret("TIBBER_TOKEN")

        assert result == "prod-token-xyz"
        mock_client.access_secret_version.assert_called_once_with(
            request={
                "name": "projects/my-project/secrets/TIBBER_TOKEN/versions/latest"
            }
        )

    def test_get_secret_strips_trailing_newline(self, monkeypatch):
        import secret_loader as s

        monkeypatch.setattr(s, "_IS_GCP", True)
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")

        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = self._make_sm_response(
            "token-with-newline\n"
        )

        with patch("secret_loader._get_sm_client", return_value=mock_client):
            result = s.get_secret("TIBBER_TOKEN")

        assert result == "token-with-newline"

    def test_get_secret_returns_default_when_project_missing(self, monkeypatch):
        import secret_loader as s

        monkeypatch.setattr(s, "_IS_GCP", True)
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

        result = s.get_secret("TIBBER_TOKEN", "fallback")

        assert result == "fallback"

    def test_get_secret_returns_default_on_sm_error(self, monkeypatch):
        import secret_loader as s

        monkeypatch.setattr(s, "_IS_GCP", True)
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")

        mock_client = MagicMock()
        mock_client.access_secret_version.side_effect = Exception(
            "Secret not found"
        )

        with patch("secret_loader._get_sm_client", return_value=mock_client):
            result = s.get_secret("MISSING_SECRET", "safe-default")

        assert result == "safe-default"
