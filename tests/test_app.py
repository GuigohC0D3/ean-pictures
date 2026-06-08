"""Testes das rotas Flask (com o serviço externo mockado)."""

import pytest

import app as app_module
from services import InvalidEANError, ProductNotFoundError

VALID = "7891000100103"


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Histórico isolado em arquivo temporário.
    monkeypatch.setattr(app_module, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(app_module, "DATA_DIR", tmp_path)
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def _fake_product(ean, providers=None):
    return {"ean": ean, "name": "Leite Moça", "image": "http://i/x.png",
            "description": "leite", "source": "OFF", "from_cache": False}


def test_index_ok(client):
    assert client.get("/").status_code == 200


def test_api_product_ok(client, monkeypatch):
    monkeypatch.setattr(app_module.service, "get_product", _fake_product)
    resp = client.get(f"/api/product/{VALID}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ean"] == VALID
    assert set(body) == {"ean", "name", "image", "description"}


def test_api_product_invalido(client, monkeypatch):
    def boom(ean, providers=None):
        raise InvalidEANError("invalido")
    monkeypatch.setattr(app_module.service, "get_product", boom)
    resp = client.get("/api/product/123")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_ean"


def test_api_batch_json(client, monkeypatch):
    monkeypatch.setattr(app_module.service, "get_product", _fake_product)
    resp = client.post("/api/batch", json={"eans": f"{VALID}\n{VALID}", "provider": "auto"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["summary"]["found"] == 1   # deduplicado
    assert body["results"][0]["ean"] == VALID


def test_api_batch_vazio(client):
    resp = client.post("/api/batch", json={"eans": "lixo sem ean"})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "empty"


def test_api_batch_export_csv(client, monkeypatch):
    monkeypatch.setattr(app_module.service, "get_product", _fake_product)
    resp = client.post("/api/batch/export.csv", json={"eans": [VALID]})
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
    assert b"produtos.csv" in resp.headers["Content-Disposition"].encode()
    assert VALID.encode() in resp.data


def test_api_batch_export_formato_invalido(client):
    resp = client.post("/api/batch/export.pdf", json={"eans": [VALID]})
    assert resp.status_code == 400
