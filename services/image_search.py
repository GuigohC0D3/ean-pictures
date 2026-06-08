"""
Busca de imagem por nome do produto (fallback).

Quando a cascata de provedores encontra o produto mas **sem foto** (cenário
comum: ~77% dos itens no benchmark), tentamos achar uma imagem por busca textual.

Backends suportados (escolha por IMAGE_SEARCH_PROVIDER):
    - google   -> Google Custom Search JSON API (100 buscas/dia grátis)
                  requer GOOGLE_CSE_KEY + GOOGLE_CSE_CX
    - serpapi  -> SerpAPI (engine google_images), requer SERPAPI_KEY

Fica DESLIGADO por padrão: sem provider/credenciais, from_env() devolve None e
a busca de imagem é simplesmente pulada (nunca quebra a consulta principal).
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger("ean_service")

# Domínios de imagem que costumam bloquear hotlink ou ser thumbnails ruins.
# Evita devolvê-los quando há alternativa.
_BAD_IMAGE_HOSTS = ("lookaside.", "encrypted-tbn", "gstatic.com")


class ImageSearcher:
    """Busca a URL de uma imagem a partir de um texto (nome do produto)."""

    def __init__(self, provider: str, timeout: int = 10) -> None:
        self.provider = provider
        self.timeout = timeout
        self.label = {"google": "Google Imagens", "serpapi": "SerpAPI"}.get(
            provider, provider
        )

    def search(self, query: str) -> str | None:
        """Devolve a URL da 1ª imagem encontrada, ou None. Nunca levanta."""
        query = (query or "").strip()
        if not query:
            return None
        try:
            if self.provider == "google":
                return self._search_google(query)
            if self.provider == "serpapi":
                return self._search_serpapi(query)
        except requests.exceptions.RequestException as exc:
            logger.warning("  [image-search] falha (%s): %s", self.provider, exc)
        except (ValueError, KeyError, IndexError) as exc:
            logger.warning("  [image-search] resposta inesperada (%s): %s", self.provider, exc)
        return None

    # ------------------------------------------------------------------ #
    def _search_google(self, query: str) -> str | None:
        key = os.getenv("GOOGLE_CSE_KEY")
        cx = os.getenv("GOOGLE_CSE_CX")
        if not key or not cx:
            return None
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": key,
                "cx": cx,
                "q": query,
                "searchType": "image",
                "num": 3,
                "safe": "active",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        items = resp.json().get("items") or []
        return self._pick(item.get("link") for item in items)

    def _search_serpapi(self, query: str) -> str | None:
        key = os.getenv("SERPAPI_KEY")
        if not key:
            return None
        resp = requests.get(
            "https://serpapi.com/search.json",
            params={"engine": "google_images", "q": query, "api_key": key, "num": 3},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        results = resp.json().get("images_results") or []
        return self._pick(r.get("original") or r.get("thumbnail") for r in results)

    @staticmethod
    def _pick(urls) -> str | None:
        """Escolhe a 1ª URL http(s) que não seja de um host problemático."""
        first_any = None
        for url in urls:
            if not url or not isinstance(url, str) or not url.startswith("http"):
                continue
            if first_any is None:
                first_any = url
            if not any(bad in url for bad in _BAD_IMAGE_HOSTS):
                return url
        return first_any


def from_env(timeout: int = 10) -> ImageSearcher | None:
    """
    Cria o searcher conforme as variáveis de ambiente, ou None se não configurado.

    IMAGE_SEARCH_PROVIDER define o backend; cada um exige suas credenciais.
    """
    provider = os.getenv("IMAGE_SEARCH_PROVIDER", "").strip().lower()
    if provider == "google" and os.getenv("GOOGLE_CSE_KEY") and os.getenv("GOOGLE_CSE_CX"):
        return ImageSearcher("google", timeout)
    if provider == "serpapi" and os.getenv("SERPAPI_KEY"):
        return ImageSearcher("serpapi", timeout)
    return None
