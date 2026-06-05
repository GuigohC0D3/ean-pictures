"""
Aplicação Flask — EAN Pictures.

Rotas:
    GET  /                      -> página principal (busca por EAN)
    POST /buscar                -> consulta usada pelo front-end (JSON)
    GET  /api/product/<ean>     -> endpoint REST público
    GET  /api/history           -> histórico das últimas consultas
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from datetime import datetime
from functools import wraps
from pathlib import Path
from threading import Lock

from flask import Flask, Response, jsonify, render_template, request

# Carrega variáveis do .env (se existir) antes de instanciar o service.
# python-dotenv é opcional: se não estiver instalado, segue só com o ambiente.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:
    pass

from services import (
    EANPicturesService,
    InvalidEANError,
    ProductNotFoundError,
    APIUnavailableError,
)

# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
HISTORY_FILE = DATA_DIR / "history.json"
HISTORY_LIMIT = 10

# Rate limit do endpoint REST: N requisições por janela (segundos), por IP.
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "30"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

app = Flask(__name__)
service = EANPicturesService()

# Lock para escrita concorrente no arquivo de histórico.
_history_lock = Lock()


# --------------------------------------------------------------------------- #
# Rate limiting (em memória, janela deslizante por IP)
# --------------------------------------------------------------------------- #
_rate_hits: dict[str, deque] = defaultdict(deque)
_rate_lock = Lock()


def _client_ip() -> str:
    """IP do cliente, respeitando proxy reverso (X-Forwarded-For)."""
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() if fwd else (request.remote_addr or "unknown")


def rate_limited(func):
    """
    Decorator de rate limit por IP usando janela deslizante.

    Permite RATE_LIMIT_MAX requisições a cada RATE_LIMIT_WINDOW segundos.
    Responde 429 (com Retry-After) ao exceder.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        ip = _client_ip()
        now = time.time()
        with _rate_lock:
            hits = _rate_hits[ip]
            # Descarta marcações fora da janela.
            while hits and now - hits[0] > RATE_LIMIT_WINDOW:
                hits.popleft()
            if len(hits) >= RATE_LIMIT_MAX:
                retry = int(RATE_LIMIT_WINDOW - (now - hits[0])) + 1
                resp = jsonify(
                    {
                        "error": "Muitas requisições. Tente novamente em instantes.",
                        "code": "rate_limited",
                    }
                )
                resp.status_code = 429
                resp.headers["Retry-After"] = str(retry)
                return resp
            hits.append(now)
        return func(*args, **kwargs)

    return wrapper


# --------------------------------------------------------------------------- #
# Histórico (persistido em JSON)
# --------------------------------------------------------------------------- #
def _ensure_history_file() -> None:
    """Garante que data/history.json exista."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("[]", encoding="utf-8")


def load_history() -> list[dict]:
    """Lê o histórico do disco; devolve lista vazia em caso de erro."""
    _ensure_history_file()
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def add_to_history(product: dict) -> None:
    """
    Adiciona um produto ao topo do histórico, mantém só os últimos N
    e evita duplicar o mesmo EAN consecutivamente.
    """
    with _history_lock:
        history = load_history()
        history = [h for h in history if h.get("ean") != product.get("ean")]

        history.insert(
            0,
            {
                "ean": product.get("ean"),
                "name": product.get("name"),
                "image": product.get("image"),
                "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
            },
        )
        history = history[:HISTORY_LIMIT]
        HISTORY_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def clear_history() -> None:
    """Esvazia o histórico persistido."""
    with _history_lock:
        HISTORY_FILE.write_text("[]", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Função reutilizável de consulta + tratamento de erros
# --------------------------------------------------------------------------- #
# Fontes que o front pode selecionar (além de "auto" = cascata configurada).
KNOWN_PROVIDERS = {"cosmos", "ean-db", "gtin", "upcitemdb", "openfoodfacts", "ean-search"}


def consultar_produto(ean: str, provider: str | None = None) -> tuple[dict, int]:
    """
    Consulta o produto e devolve (payload, status_http).

    `provider` filtra a fonte (ex.: "gtin"); valores desconhecidos ou "auto"
    caem na cascata padrão. Centraliza o tratamento de exceções para ser
    reaproveitada tanto pela rota do front-end quanto pelo endpoint REST.
    """
    providers = [provider] if provider in KNOWN_PROVIDERS else None
    try:
        product = service.get_product(ean, providers=providers)
        # Só registra no histórico se não veio do cache (evita ruído).
        if not product.get("from_cache"):
            add_to_history(product)
        return {"ok": True, "product": product}, 200

    except InvalidEANError as exc:
        return {"ok": False, "error": str(exc), "code": "invalid_ean"}, 400
    except ProductNotFoundError as exc:
        return {"ok": False, "error": str(exc), "code": "not_found"}, 404
    except APIUnavailableError as exc:
        return {"ok": False, "error": str(exc), "code": "api_unavailable"}, 503


# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    """Renderiza a página principal com o histórico atual."""
    return render_template("index.html", history=load_history())


@app.route("/buscar", methods=["POST"])
def buscar():
    """Endpoint consumido pelo JavaScript do front-end."""
    payload = request.get_json(silent=True) or {}
    ean = str(payload.get("ean", "")).strip()
    provider = str(payload.get("provider", "")).strip().lower()
    result, status = consultar_produto(ean, provider)
    # Anexa o histórico atualizado para o front renderizar sem novo request.
    result["history"] = load_history()
    return jsonify(result), status


@app.route("/api/product/<ean>")
@rate_limited
def api_product(ean: str):
    """
    Endpoint REST público.

    Retorna o formato enxuto pedido na especificação:
        { "ean": "", "name": "", "image": "", "description": "" }
    """
    provider = request.args.get("provider", "").strip().lower()
    result, status = consultar_produto(ean, provider)

    if not result["ok"]:
        return jsonify({"error": result["error"], "code": result["code"]}), status

    p = result["product"]
    return jsonify(
        {
            "ean": p.get("ean", ""),
            "name": p.get("name", ""),
            "image": p.get("image", ""),
            "description": p.get("description", ""),
        }
    ), 200


@app.route("/img/gtin/<ean>")
def gtin_image(ean: str):
    """
    Proxy autenticado da imagem do GTIN.

    A URL original do GTIN exige Bearer token, que o <img> do navegador não
    envia. Aqui buscamos a imagem com o token (do serviço) e a repassamos.
    404 quando não há foto real (o front cai no placeholder "Sem imagem").
    Sem @rate_limited de propósito: thumbnails do histórico fariam estourar.
    """
    img = service.get_gtin_image(ean)
    if not img:
        return jsonify({"error": "Imagem indisponível.", "code": "no_image"}), 404
    content, ctype = img
    resp = Response(content, mimetype=ctype or "image/png")
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


@app.route("/api/history")
@rate_limited
def api_history():
    """Devolve as últimas consultas registradas."""
    return jsonify(load_history()), 200


@app.route("/api/history", methods=["DELETE"])
@rate_limited
def api_history_clear():
    """Limpa todo o histórico de consultas."""
    clear_history()
    return jsonify({"ok": True, "history": []}), 200


# --------------------------------------------------------------------------- #
# Bootstrap
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    _ensure_history_file()
    port = int(os.getenv("PORT", "5000"))
    # debug e host configuráveis por ambiente. Default seguro: debug desligado
    # (o debugger do Werkzeug permite RCE se exposto) e bind só em localhost.
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    host = os.getenv("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=debug)
