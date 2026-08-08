# tests/test_legal.py
import pytest
from fastapi.testclient import TestClient
from api.main import app
from api import legal_service

client = TestClient(app)


def test_load_legal_ssot():
    ssot = legal_service.load_legal_ssot()
    assert isinstance(ssot, dict)
    assert "company" in ssot
    assert "cnpj" in ssot["company"]


def test_get_legal_document_valid():
    doc = legal_service.get_legal_document("privacidade")
    assert doc["doc_name"] == "privacidade"
    assert "content_markdown" in doc
    assert doc["ssot_used"].get("cnpj") in doc["content_markdown"]


def test_get_legal_document_invalid():
    with pytest.raises(ValueError):
        legal_service.get_legal_document("documento_inexistente")


def test_endpoint_get_legal_doc_success():
    response = client.get("/api/v1/public/legal/tos")
    assert response.status_code == 200
    data = response.json()
    assert data["doc_name"] == "tos"
    assert "content_markdown" in data


def test_endpoint_get_legal_doc_not_found():
    response = client.get("/api/v1/public/legal/invalido")
    assert response.status_code == 404
