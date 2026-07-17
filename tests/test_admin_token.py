"""
Testes para P1-C: constant-time admin token (SR-API-2).

Valida:
1. ADMIN_API_TOKEN ausente → 500 controlado.
2. Token inválido → 401.
3. Token válido → endpoint responde.
4. Algoritmo de comparação usa `secrets.compare_digest`.
"""
import secrets
import os
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app, verify_admin_token


class TestVerifyAdminTokenFunction:
    """Testes unitários da função verify_admin_token."""

    def test_missing_env_raises_500(self):
        with patch("api.main.settings.ADMIN_API_TOKEN", None):
            with pytest.raises(HTTPException) as exc:
                verify_admin_token(authorization="Bearer any-token")
            assert exc.value.status_code == 500
            assert "not configured" in exc.value.detail.lower()

    def test_missing_header_raises_401(self):
        with patch("api.main.settings.ADMIN_API_TOKEN", "real-token"):
            with pytest.raises(HTTPException) as exc:
                verify_admin_token(authorization=None)
            assert exc.value.status_code == 401

    def test_invalid_token_raises_401(self):
        with patch("api.main.settings.ADMIN_API_TOKEN", "real-token"):
            with pytest.raises(HTTPException) as exc:
                verify_admin_token(authorization="Bearer wrong-token")
            assert exc.value.status_code == 401

    def test_valid_token_succeeds(self):
        with patch("api.main.settings.ADMIN_API_TOKEN", "real-token"):
            result = verify_admin_token(authorization="Bearer real-token")
            assert result is None

    def test_uses_compare_digest(self):
        """Verificação estática: verify_admin_token deve usar secrets.compare_digest
        para evitar timing attack (SR-API-2)."""
        import inspect
        source = inspect.getsource(verify_admin_token)
        assert "compare_digest" in source, (
            "verify_admin_token precisa usar secrets.compare_digest "
            "para comparação constante"
        )

    def test_compare_digest_semantic(self):
        """Teste semântico: compare_digest rejeita diferentes e aceita iguais."""
        admin_token = "super-secret-token"
        cases = [
            (admin_token, admin_token, True),
            (admin_token, "wrong", False),
            (admin_token, "", False),
            (admin_token, "SUPER-SECRET-TOKEN", False),
        ]
        for a, b, expected in cases:
            assert secrets.compare_digest(a, b) == expected


@pytest.fixture(autouse=True)
def _patch_admin_token():
    """Override ADMIN_API_TOKEN for all integration tests."""
    patcher = patch("api.main.settings.ADMIN_API_TOKEN", "test-admin-token")
    patcher.start()
    yield
    patcher.stop()


class TestAdminTokenIntegration:
    """Testes de integração via HTTP contra o app."""

    def test_missing_header_returns_401(self):
        client = TestClient(app)
        resp = client.post("/api/v1/admin/populate-database")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/admin/populate-database",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    def test_invalid_prefix_returns_401(self):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/admin/populate-database",
            headers={"Authorization": "Token test-admin-token"},
        )
        assert resp.status_code == 401
