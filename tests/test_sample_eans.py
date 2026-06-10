"""Garante a integridade da lista curada de EANs (sem dígito inválido/duplicata)."""

from services import EANPicturesService
from tests.sample_eans import DROGARIA_GLOBO, SOURCES, all_eans


def test_todos_os_eans_da_globo_sao_validos():
    invalidos = [
        ean
        for categoria in DROGARIA_GLOBO.values()
        for ean in categoria
        if not EANPicturesService.is_valid_ean(ean)
    ]
    assert invalidos == [], f"EANs com dígito verificador inválido: {invalidos}"


def test_all_eans_remove_duplicatas_e_preserva_ordem():
    eans = all_eans("globo")
    assert len(eans) == len(set(eans))
    assert eans[0] == next(iter(next(iter(DROGARIA_GLOBO.values()))))


def test_sources_expoe_globo():
    assert "globo" in SOURCES
    assert SOURCES["globo"] is DROGARIA_GLOBO
