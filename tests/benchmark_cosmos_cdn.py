"""
Benchmark direto das imagens da CDN Bluesoft Cosmos.

Este script e independente de tests/benchmark.py: extrai EANs de um PDF,
monta https://cdn-cosmos.bluesoft.com.br/products/{ean} e valida a resposta
real da CDN sem consultar a API autenticada da Cosmos.

Uso:
    python tests/benchmark_cosmos_cdn.py --pdf produtos.pdf
    python tests/benchmark_cosmos_cdn.py --pdf novos_produtos.pdf -n 20
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services import build_cosmos_product_image_url  # noqa: E402
from services.ean_service import EANPicturesService  # noqa: E402
from services.batch import (  # noqa: E402
    extract_eans_from_pdf,
)
from tests.sample_eans import SOURCES, all_eans  # noqa: E402

REPORTS_DIR = ROOT / "reports"
LOGS_DIR = ROOT / "logs"
DEFAULT_REPORT = REPORTS_DIR / "cosmos-cdn.md"
USER_AGENT = "EAN-Pictures-CDN-Benchmark/1.0"

log = logging.getLogger("benchmark_cosmos_cdn")


def detect_image_type(content: bytes) -> str:
    """Identifica formatos comuns de imagem pela assinatura binaria."""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"BM"):
        return "image/bmp"
    return ""


def setup_logging(debug: bool) -> Path:
    """Configura log no console e em arquivo proprio deste benchmark."""
    LOGS_DIR.mkdir(exist_ok=True)
    log_path = LOGS_DIR / f"benchmark_cosmos_cdn_{datetime.now():%Y-%m-%d_%H%M%S}.log"

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    console.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s | %(message)s", "%H:%M:%S")
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s | %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
    )

    log.setLevel(logging.DEBUG)
    log.handlers = [console, file_handler]
    log.propagate = False
    return log_path


def load_pdf_eans(pdf_path: Path) -> list[str]:
    """Carrega somente EANs validos e unicos do PDF."""
    return extract_eans_from_pdf(pdf_path.read_bytes())


def check_cdn_image(
    ean: str,
    timeout: float = 10,
    fetch: Callable[..., object] = requests.get,
) -> dict:
    """Consulta uma URL da CDN e classifica se ela contem uma imagem utilizavel."""
    url = build_cosmos_product_image_url(ean)
    started = time.perf_counter()

    try:
        response = fetch(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        status_code = int(response.status_code)
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].lower()
        content = response.content or b""
        detected_type = detect_image_type(content)
        is_image = bool(content) and (
            content_type.startswith("image/") or bool(detected_type)
        )

        if status_code == 200 and is_image:
            status = "OK"
            error = ""
        elif status_code == 404:
            status = "NOT_FOUND"
            error = "Imagem nao encontrada."
        elif status_code == 200:
            status = "INVALID_CONTENT"
            error = f"Conteudo inesperado: {content_type or 'sem Content-Type'}."
        else:
            status = "HTTP_ERROR"
            error = f"HTTP {status_code}."

        return {
            "ean": ean,
            "url": url,
            "status": status,
            "status_code": status_code,
            "content_type": content_type,
            "detected_type": detected_type,
            "size_bytes": len(content),
            "latency_ms": latency_ms,
            "error": error,
        }
    except requests.RequestException as exc:
        return {
            "ean": ean,
            "url": url,
            "status": "REQUEST_ERROR",
            "status_code": 0,
            "content_type": "",
            "detected_type": "",
            "size_bytes": 0,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }


def run_benchmark(
    eans: list[str],
    timeout: float = 10,
    workers: int = 8,
    fetch: Callable[..., object] = requests.get,
) -> list[dict]:
    """Testa as URLs em paralelo e preserva a ordem original dos EANs."""
    if not eans:
        return []

    total = len(eans)
    max_workers = max(1, min(workers, total))

    def check(ean: str) -> dict:
        result = check_cdn_image(ean, timeout=timeout, fetch=fetch)
        log.info(
            "%s | %s | HTTP %s | %d bytes | %d ms",
            ean,
            result["status"],
            result["status_code"] or "-",
            result["size_bytes"],
            result["latency_ms"],
        )
        return result

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(check, eans))


def summarize(results: list[dict]) -> dict:
    """Calcula cobertura e latencia das imagens confirmadas."""
    total = len(results)
    available = sum(1 for result in results if result["status"] == "OK")
    ok_latencies = [
        result["latency_ms"] for result in results if result["status"] == "OK"
    ]
    return {
        "total": total,
        "available": available,
        "missing": total - available,
        "coverage": round(100 * available / total, 1) if total else 0,
        "avg_latency_ms": (
            round(sum(ok_latencies) / len(ok_latencies)) if ok_latencies else 0
        ),
        "total_bytes": sum(
            result["size_bytes"] for result in results if result["status"] == "OK"
        ),
    }


def write_report(source_label: str, results: list[dict], output_path: Path) -> None:
    """Grava um relatorio Markdown sem alterar os relatorios do benchmark antigo."""
    summary = summarize(results)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Benchmark direto - CDN Bluesoft Cosmos",
        "",
        f"_Gerado em {datetime.now():%d/%m/%Y %H:%M} por "
        "`tests/benchmark_cosmos_cdn.py`._",
        "",
        f"Fonte: `{source_label}`",
        "",
        "## Resumo",
        "",
        f"- **EANs testados:** {summary['total']}",
        f"- **Imagens disponiveis:** {summary['available']}/{summary['total']} "
        f"(**{summary['coverage']}%**)",
        f"- **Sem imagem valida:** {summary['missing']}",
        f"- **Latencia media dos sucessos:** {summary['avg_latency_ms']} ms",
        f"- **Bytes totais das imagens:** {summary['total_bytes']}",
        "",
        "Uma imagem conta como disponivel quando a resposta tem HTTP 200, corpo "
        "nao vazio e `Content-Type: image/*` ou assinatura binaria reconhecida.",
        "",
        "## Detalhe por EAN",
        "",
        "| EAN | Status | HTTP | Tipo | Tamanho | Latencia | URL |",
        "|-----|--------|------|------|---------|----------|-----|",
    ]

    for result in results:
        lines.append(
            f"| {result['ean']} | {result['status']} | "
            f"{result['status_code'] or '-'} | "
            f"{result['content_type'] or result['detected_type'] or '-'} | "
            f"{result['size_bytes']} bytes | {result['latency_ms']} ms | "
            f"[abrir]({result['url']}) |"
        )

    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Testa diretamente as imagens da CDN Bluesoft Cosmos."
    )
    parser.add_argument(
        "--pdf",
        default="produtos.pdf",
        metavar="ARQ",
        help="PDF de onde extrair os EANs (padrao: produtos.pdf)",
    )
    parser.add_argument(
        "--source",
        choices=sorted(SOURCES),
        metavar="FONTE",
        help="usa uma lista curada de EANs em vez do PDF (ex.: globo)",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        metavar="N",
        help="limita aos N primeiros EANs",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        metavar="N",
        help="quantidade de requisicoes paralelas (padrao: 8)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10,
        metavar="S",
        help="timeout de cada requisicao em segundos (padrao: 10)",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_REPORT),
        metavar="ARQ",
        help="arquivo Markdown de saida (padrao: reports/cosmos-cdn.md)",
    )
    parser.add_argument("--debug", action="store_true", help="exibe logs detalhados")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log_path = setup_logging(args.debug)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path

    if args.source:
        # Lista curada (ex.: drogaria-globo): filtra so os EANs com digito valido.
        source_label = f"{args.source} (lista curada)"
        eans = [
            ean for ean in all_eans(args.source)
            if EANPicturesService.is_valid_ean(ean)
        ]
    else:
        pdf_path = Path(args.pdf)
        if not pdf_path.is_absolute():
            pdf_path = ROOT / pdf_path
        if not pdf_path.is_file():
            log.error("PDF nao encontrado: %s", pdf_path)
            return 2
        source_label = pdf_path.name
        eans = load_pdf_eans(pdf_path)

    if args.limit is not None:
        eans = eans[: max(0, args.limit)]
    if not eans:
        log.error("Nenhum EAN valido encontrado em %s.", source_label)
        return 1

    log.info(
        "Testando %d EANs de %s com %d workers.",
        len(eans),
        source_label,
        max(1, args.workers),
    )
    results = run_benchmark(
        eans,
        timeout=max(0.1, args.timeout),
        workers=max(1, args.workers),
    )
    write_report(source_label, results, output_path)

    summary = summarize(results)
    log.info(
        "Fim: %d/%d imagens disponiveis (%.1f%%).",
        summary["available"],
        summary["total"],
        summary["coverage"],
    )
    log.info("Relatorio: %s", output_path)
    log.info("Log: %s", log_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
