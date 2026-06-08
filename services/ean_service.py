"""
Serviço de integração com a API EAN Pictures.

Encapsula toda a lógica de consulta de produtos por código de barras (EAN/UPC).
É *agnóstico de provedor*: por padrão usa o Open Food Facts (gratuito, sem token),
mas pode ser apontado para o EAN-Search apenas trocando variáveis de ambiente.

Exceções de domínio:
    - InvalidEANError      -> EAN com formato/dígito verificador inválido
    - ProductNotFoundError -> produto não encontrado na base
    - APIUnavailableError  -> falha de rede / API fora do ar / timeout
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import threading
import time
from pathlib import Path

import requests

from .cache import SqliteCache
from .image_search import ImageSearcher
from .image_search import from_env as _image_searcher_from_env

# Logger do serviço. Por padrão fica silencioso (NullHandler); quem quiser ver
# os logs (ex.: tests/benchmark.py) configura o handler/level.
logger = logging.getLogger("ean_service")
logger.addHandler(logging.NullHandler())


# --------------------------------------------------------------------------- #
# Exceções de domínio
# --------------------------------------------------------------------------- #
class EANServiceError(Exception):
    """Erro base do serviço de EAN."""


class InvalidEANError(EANServiceError):
    """O código EAN informado é inválido."""


class ProductNotFoundError(EANServiceError):
    """Nenhum produto foi encontrado para o EAN informado."""


class APIUnavailableError(EANServiceError):
    """A API externa está indisponível ou não respondeu."""


# --------------------------------------------------------------------------- #
# Serviço
# --------------------------------------------------------------------------- #
class EANPicturesService:
    """
    Responsável por consultar produtos por EAN, formatar os dados e tratar erros.

    Possui um cache simples em memória (thread-safe) para evitar consultas
    repetidas ao mesmo código de barras durante a execução do servidor.
    """

    # Provedores suportados e seus endpoints padrão.
    _DEFAULT_BASE_URLS = {
        "cosmos": "https://api.cosmos.bluesoft.com.br/gtins",
        "ean-db": "https://ean-db.com/api/v2/product",
        "gtin": "https://gtin.rscsistemas.com.br",
        "upcitemdb": "https://api.upcitemdb.com/prod/trial/lookup",
        "openfoodfacts": "https://world.openfoodfacts.org/api/v2/product",
        "ean-search": "https://api.ean-search.org/api",
    }

    # Variável de ambiente com o token específico de cada provedor autenticado.
    # Se ausente, cai no EAN_API_TOKEN global.
    _PROVIDER_TOKEN_ENV = {
        "cosmos": "COSMOS_TOKEN",
        "ean-db": "EAN_DB_TOKEN",
        "gtin": "GTIN_TOKEN",
        "ean-search": "EAN_SEARCH_TOKEN",
    }

    # Base URL própria por provedor (sobrescreve o default acima, se definida).
    _PROVIDER_BASE_ENV = {
        "gtin": "GTIN_BASE_URL",
    }

    # Alguns servidores (RSC GTIN) têm WAF que bloqueia User-Agent não-navegador.
    _BROWSER_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )

    # O GTIN devolve uma imagem-placeholder (PNG fixo) quando NÃO tem foto real
    # do produto. Detectamos pela assinatura (tamanho + md5) para tratar como
    # "sem imagem" — assim o front mostra o aviso e, na cascata, outra fonte
    # com foto de verdade pode vencer.
    _GTIN_PLACEHOLDER_SIZE = 21773
    _GTIN_PLACEHOLDER_MD5 = "b16cf5a3e39f62b2f504e72a425de708"

    def __init__(
        self,
        provider: str | None = None,
        token: str | None = None,
        base_url: str | None = None,
        timeout: int = 10,
        cache_ttl: int | None = None,
        image_searcher: ImageSearcher | None = None,
    ) -> None:
        # Configuração via parâmetros ou variáveis de ambiente.
        # `provider` aceita uma lista separada por vírgula -> fallback em cascata.
        # Padrão: cobertura geral (UPCitemdb) + alimentos (Open Food Facts).
        raw = provider or os.getenv("EAN_API_PROVIDER", "upcitemdb,openfoodfacts")
        self.providers = [p.strip().lower() for p in raw.split(",") if p.strip()]
        self.token = token or os.getenv("EAN_API_TOKEN")
        # Override opcional do endpoint base (aplicado ao 1º provedor).
        self.base_url_override = base_url or os.getenv("EAN_API_BASE_URL")
        self.timeout = timeout
        # TTL do cache em segundos (0 = nunca expira). Padrão: 1 hora.
        self.cache_ttl = (
            cache_ttl if cache_ttl is not None else int(os.getenv("EAN_CACHE_TTL", "3600"))
        )
        # Merge de imagem: na cascata, herda a foto de um provedor posterior
        # mantendo os dados textuais do preferido. EAN_MERGE_IMAGE=0 desliga.
        self.merge_image = os.getenv("EAN_MERGE_IMAGE", "1") != "0"

        # Fallback de imagem por nome: quando o produto é achado SEM foto, busca
        # uma imagem por texto (Google CSE / SerpAPI). None = desligado.
        self.image_searcher = (
            image_searcher if image_searcher is not None
            else _image_searcher_from_env(self.timeout)
        )

        # Cache em memória (L1): {ean: (produto_formatado, expira_em_epoch)}.
        self._cache: dict[str, tuple[dict, float]] = {}
        self._lock = threading.Lock()

        # Cache persistente (L2, opcional): sobrevive a reinícios do servidor.
        # EAN_CACHE_BACKEND=memory desliga; sqlite (padrão) grava em disco.
        # EAN_CACHE_PATH define o arquivo (padrão: data/cache.db ao lado do app).
        self._pcache: SqliteCache | None = None
        backend = os.getenv("EAN_CACHE_BACKEND", "sqlite").strip().lower()
        if backend == "sqlite":
            default_path = Path(__file__).resolve().parent.parent / "data" / "cache.db"
            cache_path = os.getenv("EAN_CACHE_PATH", str(default_path))
            if cache_path != ":memory:":
                Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            self._pcache = SqliteCache(cache_path, ttl=self.cache_ttl)

        # Cache do token do GTIN obtido via auto-login: (token, expira_em_epoch).
        # Renovado sob demanda (expirou) ou ao receber 401 da API.
        self._gtin_token_cache: tuple[str, float] | None = None
        self._gtin_lock = threading.Lock()

        # Cache das imagens do GTIN (servidas pelo proxy do Flask, já que a URL
        # original exige Bearer token): {ean: ((bytes, content_type) | None, expira)}.
        # O valor None marca "sem foto real" (placeholder) já verificado.
        self._gtin_img_cache: dict[str, tuple[tuple[bytes, str] | None, float]] = {}

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def get_product(self, ean: str, providers: list[str] | None = None) -> dict:
        """
        Consulta um produto pelo EAN e devolve os dados já formatados.

        `providers` permite filtrar a fonte por consulta (ex.: ["gtin"] busca
        só no GTIN). Quando None, usa a cascata configurada no ambiente.

        Levanta InvalidEANError, ProductNotFoundError ou APIUnavailableError.
        """
        ean = self.normalize_ean(ean)

        if not self.is_valid_ean(ean):
            raise InvalidEANError(f"Código EAN inválido: {ean!r}")

        active = [p.strip().lower() for p in (providers or self.providers) if p.strip()]
        if not active:
            active = self.providers

        # Chave de cache inclui as fontes ativas: resultado do "só GTIN" não
        # pode colidir com o da cascata para o mesmo EAN.
        cache_key = f"{ean}|{','.join(active)}"

        # 1) Tenta o cache primeiro.
        cached = self._cache_get(cache_key)
        if cached is not None:
            # Marca a origem para o front-end saber que veio do cache.
            return {**cached, "from_cache": True}

        # 2) Consulta os provedores (em cascata, ou só o selecionado).
        product = self._fetch_with_fallback(ean, active)

        # 3) Guarda no cache e retorna.
        self._cache_set(cache_key, product)
        return {**product, "from_cache": False}

    def _fetch_one(self, provider: str, ean: str, base_url: str) -> dict:
        """Despacha a consulta para o provedor certo."""
        if provider == "cosmos":
            return self._fetch_cosmos(ean, base_url)
        if provider == "ean-db":
            return self._fetch_ean_db(ean, base_url)
        if provider == "gtin":
            return self._fetch_gtin(ean, base_url)
        if provider == "ean-search":
            return self._fetch_ean_search(ean, base_url)
        if provider == "upcitemdb":
            return self._fetch_upcitemdb(ean, base_url)
        return self._fetch_openfoodfacts(ean, base_url)

    def _fetch_with_fallback(self, ean: str, providers: list[str] | None = None) -> dict:
        """
        Percorre os provedores (parâmetro ou os configurados) na ordem definida.

        - Se um provedor não encontra o produto, tenta o próximo.
        - Se um provedor está fora do ar, também tenta o próximo.
        - Se um provedor acha o produto mas SEM imagem, guarda como reserva e
          continua: prefere um resultado posterior que tenha imagem (importante
          para remédios, em que nem toda base tem foto).
        - Só falha quando todos falham: prioriza 'não encontrado' sobre
          'indisponível' na mensagem final.
        """
        last_unavailable: APIUnavailableError | None = None
        any_not_found = False
        imageless: dict | None = None  # 1º resultado achado, porém sem foto

        active = providers or self.providers
        logger.info("cascata para %s: %s", ean, ",".join(active))
        for index, provider in enumerate(active):
            base_url = self._base_for(provider, is_first=index == 0)
            try:
                product = self._fetch_one(provider, ean, base_url)
            except ProductNotFoundError:
                logger.info("  [%s] nao encontrou %s", provider, ean)
                any_not_found = True
                continue
            except APIUnavailableError as exc:
                logger.warning("  [%s] indisponivel para %s: %s", provider, ean, exc)
                last_unavailable = exc
                continue

            # Achou com imagem.
            if product.get("image"):
                # Se um provedor anterior (mais preferido) já trouxe os dados mas
                # sem foto, mantém o nome/descrição dele e só herda a imagem deste
                # — ex.: Cosmos dá o nome BR correto, Open Food Facts dá a foto.
                if imageless is not None and self.merge_image:
                    logger.info(
                        "  [%s] tem imagem -> merge na ficha de %s",
                        provider, imageless.get("source"),
                    )
                    merged = {**imageless, "image": product["image"]}
                    merged["image_source"] = product.get("source")
                    return merged
                logger.info("  [%s] ACHOU com imagem -> usando (%s)", provider, product.get("name", "")[:40])
                return product
            # Achou sem imagem -> guarda e segue tentando os próximos.
            logger.info("  [%s] achou SEM imagem, guarda e continua (%s)", provider, product.get("name", "")[:40])
            if imageless is None:
                imageless = product

        # Nenhum provedor trouxe imagem; usa o primeiro achado (sem foto) e,
        # se houver searcher configurado, tenta achar uma imagem pelo nome.
        if imageless is not None:
            return self._with_image_fallback(imageless)

        if any_not_found:
            raise ProductNotFoundError(f"Produto não encontrado para o EAN {ean}.")
        raise last_unavailable or APIUnavailableError("Nenhum provedor respondeu.")

    def _with_image_fallback(self, product: dict) -> dict:
        """
        Tenta preencher a imagem de um produto sem foto via busca por nome.

        Monta a query com marca + nome (melhora a precisão) e devolve uma cópia
        com 'image' e 'image_source' preenchidos quando encontra algo.
        """
        if self.image_searcher is None or product.get("image"):
            return product

        name = product.get("name") or ""
        if not name or name == "Produto sem nome":
            return product
        brand = (product.get("extra") or {}).get("Marca") or ""
        query = f"{brand} {name}".strip()

        logger.info("  [image-search] buscando foto de '%s'", query[:60])
        url = self.image_searcher.search(query)
        if not url:
            return product

        logger.info("  [image-search] foto encontrada via %s", self.image_searcher.label)
        return {**product, "image": url, "image_source": self.image_searcher.label}

    def _base_for(self, provider: str, is_first: bool) -> str:
        """Resolve a URL base de um provedor (env específica > override global > default)."""
        env_name = self._PROVIDER_BASE_ENV.get(provider)
        if env_name and os.getenv(env_name):
            return os.getenv(env_name)
        if is_first and self.base_url_override:
            return self.base_url_override
        return self._DEFAULT_BASE_URLS.get(provider, "")

    def _token_for(self, provider: str) -> str | None:
        """
        Token de um provedor: env específica (ex.: EAN_DB_TOKEN) tem prioridade;
        caso ausente, usa o EAN_API_TOKEN global. Permite encadear vários
        provedores autenticados ao mesmo tempo.
        """
        env_name = self._PROVIDER_TOKEN_ENV.get(provider)
        if env_name and os.getenv(env_name):
            return os.getenv(env_name)
        return self.token

    # ------------------------------------------------------------------ #
    # Validação de EAN
    # ------------------------------------------------------------------ #
    @staticmethod
    def normalize_ean(ean: str) -> str:
        """Remove espaços e caracteres não numéricos das bordas."""
        return (ean or "").strip()

    @staticmethod
    def is_valid_ean(ean: str) -> bool:
        """
        Valida EAN-8, UPC-A (12), EAN-13 e GTIN-14 pelo dígito verificador.

        O algoritmo do dígito verificador é o mesmo (módulo 10) para todos.
        """
        if not ean or not ean.isdigit():
            return False
        if len(ean) not in (8, 12, 13, 14):
            return False

        digits = [int(d) for d in ean]
        check = digits[-1]
        body = digits[:-1]

        # Da direita para a esquerda, pesos alternam 3 e 1.
        total = 0
        for i, d in enumerate(reversed(body)):
            total += d * (3 if i % 2 == 0 else 1)

        expected = (10 - (total % 10)) % 10
        return expected == check

    # ------------------------------------------------------------------ #
    # Provedores
    # ------------------------------------------------------------------ #
    def _fetch_cosmos(self, ean: str, base_url: str) -> dict:
        """
        Consulta a Bluesoft Cosmos (cobertura BR, inclui farmácia).

        Requer token gratuito (COSMOS_TOKEN ou EAN_API_TOKEN; cadastro em
        https://cosmos.bluesoft.com.br). Enviado no header X-Cosmos-Token.
        """
        token = self._token_for("cosmos")
        if not token:
            raise APIUnavailableError(
                "Token não configurado para o provedor 'cosmos' "
                "(defina COSMOS_TOKEN ou EAN_API_TOKEN)."
            )

        url = f"{base_url}/{ean}.json"
        data = self._http_get_json(
            url,
            headers={
                "X-Cosmos-Token": token,
                "Content-Type": "application/json",
            },
        )

        if not data:
            raise ProductNotFoundError(f"Produto não encontrado para o EAN {ean}.")
        # Cosmos devolve 'message' quando há erro. Distingue "não encontrado"
        # (404) de indisponibilidade real (limite, auth) pela mensagem.
        msg = str(data.get("message") or "")
        if msg and not data.get("description"):
            low = msg.lower()
            if "não existe" in low or "nao existe" in low or "not found" in low:
                raise ProductNotFoundError(f"Produto não encontrado para o EAN {ean}.")
            raise APIUnavailableError(msg)

        return self._format_cosmos(ean, data)

    def _fetch_ean_db(self, ean: str, base_url: str) -> dict:
        """
        Consulta a EAN-DB (https://ean-db.com) — cobertura internacional ampla.

        Requer token JWT gratuito (EAN_DB_TOKEN ou EAN_API_TOKEN), enviado
        no header Authorization: Bearer <token>.
        """
        token = self._token_for("ean-db")
        if not token:
            raise APIUnavailableError(
                "Token não configurado para o provedor 'ean-db' "
                "(defina EAN_DB_TOKEN ou EAN_API_TOKEN)."
            )

        url = f"{base_url}/{ean}"
        data = self._http_get_json(
            url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
        )

        product = (data or {}).get("product")
        if not product:
            raise ProductNotFoundError(f"Produto não encontrado para o EAN {ean}.")

        return self._format_ean_db(ean, product)

    def _fetch_gtin(self, ean: str, base_url: str) -> dict:
        """
        Consulta a RSC Sistemas GTIN (https://gtin.rscsistemas.com.br) — base BR.

        Autenticação via Bearer token. O token expira em ~1h, então o serviço
        faz **auto-login** quando há credenciais (GTIN_USER/GTIN_PASSWORD):
        renova o token sob demanda e refaz a consulta uma vez em caso de 401.
        Sem credenciais, usa o GTIN_TOKEN estático (renovação manual).

        O WAF do servidor exige User-Agent de navegador (enviamos UA do Chrome).
        Endpoint: /api/gtin/infor/{ean}. Plano grátis: 20 req/min.
        """
        token = self._gtin_get_token(base_url)
        if not token:
            raise APIUnavailableError(
                "Provedor 'gtin' sem credenciais: defina GTIN_USER + GTIN_PASSWORD "
                "(auto-login) ou um GTIN_TOKEN estático."
            )

        url = f"{base_url.rstrip('/')}/api/gtin/infor/{ean}"

        def _request(tok: str):
            return self._http_get_json(
                url,
                headers={
                    "User-Agent": self._BROWSER_UA,  # WAF bloqueia UA não-navegador
                    "Accept": "application/json",
                    "Authorization": f"Bearer {tok}",
                },
            )

        try:
            data = _request(token)
        except APIUnavailableError as exc:
            # 401 = token expirado/inválido. Se temos credenciais, renova e
            # tenta de novo uma única vez (evita loop de re-login).
            if self._gtin_credentials() and "401" in str(exc):
                token = self._gtin_get_token(base_url, force=True)
                data = _request(token)
            else:
                raise

        # 404 devolve {"mensagem": "Produto não encontrado..."} (sem 'nome').
        if not data or not data.get("nome"):
            raise ProductNotFoundError(f"Produto não encontrado para o EAN {ean}.")

        # Verifica se há foto real (a URL é protegida e pode ser só placeholder).
        # O resultado fica em cache e é reaproveitado pelo proxy /img/gtin/<ean>.
        has_image = data.get("link_foto") and self._gtin_load_image(ean, base_url, token) is not None
        return self._format_gtin(ean, data, has_image=bool(has_image))

    # ------------------------------------------------------------------ #
    # Auto-login do GTIN (RSC Sistemas)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _gtin_credentials() -> tuple[str, str] | None:
        """Lê usuário/senha do GTIN do ambiente; None se não configurados."""
        user = os.getenv("GTIN_USER") or os.getenv("GTIN_EMAIL")
        pwd = os.getenv("GTIN_PASSWORD") or os.getenv("GTIN_SENHA")
        return (user, pwd) if user and pwd else None

    def _gtin_get_token(self, base_url: str, force: bool = False) -> str | None:
        """
        Devolve um token válido para o GTIN.

        - Com credenciais (GTIN_USER/GTIN_PASSWORD): faz login no /oauth/token,
          guarda o token em cache (~55 min) e o reaproveita. `force=True`
          ignora o cache e renova (usado após um 401).
        - Sem credenciais: cai no token estático (GTIN_TOKEN/EAN_API_TOKEN).
        """
        creds = self._gtin_credentials()
        if not creds:
            return self._token_for("gtin")

        with self._gtin_lock:
            now = time.time()
            if not force and self._gtin_token_cache:
                cached_token, expires_at = self._gtin_token_cache
                if now < expires_at:
                    return cached_token

            token = self._gtin_login(base_url, *creds)
            # Token vale 1h; renova com folga para não usar perto do limite.
            self._gtin_token_cache = (token, now + 55 * 60)
            return token

    def _gtin_login(self, base_url: str, user: str, password: str) -> str:
        """
        Autentica em POST /oauth/token com HTTP Basic e devolve o token.

        Resposta esperada: {"token": "..."}.
        """
        basic = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        url = f"{base_url.rstrip('/')}/oauth/token"
        data = self._http_post_json(
            url,
            headers={
                "User-Agent": self._BROWSER_UA,
                "Accept": "application/json",
                "Authorization": f"Basic {basic}",
            },
        )
        logger.info("GTIN auto-login em %s (user=%s)", url, user)
        token = (data or {}).get("token")
        if not token:
            raise APIUnavailableError(
                "Login no GTIN falhou: a API não retornou um token "
                "(verifique GTIN_USER/GTIN_PASSWORD)."
            )
        logger.info("GTIN auto-login OK (token renovado)")
        return token

    # ------------------------------------------------------------------ #
    # Imagem do GTIN (proxy autenticado)
    # ------------------------------------------------------------------ #
    def get_gtin_image(self, ean: str) -> tuple[bytes, str] | None:
        """
        Devolve (bytes, content_type) da foto do produto no GTIN, ou None se
        não houver foto real. Usado pela rota /img/gtin/<ean> do Flask, já que
        a URL original do GTIN exige Authorization (o <img> não envia header).
        """
        ean = self.normalize_ean(ean)

        # Reaproveita o que já foi verificado na consulta do produto.
        cached = self._gtin_img_cache.get(ean)
        if cached is not None:
            result, expires_at = cached
            if not expires_at or time.time() < expires_at:
                return result

        base_url = self._base_for("gtin", is_first=False)
        token = self._gtin_get_token(base_url)
        if not token:
            return None
        return self._gtin_load_image(ean, base_url, token)

    def _gtin_load_image(self, ean: str, base_url: str, token: str) -> tuple[bytes, str] | None:
        """Baixa a imagem autenticada, descarta placeholder e guarda em cache."""
        url = f"{base_url.rstrip('/')}/api/gtin/img/{ean}"
        result: tuple[bytes, str] | None = None
        try:
            resp = requests.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": self._BROWSER_UA, "Authorization": f"Bearer {token}"},
            )
            ctype = resp.headers.get("content-type", "")
            if resp.status_code == 200 and ctype.startswith("image"):
                is_placeholder = (
                    len(resp.content) == self._GTIN_PLACEHOLDER_SIZE
                    and hashlib.md5(resp.content).hexdigest() == self._GTIN_PLACEHOLDER_MD5
                )
                if is_placeholder:
                    logger.info("  [gtin] imagem de %s e placeholder (sem foto real)", ean)
                else:
                    logger.info("  [gtin] imagem real de %s (%d bytes)", ean, len(resp.content))
                    result = (resp.content, ctype)
            else:
                logger.info("  [gtin] imagem de %s indisponivel (HTTP %s)", ean, resp.status_code)
        except requests.exceptions.RequestException as exc:
            logger.warning("  [gtin] falha ao buscar imagem de %s: %s", ean, exc)
            result = None

        expires_at = time.time() + self.cache_ttl if self.cache_ttl else 0
        self._gtin_img_cache[ean] = (result, expires_at)
        return result

    def _fetch_upcitemdb(self, ean: str, base_url: str) -> dict:
        """
        Consulta o UPCitemdb (endpoint trial, gratuito e sem token).

        Cobertura geral de produtos (não apenas alimentos). O endpoint trial
        é limitado a ~100 buscas/dia por IP.
        """
        data = self._http_get_json(base_url, params={"upc": ean})

        if not data:
            raise ProductNotFoundError(f"Produto não encontrado para o EAN {ean}.")

        code = data.get("code")
        if code == "TOO_MANY_REQUESTS":
            raise APIUnavailableError(
                "Limite diário de consultas do UPCitemdb atingido. Tente mais tarde."
            )
        items = data.get("items") or []
        if code != "OK" or not items:
            raise ProductNotFoundError(f"Produto não encontrado para o EAN {ean}.")

        return self._format_upcitemdb(ean, items[0])

    def _fetch_openfoodfacts(self, ean: str, base_url: str) -> dict:
        """Consulta o Open Food Facts (gratuito, sem token)."""
        url = f"{base_url}/{ean}.json"
        data = self._http_get_json(url)

        # status == 1 significa produto encontrado.
        if not data or data.get("status") != 1:
            raise ProductNotFoundError(f"Produto não encontrado para o EAN {ean}.")

        product = data.get("product", {}) or {}
        return self._format_openfoodfacts(ean, product)

    def _fetch_ean_search(self, ean: str, base_url: str) -> dict:
        """Consulta o EAN-Search (requer token: EAN_SEARCH_TOKEN ou EAN_API_TOKEN)."""
        token = self._token_for("ean-search")
        if not token:
            raise APIUnavailableError(
                "Token não configurado para o provedor 'ean-search' "
                "(defina EAN_SEARCH_TOKEN ou EAN_API_TOKEN)."
            )

        params = {
            "token": token,
            "op": "barcode-lookup",
            "format": "json",
            "ean": ean,
        }
        data = self._http_get_json(base_url, params=params)

        # A resposta é uma lista; vazia ou com 'error' = não encontrado.
        if not data or not isinstance(data, list) or "error" in data[0]:
            raise ProductNotFoundError(f"Produto não encontrado para o EAN {ean}.")

        return self._format_ean_search(ean, data[0])

    # ------------------------------------------------------------------ #
    # Formatação dos dados (saída padronizada)
    # ------------------------------------------------------------------ #
    @classmethod
    def _format_gtin(cls, ean: str, p: dict, has_image: bool = False) -> dict:
        """Converte a resposta da RSC GTIN no formato padrão da app."""
        extra = {
            "Marca": (p.get("marca") or "").strip() or None,
            "Categoria": p.get("categoria"),
            "País": p.get("pais"),
            "NCM": p.get("ncm"),
        }
        # "Desconhecido" da RSC não agrega — descarta.
        if (extra.get("Marca") or "").lower() == "desconhecido":
            extra["Marca"] = None
        extra = {k: v for k, v in extra.items() if v}

        return {
            "ean": ean,
            "name": p.get("nome") or "Produto sem nome",
            # Imagem servida pelo proxy do Flask (a URL original exige token).
            # Vazia quando o GTIN só tem o placeholder (sem foto real).
            "image": f"/img/gtin/{ean}" if has_image else "",
            "description": p.get("categoria") or p.get("nome") or "",
            "extra": extra,
            "source": "RSC GTIN",
        }

    @staticmethod
    def _format_ean_db(ean: str, p: dict) -> dict:
        """Converte a resposta da EAN-DB (v2) no formato padrão da app."""

        def pick_title(obj: dict | None) -> str | None:
            # EAN-DB devolve títulos por idioma: prioriza pt/en, senão o 1º.
            titles = (obj or {}).get("titles") or {}
            if not isinstance(titles, dict) or not titles:
                return None
            for lang in ("pt", "en"):
                if titles.get(lang):
                    return titles[lang]
            return next(iter(titles.values()), None)

        name = pick_title(p) or "Produto sem nome"
        images = p.get("images") or []
        image = images[0].get("url", "") if images and isinstance(images[0], dict) else ""

        categories = p.get("categories") or []
        category = pick_title(categories[0]) if categories else None
        manufacturer = pick_title(p.get("manufacturer"))

        extra = {
            "Fabricante": manufacturer,
            "Categoria": category,
        }
        extra = {k: v for k, v in extra.items() if v}

        return {
            "ean": ean,
            "name": name,
            "image": image,
            "description": category or name,
            "extra": extra,
            "source": "EAN-DB",
        }

    @staticmethod
    def _format_cosmos(ean: str, p: dict) -> dict:
        """Converte a resposta da Bluesoft Cosmos no formato padrão da app."""
        brand = (p.get("brand") or {}).get("name") if isinstance(p.get("brand"), dict) else None
        ncm = (p.get("ncm") or {}).get("description") if isinstance(p.get("ncm"), dict) else None
        gpc = (p.get("gpc") or {}).get("description") if isinstance(p.get("gpc"), dict) else None

        extra = {
            "Marca": brand,
            "Categoria": gpc,
            "NCM": ncm,
            "Preço médio": (f"R$ {p['avg_price']:.2f}" if p.get("avg_price") else None),
        }
        extra = {k: v for k, v in extra.items() if v}

        return {
            "ean": ean,
            "name": p.get("description") or "Produto sem nome",
            "image": p.get("thumbnail") or "",
            "description": gpc or p.get("description") or "",
            "extra": extra,
            "source": "Bluesoft Cosmos",
        }

    @staticmethod
    def _format_upcitemdb(ean: str, p: dict) -> dict:
        """Converte a resposta do UPCitemdb no formato padrão da app."""
        images = p.get("images") or []
        extra = {
            "Marca": p.get("brand"),
            "Categoria": p.get("category"),
            "Modelo": p.get("model"),
            "Cor": p.get("color"),
            "Fabricante": p.get("manufacturer"),
        }
        extra = {k: v for k, v in extra.items() if v}

        return {
            "ean": ean,
            "name": p.get("title") or "Produto sem nome",
            "image": images[0] if images else "",
            "description": p.get("description") or p.get("category") or "",
            "extra": extra,
            "source": "UPCitemdb",
        }

    @staticmethod
    def _format_openfoodfacts(ean: str, p: dict) -> dict:
        """Converte a resposta do Open Food Facts no formato padrão da app."""
        name = (
            p.get("product_name")
            or p.get("product_name_pt")
            or p.get("generic_name")
            or "Produto sem nome"
        )
        image = (
            p.get("image_front_url")
            or p.get("image_url")
            or p.get("image_front_small_url")
            or ""
        )
        description = p.get("generic_name") or p.get("categories") or ""

        # Informações extras úteis exibidas no card.
        extra = {
            "Marca": p.get("brands"),
            "Quantidade": p.get("quantity"),
            "Categorias": p.get("categories"),
            "País de origem": p.get("countries"),
            "Nutri-Score": (p.get("nutriscore_grade") or "").upper() or None,
        }
        extra = {k: v for k, v in extra.items() if v}

        return {
            "ean": ean,
            "name": name,
            "image": image,
            "description": description,
            "extra": extra,
            "source": "Open Food Facts",
        }

    @staticmethod
    def _format_ean_search(ean: str, p: dict) -> dict:
        """Converte a resposta do EAN-Search no formato padrão da app."""
        name = p.get("name") or "Produto sem nome"
        extra = {
            "Categoria": p.get("categoryName"),
            "Emissor": p.get("issuingCountry"),
        }
        extra = {k: v for k, v in extra.items() if v}

        return {
            "ean": ean,
            "name": name,
            "image": p.get("image", ""),
            "description": p.get("name", ""),
            "extra": extra,
            "source": "EAN-Search",
        }

    # ------------------------------------------------------------------ #
    # HTTP helper
    # ------------------------------------------------------------------ #
    def _http_get_json(self, url: str, params: dict | None = None, headers: dict | None = None):
        """Faz GET, converte para JSON e traduz falhas em APIUnavailableError."""
        request_headers = {"User-Agent": "EAN-Pictures-App/1.0 (Flask demo)"}
        if headers:
            request_headers.update(headers)
        # Loga só a URL (sem params) — query string pode conter token.
        logger.debug("GET %s", url)
        try:
            resp = requests.get(
                url,
                params=params,
                timeout=self.timeout,
                headers=request_headers,
            )
            logger.debug("GET %s -> HTTP %s (%d bytes)", url, resp.status_code, len(resp.content))
            # 404 = produto inexistente na base; devolvemos o corpo (quando JSON)
            # para o provedor decidir entre "não encontrado" e "indisponível".
            if resp.status_code == 404:
                try:
                    return resp.json()
                except ValueError:
                    return None
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout as exc:
            raise APIUnavailableError("Tempo limite excedido ao consultar a API.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise APIUnavailableError("Não foi possível conectar à API.") from exc
        except requests.exceptions.HTTPError as exc:
            # Usa só o status; a str do HTTPError inclui a URL completa,
            # que pode conter o token em query string (vazamento de credencial).
            status = getattr(exc.response, "status_code", "desconhecido")
            raise APIUnavailableError(f"A API retornou erro HTTP {status}.") from exc
        except ValueError as exc:  # JSON inválido
            raise APIUnavailableError("Resposta inválida da API (JSON malformado).") from exc

    def _http_post_json(self, url: str, headers: dict | None = None, json_body: dict | None = None):
        """POST + JSON, com a mesma tradução de falhas do _http_get_json."""
        request_headers = {"User-Agent": "EAN-Pictures-App/1.0 (Flask demo)"}
        if headers:
            request_headers.update(headers)
        try:
            resp = requests.post(url, json=json_body, timeout=self.timeout, headers=request_headers)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout as exc:
            raise APIUnavailableError("Tempo limite excedido ao autenticar na API.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise APIUnavailableError("Não foi possível conectar à API.") from exc
        except requests.exceptions.HTTPError as exc:
            status = getattr(exc.response, "status_code", "desconhecido")
            raise APIUnavailableError(f"A API retornou erro HTTP {status}.") from exc
        except ValueError as exc:  # JSON inválido
            raise APIUnavailableError("Resposta inválida da API (JSON malformado).") from exc

    # ------------------------------------------------------------------ #
    # Cache (thread-safe)
    # ------------------------------------------------------------------ #
    def _cache_get(self, ean: str) -> dict | None:
        with self._lock:
            entry = self._cache.get(ean)
            if entry is not None:
                product, expires_at = entry
                # expires_at == 0 significa "sem expiração".
                if expires_at and time.time() > expires_at:
                    del self._cache[ean]  # entrada expirada
                else:
                    return product

        # Miss no L1: tenta o cache persistente (L2) e promove para o L1.
        if self._pcache is not None:
            product = self._pcache.get(ean)
            if product is not None:
                expires_at = time.time() + self.cache_ttl if self.cache_ttl else 0
                with self._lock:
                    self._cache[ean] = (product, expires_at)
                return product
        return None

    def _cache_set(self, ean: str, product: dict) -> None:
        expires_at = time.time() + self.cache_ttl if self.cache_ttl else 0
        with self._lock:
            self._cache[ean] = (product, expires_at)
        if self._pcache is not None:
            self._pcache.set(ean, product)

    def clear_cache(self) -> None:
        """Limpa o cache em memória e o persistente (útil para testes)."""
        with self._lock:
            self._cache.clear()
        if self._pcache is not None:
            self._pcache.clear()
