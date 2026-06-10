"""Testes do módulo de lote: extração de EANs, lookup paralelo e export."""

import pytest

import io

from services import (
    EANPicturesService,
    InvalidEANError,
    build_cosmos_product_image_url,
    cosmos_image_url_if_available,
    extract_cosmos_image_urls_from_pdf,
    extract_eans_from_text,
    lookup_batch,
    resolve_cosmos_image_urls,
    results_to_csv,
    summarize,
)
from services.batch import extract_eans_from_csv, results_to_xlsx

VALID_A = "7891000100103"
VALID_B = "3017620422003"

JPEG_MAGIC = b"\xff\xd8\xff\xe0\x00\x10JFIF"


class _FakeResponse:
    """Resposta mínima compatível com o uso em cosmos_image_url_if_available."""

    def __init__(self, status_code, content, content_type=""):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.raw = io.BytesIO(content)
        self.content = content

    def close(self):
        pass


def _fake_fetch(responses):
    """Devolve um fetch que responde por EAN conforme o mapa {ean: _FakeResponse}."""

    def fetch(url, **_kw):
        ean = url.rsplit("/", 1)[-1]
        return responses[ean]

    return fetch


def test_extrai_eans_de_texto_misto():
    text = f"Produto 1: {VALID_A}\nlixo 123 abc\noutro {VALID_B} fim"
    assert extract_eans_from_text(text) == [VALID_A, VALID_B]


def test_extrai_remove_separadores_e_duplicatas():
    # Código formatado com . e -, depois repetido (deve deduplicar).
    text = f"7891000-100103\n{VALID_A}\n{VALID_B}"
    out = extract_eans_from_text(text)
    assert out == [VALID_A, VALID_B]   # juntou os dígitos e deduplicou


def test_extrai_descarta_invalidos():
    # 7891000100104 tem dígito verificador errado -> deve sair.
    assert extract_eans_from_text("7891000100104") == []


def test_extrai_de_csv():
    data = f"nome,codigo\nLeite,{VALID_A}\nNutella,{VALID_B}\n".encode("utf-8")
    assert extract_eans_from_csv(data) == [VALID_A, VALID_B]


def test_monta_url_de_imagem_cosmos():
    assert build_cosmos_product_image_url(f"  {VALID_A}  ") == (
        f"https://cdn-cosmos.bluesoft.com.br/products/{VALID_A}"
    )


def test_url_de_imagem_cosmos_rejeita_ean_invalido():
    with pytest.raises(InvalidEANError):
        build_cosmos_product_image_url("7891000100104")


def test_extrai_urls_cosmos_do_pdf(monkeypatch):
    monkeypatch.setattr(
        "services.batch.extract_eans_from_pdf",
        lambda _data: [VALID_A, VALID_B],
    )

    assert extract_cosmos_image_urls_from_pdf(b"pdf") == [
        f"https://cdn-cosmos.bluesoft.com.br/products/{VALID_A}",
        f"https://cdn-cosmos.bluesoft.com.br/products/{VALID_B}",
    ]


def test_cosmos_url_disponivel_quando_imagem_valida():
    fetch = _fake_fetch({VALID_A: _FakeResponse(200, JPEG_MAGIC, "image/jpeg")})
    assert cosmos_image_url_if_available(VALID_A, fetch=fetch) == (
        f"https://cdn-cosmos.bluesoft.com.br/products/{VALID_A}"
    )


def test_cosmos_url_none_em_404():
    fetch = _fake_fetch({VALID_A: _FakeResponse(404, b"<html>nao</html>", "text/html")})
    assert cosmos_image_url_if_available(VALID_A, fetch=fetch) is None


def test_cosmos_url_none_quando_conteudo_nao_e_imagem():
    # HTTP 200 mas corpo minúsculo/sem assinatura de imagem (caso INVALID_CONTENT).
    fetch = _fake_fetch({VALID_A: _FakeResponse(200, b"not-an-image", "text/plain")})
    assert cosmos_image_url_if_available(VALID_A, fetch=fetch) is None


def test_cosmos_url_none_para_ean_invalido():
    assert cosmos_image_url_if_available("7891000100104") is None


def test_resolve_cosmos_urls_filtra_indisponiveis():
    fetch = _fake_fetch(
        {
            VALID_A: _FakeResponse(200, JPEG_MAGIC, "image/jpeg"),
            VALID_B: _FakeResponse(404, b"x", "text/html"),
        }
    )
    assert resolve_cosmos_image_urls([VALID_A, VALID_B], fetch=fetch) == {
        VALID_A: f"https://cdn-cosmos.bluesoft.com.br/products/{VALID_A}"
    }


def test_lookup_batch_preserva_ordem(monkeypatch):
    svc = EANPicturesService(provider="openfoodfacts")

    def fake_get(ean, providers=None):
        if ean == VALID_B:
            from services import ProductNotFoundError
            raise ProductNotFoundError("nao")
        return {"ean": ean, "name": "Leite", "image": "u", "source": "OFF"}

    monkeypatch.setattr(svc, "get_product", fake_get)

    results = lookup_batch(svc, [VALID_A, VALID_B])
    assert [r["ean"] for r in results] == [VALID_A, VALID_B]
    assert results[0]["found"] is True
    assert results[1]["found"] is False
    assert results[1]["code"] == "not_found"


def test_summarize_e_csv():
    results = [
        {"ean": VALID_A, "found": True, "image": "u", "name": "A", "source": "OFF", "description": "", "error": ""},
        {"ean": VALID_B, "found": False, "image": "", "name": "", "source": "", "description": "", "error": "x"},
    ]
    s = summarize(results)
    assert s == {"total": 2, "found": 1, "not_found": 1, "with_image": 1}

    csv_text = results_to_csv(results)
    assert "ean,name,image" in csv_text
    assert VALID_A in csv_text


def test_export_xlsx_gera_bytes():
    results = [{"ean": VALID_A, "found": True, "image": "", "name": "A", "source": "OFF", "description": "", "error": ""}]
    blob = results_to_xlsx(results)
    assert blob[:2] == b"PK"   # assinatura de arquivo zip/xlsx
