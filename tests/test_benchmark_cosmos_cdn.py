"""Testes do benchmark direto da CDN Cosmos."""

import requests

from tests.benchmark_cosmos_cdn import (
    check_cdn_image,
    detect_image_type,
    run_benchmark,
    summarize,
)

VALID_A = "7891000100103"
VALID_B = "3017620422003"


class _FakeResponse:
    def __init__(self, status_code, content_type="", content=b""):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.content = content


def test_check_cdn_image_confirma_imagem():
    result = check_cdn_image(
        VALID_A,
        fetch=lambda *_args, **_kwargs: _FakeResponse(
            200, "image/jpeg; charset=binary", b"imagem"
        ),
    )

    assert result["status"] == "OK"
    assert result["content_type"] == "image/jpeg"
    assert result["size_bytes"] == 6


def test_check_cdn_image_rejeita_html_com_http_200():
    result = check_cdn_image(
        VALID_A,
        fetch=lambda *_args, **_kwargs: _FakeResponse(
            200, "text/html", b"<html></html>"
        ),
    )

    assert result["status"] == "INVALID_CONTENT"


def test_check_cdn_image_detecta_jpeg_sem_content_type():
    result = check_cdn_image(
        VALID_A,
        fetch=lambda *_args, **_kwargs: _FakeResponse(
            200, "", b"\xff\xd8\xff\xe0imagem"
        ),
    )

    assert result["status"] == "OK"
    assert result["detected_type"] == "image/jpeg"


def test_detect_image_type_reconhece_formatos_comuns():
    assert detect_image_type(b"\x89PNG\r\n\x1a\nresto") == "image/png"
    assert detect_image_type(b"GIF89aresto") == "image/gif"
    assert detect_image_type(b"RIFF1234WEBPresto") == "image/webp"
    assert detect_image_type(b"<html>") == ""


def test_check_cdn_image_trata_404():
    result = check_cdn_image(
        VALID_A,
        fetch=lambda *_args, **_kwargs: _FakeResponse(404, "text/html", b""),
    )

    assert result["status"] == "NOT_FOUND"
    assert result["status_code"] == 404


def test_check_cdn_image_trata_falha_de_rede():
    def fail(*_args, **_kwargs):
        raise requests.Timeout("tempo esgotado")

    result = check_cdn_image(VALID_A, fetch=fail)

    assert result["status"] == "REQUEST_ERROR"
    assert result["status_code"] == 0


def test_run_benchmark_preserva_ordem_e_resume():
    def fetch(url, **_kwargs):
        if url.endswith(VALID_A):
            return _FakeResponse(200, "image/png", b"abc")
        return _FakeResponse(404, "text/html", b"")

    results = run_benchmark([VALID_A, VALID_B], workers=2, fetch=fetch)
    summary = summarize(results)

    assert [result["ean"] for result in results] == [VALID_A, VALID_B]
    assert summary["total"] == 2
    assert summary["available"] == 1
    assert summary["missing"] == 1
    assert summary["coverage"] == 50.0
