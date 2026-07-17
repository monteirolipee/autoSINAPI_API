"""
Tests for STORY-GOLIVE-03 (Fase 3): Maturidade Operacional.

Covers AC1–AC6:
  1. /metrics endpoint exists and returns Prometheus-format data
  2. Admin endpoints require ADMIN_API_TOKEN
  3. schedule_monthly_etl computes correct target competência
  4. Sentry init depends on SENTRY_DSN being set
  5. Quota gauge updater runs without crashing
  6. schedule_monthly_etl dispatches populate_sinapi_task for each ETL_STATES
"""

import os
import sys
from unittest.mock import MagicMock, patch

# Mock autosinapi toolkit before any app import (it's not installed in test env)
sys.modules["autosinapi"] = MagicMock()
# Also mock the full object tree that tasks.py accesses
sys.modules["autosinapi.etl_pipeline"] = MagicMock()

# Set minimal required env before any app imports to avoid pydantic validation error
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

import pytest
from fastapi.testclient import TestClient
import datetime as dt_module
from dateutil.relativedelta import relativedelta

from api.main import app
from api import config as app_config
from api.populate_utils import compute_target_month, parse_etl_states


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def client():
    return TestClient(app)


# ── AC3: /metrics endpoint ───────────────────────────────────────

class TestMetricsEndpoint:
    def test_metrics_endpoint_exists(self):
        """Use with-client block to trigger on-event startup (instrumentator)."""
        with TestClient(app) as client:
            resp = client.get("/metrics")
            assert resp.status_code == 200, f"Got {resp.status_code}"
            body = resp.text
            assert "http_requests_total" in body or "python_info" in body

    def test_metrics_returns_prometheus_format(self):
        with TestClient(app) as client:
            resp = client.get("/metrics")
            lines = resp.text.splitlines()
            help_lines = [l for l in lines if l.startswith("# HELP")]
            assert len(help_lines) > 0, "Expected at least one # HELP line in Prometheus output"


# ── Cross-cutting: Admin auth ───────────────────────────────────

class TestAdminAuth:
    ADMIN_ENDPOINTS = [
        ("POST", "/api/v1/admin/populate-database"),
        ("GET", "/api/v1/admin/tasks/some-id"),
    ]

    def test_admin_fails_without_token(self, client):
        """Without ADMIN_API_TOKEN configured, returns 500."""
        for method, path in self.ADMIN_ENDPOINTS:
            resp = client.request(method, path, json={"year": 2026, "month": 1, "state": "SP"})
            assert resp.status_code == 500

    def test_admin_blocked_with_wrong_token(self, client):
        """With ADMIN_API_TOKEN set, wrong token returns 401."""
        with patch.object(app_config.settings, "ADMIN_API_TOKEN", "real-token"):
            for method, path in self.ADMIN_ENDPOINTS:
                resp = client.request(
                    method, path,
                    json={"year": 2026, "month": 1, "state": "SP"},
                    headers={"Authorization": "Bearer wrong-token"},
                )
                assert resp.status_code == 401

    def test_admin_allowed_with_valid_token(self):
        """Valid token passes the dependency."""
        from api.main import verify_admin_token
        with patch.object(app_config.settings, "ADMIN_API_TOKEN", "test-admin-token-123"):
            try:
                verify_admin_token(authorization="Bearer test-admin-token-123")
            except Exception as exc:
                pytest.fail(f"verify_admin_token raised {exc}")

    def test_admin_rejected_without_bearer_prefix(self):
        """Authorization header without 'Bearer ' prefix returns 401."""
        from api.main import verify_admin_token
        from fastapi import HTTPException
        with patch.object(app_config.settings, "ADMIN_API_TOKEN", "token"):
            with pytest.raises(HTTPException) as exc:
                verify_admin_token(authorization="token")
            assert exc.value.status_code == 401


# ── AC1: Pure logic tests for schedule_monthly_etl helpers ──────

class TestComputeTargetMonth:
    def test_returns_previous_month_by_default(self):
        year, month = compute_target_month(lookback=1)
        now = dt_module.datetime.now(dt_module.timezone.utc)
        expected = now - relativedelta(months=1)
        assert (year, month) == (expected.year, expected.month)

    def test_handles_year_wrap(self):
        with patch("api.populate_utils.datetime") as mock_dt:
            mock_dt.now.return_value = dt_module.datetime(2026, 1, 15, 3, 0, 0, tzinfo=dt_module.timezone.utc)
            mock_dt.timezone = dt_module.timezone
            year, month = compute_target_month(lookback=1)
            assert (year, month) == (2025, 12)

    def test_lookback_months_parameter(self):
        with patch("api.populate_utils.datetime") as mock_dt:
            mock_dt.now.return_value = dt_module.datetime(2026, 6, 15, 3, 0, 0, tzinfo=dt_module.timezone.utc)
            mock_dt.timezone = dt_module.timezone
            year, month = compute_target_month(lookback=3)
            assert (year, month) == (2026, 3)


class TestParseEtlStates:
    def test_single_state(self):
        assert parse_etl_states("SP") == ["SP"]

    def test_multiple_states(self):
        assert parse_etl_states("SP,RJ,MG") == ["SP", "RJ", "MG"]

    def test_strip_whitespace(self):
        assert parse_etl_states(" SP , RJ ") == ["SP", "RJ"]

    def test_default_sp(self):
        assert parse_etl_states("SP") == ["SP"]

    def test_handles_empty_segments(self):
        assert parse_etl_states("SP,,RJ") == ["SP", "RJ"]

    def test_uppercase(self):
        assert parse_etl_states("sp") == ["SP"]


# ── AC1: schedule_monthly_etl dispatches correctly ─────────────

class TestScheduleMonthlyEtl:
    @patch("api.populate_utils.dispatch_populate")
    @patch("api.populate_utils.datetime")
    def test_dispatches_for_each_state(self, mock_dt, mock_dispatch):
        mock_dt.now.return_value = dt_module.datetime(2026, 6, 15, 3, 0, 0, tzinfo=dt_module.timezone.utc)
        mock_dt.timezone = dt_module.timezone
        from api.tasks import schedule_monthly_etl
        with patch.object(app_config.settings, "ETL_LOOKBACK_MONTHS", 2), \
             patch.object(app_config.settings, "ETL_STATES", "SP,RJ"):
            schedule_monthly_etl()
            assert mock_dispatch.call_count == 2
            mock_dispatch.assert_any_call(2026, 4, "SP")
            mock_dispatch.assert_any_call(2026, 4, "RJ")


# ── AC4: Sentry init ────────────────────────────────────────────

class TestSentryInit:
    @patch("api.main.sentry_sdk")
    def test_sentry_not_inited_without_dsn(self, mock_sentry):
        from api.main import _init_sentry
        with patch.object(app_config.settings, "SENTRY_DSN", None):
            _init_sentry()
            mock_sentry.init.assert_not_called()

    @patch("api.main.sentry_sdk")
    def test_sentry_inited_with_dsn(self, mock_sentry):
        from api.main import _init_sentry
        with patch.object(app_config.settings, "SENTRY_DSN", "https://key@sentry.io/123"):
            _init_sentry()
            mock_sentry.init.assert_called_once()


# ── AC5: Quota gauge updater ─────────────────────────────────────

class TestQuotaGauge:
    def test_update_quota_gauges_does_not_crash_without_db(self):
        from api.main import _update_quota_gauges
        stop = MagicMock()
        stop.is_set.side_effect = [False, True]  # Run once then stop
        # Should not raise even without DB (engine may fail to connect)
        try:
            _update_quota_gauges(stop)
        except Exception as exc:
            pytest.fail(f"update_quota_gauges raised {exc}")
