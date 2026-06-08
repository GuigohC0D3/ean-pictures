"""Testes do EANPicturesService: validação, cache, cascata e merge de imagem."""

import pytest

from services import (
    APIUnavailableError,
    EANPicturesService,
    InvalidEANError,
    ProductNotFoundError,
    SqliteCache,
)

VALID_EAN = "7891000100103"      # Leite Moça (EAN-13 válido)
INVALID_EAN = "7891000100104"    # dígito verificador errado


# --------------------------------------------------------------------------- #
# Validação
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ean", ["7891000100103", "3017620422003", "0036000291452"])
def test_eans_validos(ean):
    assert EANPicturesService.is_valid_ean(ean)


@pytest.mark.parametrize("ean", ["", "abc", "123", INVALID_EAN, "78910001001031"])
def test_eans_invalidos(ean):
    assert not EANPicturesService.is_valid_ean(ean)


def test_get_product_ean_invalido_levanta():
    svc = EANPicturesService(provider="openfoodfacts")
    with pytest.raises(InvalidEANError):
        svc.get_product(INVALID_EAN)


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #
def test_cache_evita_segunda_consulta(monkeypatch):
    svc = EANPicturesService(provider="openfoodfacts")
    calls = {"n": 0}

    def fake_fetch(provider, ean, base_url):
        calls["n"] += 1
        return {"ean": ean, "name": "X", "image": "u", "description": "", "source": "OFF"}

    monkeypatch.setattr(svc, "_fetch_one", fake_fetch)

    p1 = svc.get_product(VALID_EAN)
    p2 = svc.get_product(VALID_EAN)
    assert calls["n"] == 1            # 2ª veio do cache
    assert p1["from_cache"] is False
    assert p2["from_cache"] is True


def test_sqlite_cache_persiste_roundtrip():
    cache = SqliteCache(":memory:", ttl=3600)
    cache.set("k", {"ean": "1", "name": "Y"})
    assert cache.get("k") == {"ean": "1", "name": "Y"}
    cache.clear()
    assert cache.get("k") is None


def test_sqlite_cache_expira():
    cache = SqliteCache(":memory:", ttl=0)
    # ttl explícito negativo no set -> já expirado.
    cache.set("k", {"v": 1}, ttl=-1)
    assert cache.get("k") is None


# --------------------------------------------------------------------------- #
# Cascata + merge de imagem
# --------------------------------------------------------------------------- #
def test_merge_imagem_mantem_nome_preferido(monkeypatch):
    svc = EANPicturesService(provider="cosmos,openfoodfacts")

    def fake_fetch(provider, ean, base_url):
        if provider == "cosmos":
            return {"ean": ean, "name": "Nome BR", "image": "", "source": "Cosmos"}
        return {"ean": ean, "name": "Generic", "image": "http://img", "source": "OFF"}

    monkeypatch.setattr(svc, "_fetch_one", fake_fetch)

    p = svc.get_product(VALID_EAN)
    assert p["name"] == "Nome BR"          # nome do provedor preferido
    assert p["image"] == "http://img"      # imagem herdada do posterior
    assert p["image_source"] == "OFF"


def test_cascata_pula_indisponivel(monkeypatch):
    svc = EANPicturesService(provider="cosmos,openfoodfacts")

    def fake_fetch(provider, ean, base_url):
        if provider == "cosmos":
            raise APIUnavailableError("sem token")
        return {"ean": ean, "name": "OK", "image": "http://i", "source": "OFF"}

    monkeypatch.setattr(svc, "_fetch_one", fake_fetch)
    assert svc.get_product(VALID_EAN)["name"] == "OK"


class _FakeSearcher:
    """Searcher de imagem fake para os testes (não toca a rede)."""

    label = "Fake"

    def __init__(self, url):
        self.url = url
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        return self.url


def test_image_fallback_preenche_foto(monkeypatch):
    fake = _FakeSearcher("http://img/found.jpg")
    svc = EANPicturesService(provider="openfoodfacts", image_searcher=fake)

    def fake_fetch(provider, ean, base_url):
        return {"ean": ean, "name": "Dipirona", "image": "",
                "extra": {"Marca": "EMS"}, "source": "Cosmos"}

    monkeypatch.setattr(svc, "_fetch_one", fake_fetch)
    p = svc.get_product(VALID_EAN)
    assert p["image"] == "http://img/found.jpg"
    assert p["image_source"] == "Fake"
    assert fake.queries == ["EMS Dipirona"]   # marca + nome


def test_image_fallback_nao_chama_se_ja_tem_foto(monkeypatch):
    fake = _FakeSearcher("http://nao/deveria.jpg")
    svc = EANPicturesService(provider="openfoodfacts", image_searcher=fake)
    monkeypatch.setattr(
        svc, "_fetch_one",
        lambda *a: {"ean": VALID_EAN, "name": "X", "image": "http://ja/tem.jpg", "source": "OFF"},
    )
    p = svc.get_product(VALID_EAN)
    assert p["image"] == "http://ja/tem.jpg"
    assert fake.queries == []          # searcher não foi usado


def test_image_searcher_pick_evita_hosts_ruins():
    from services import ImageSearcher
    pick = ImageSearcher._pick
    assert pick(["http://encrypted-tbn0.gstatic.com/x", "http://boa.com/i.jpg"]) == "http://boa.com/i.jpg"
    assert pick(["not-a-url", "https://ok.com/a.png"]) == "https://ok.com/a.png"
    assert pick([]) is None


def test_cascata_todos_nao_encontram(monkeypatch):
    svc = EANPicturesService(provider="openfoodfacts")
    monkeypatch.setattr(
        svc, "_fetch_one",
        lambda *a: (_ for _ in ()).throw(ProductNotFoundError("nao")),
    )
    with pytest.raises(ProductNotFoundError):
        svc.get_product(VALID_EAN)
