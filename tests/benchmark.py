"""
Benchmark de provedores de EAN — foco: melhor API geral (produto + imagem).

Para cada provedor, consulta a mesma lista de produtos POPULARES de várias
categorias (alimento, bebida, eletrônico, livro, etc.), mede latência, cobertura
e principalmente PRESENÇA DE IMAGEM, e gera:
  - reports/<provedor>.md  (detalhe por EAN)
  - reports/_RESUMO.md      (ranking por imagem + matriz por categoria)

Uso:
    python tests/benchmark.py

Métrica principal: "encontrado COM imagem" — é o que define a melhor API para
trabalhar (traz o produto e a foto corretos).
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Logger do benchmark (separado do "ean_service" do serviço).
log = logging.getLogger("benchmark")


def setup_logging(debug: bool) -> None:
    """
    Configura logs em tempo real no stdout E num arquivo em logs/, com timestamp.

    INFO (padrão): progresso por EAN, decisões de cascata, login, imagem.
    DEBUG (--debug): inclui cada requisição HTTP (GET url -> status, bytes).

    Cada execução grava um arquivo logs/benchmark_AAAA-MM-DD_HHMMSS.log
    (o arquivo guarda sempre DEBUG, independentemente do nível do console).
    """
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%H:%M:%S"))
    console.setLevel(logging.DEBUG if debug else logging.INFO)

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / f"benchmark_{datetime.now():%Y-%m-%d_%H%M%S}.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"))
    file_handler.setLevel(logging.DEBUG)

    for name in ("benchmark", "ean_service"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        lg.handlers = [console, file_handler]
        lg.propagate = False

    log.info("Log desta execução: %s", log_path.relative_to(ROOT))

# Carrega tokens do .env (se python-dotenv estiver instalado).
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ModuleNotFoundError:
    pass

from services.ean_service import (  # noqa: E402
    EANPicturesService,
    InvalidEANError,
    ProductNotFoundError,
    APIUnavailableError,
)

REPORTS_DIR = ROOT / "reports"

# Pausa entre requisições (segundos) para não tomar rate limit (HTTP 429).
DELAY_BETWEEN_CALLS = 1.2

PROVIDERS = ["gtin", "cosmos", "ean-db", "upcitemdb", "openfoodfacts", "ean-search"]

# Provedores que limitam POR MINUTO (free tier). Para eles, processamos os EANs
# em "páginas" (lotes) com uma pausa entre elas, deixando a janela do rate limit
# resetar — e tentamos de novo quando bate 429. (upcitemdb limita por DIA: pausar
# não ajuda, então fica de fora.)
RATE_LIMITED = {"cosmos", "gtin", "ean-search"}

# Padrões da paginação anti-429 (configuráveis por CLI).
PAGE_SIZE = 30        # itens por página (a "lista de 30")
PAGE_PAUSE = 60       # segundos de descanso entre páginas
RETRIES = 2           # tentativas extras quando um EAN toma 429
RETRY_WAIT = 60       # segundos de espera antes de cada retry

# Conjunto de teste: produtos populares e variados (foco: produto + imagem).
# (ean, descrição, categoria)
TEST_EANS: list[tuple[str, str, str]] = [
    ("3017620422003", "Nutella 400g", "Alimento"),
    ("5449000000996", "Coca-Cola lata 330ml", "Bebida"),
    ("8000500310427", "Kinder Bueno", "Alimento"),
    ("3046920022651", "Lindt Excellence 70%", "Alimento"),
    ("7891000100103", "Leite Moça 395g", "Alimento BR"),
    ("7891910000197", "Açúcar União 1kg", "Alimento BR"),
    ("7894900011517", "Coca-Cola 2L", "Bebida BR"),
    ("7891991010924", "Guaraná Antarctica 2L", "Bebida BR"),
    ("0885909950805", "Apple iPhone 6 64GB", "Eletrônico"),
    ("0194252818411", "Apple iPhone 12", "Eletrônico"),
    ("9780132350884", "Livro: Clean Code", "Livro"),
    ("9788535914849", "Livro: Companhia das Letras", "Livro BR"),
    ("7891150064386", "OMO Lavagem Perfeita", "Limpeza BR"),
    ("7896714269870", "Vit Neo A-Z 60cpr", "Farmácia BR"),
    ("7895858017392", "OsteoNutri 600mg 30cpr", "Farmácia BR"),
    ("7896090611607", "Sonrisal 2cpr efervescente", "Farmácia BR"),
    ("7895858017156", "Calman 20cpr", "Farmácia BR"),
    ("7892828002280", "Triade 1amp 3ml", "Farmácia BR"),
]


def load_pdf_eans(pdf_path: Path) -> list[tuple[str, str, str]]:
    """Extrai EANs (8/12/13/14 dígitos) do PDF. Requer pypdf."""
    try:
        import pypdf
    except ModuleNotFoundError:
        log.error("pypdf não instalado. Rode: pip install pypdf")
        sys.exit(1)
    reader = pypdf.PdfReader(str(pdf_path))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    seen: list[str] = []
    for code in re.findall(r"\b\d{8,14}\b", text):
        if len(code) in (8, 12, 13, 14) and code not in seen:
            seen.append(code)
    log.info("PDF %s: %d páginas, %d EANs únicos", pdf_path.name, len(reader.pages), len(seen))
    return [(e, f"PDF #{i + 1}", "PDF") for i, e in enumerate(seen)]


def luhn_gtin_valid(ean: str) -> bool:
    """Valida o dígito verificador do GTIN (mesma regra do service)."""
    if not ean.isdigit() or len(ean) not in (8, 12, 13, 14):
        return False
    digits = [int(d) for d in ean]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits[:-1])))
    return (10 - total % 10) % 10 == digits[-1]


def _call_with_retry(fn, retries: int, wait: float):
    """
    Executa fn(); se tomar 429 (rate limit), espera `wait`s e tenta de novo,
    até `retries` vezes. Outras falhas sobem na hora.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except APIUnavailableError as exc:
            if "429" in str(exc) and attempt < retries:
                attempt += 1
                log.warning("    ⏳ 429 (rate limit) — aguardando %ds e tentando de novo (%d/%d)",
                            wait, attempt, retries)
                time.sleep(wait)
                continue
            raise


def _pause_for_page(idx: int, paged: bool, page_size: int, page_pause: float, delay: float) -> None:
    """Entre páginas, descansa `page_pause`s; dentro da página, só o `delay` normal."""
    if not idx:
        return
    if paged and idx % page_size == 0:
        log.info("--- página de %d itens concluída; descansando %ds p/ o rate limit resetar ---",
                 page_size, page_pause)
        time.sleep(page_pause)
    elif delay:
        time.sleep(delay)


def run_provider(
    service: EANPicturesService,
    provider: str,
    eans: list[tuple[str, str, str]],
    delay: float,
    page_size: int = 0,
    page_pause: float = 0,
    retries: int = 0,
    retry_wait: float = 0,
) -> list[dict]:
    base_url = service._base_for(provider, is_first=False)
    total = len(eans)
    paged = page_size > 0 and provider in RATE_LIMITED
    extra = f" | páginas de {page_size} (pausa {page_pause:.0f}s)" if paged else ""
    log.info("=== provedor [%s] | %d EANs | delay %.1fs%s | base=%s ===",
             provider, total, delay, extra, base_url or "(default)")
    results = []
    for idx, (ean, label, category) in enumerate(eans):
        _pause_for_page(idx, paged, page_size, page_pause, delay)
        row: dict[str, object] = {"ean": ean, "label": label, "category": category}
        t0 = time.perf_counter()
        try:
            product = _call_with_retry(
                lambda: service._fetch_one(provider, ean, base_url), retries, retry_wait
            )
            row["status"] = "OK"
            row["name"] = product.get("name", "")
            row["has_image"] = bool(product.get("image"))
        except ProductNotFoundError:
            row["status"] = "NAO_ENCONTRADO"
            row["name"] = ""
            row["has_image"] = False
        except APIUnavailableError as exc:
            row["status"] = "INDISPONIVEL"
            row["name"] = str(exc)
            row["has_image"] = False
        row["latency_ms"] = round((time.perf_counter() - t0) * 1000)
        results.append(row)

        icon = {"OK": "✅", "NAO_ENCONTRADO": "❌", "INDISPONIVEL": "⚠️"}[row["status"]]
        img = "🖼️" if row["has_image"] else "  "
        detail = (row["name"] or "")[:45]
        log.info(
            "[%s] %3d/%d %-14s %s %s %4dms %s",
            provider, idx + 1, total, ean, icon, img, row["latency_ms"], detail,
        )
    found = sum(1 for r in results if r["status"] == "OK")
    with_img = sum(1 for r in results if r["has_image"])
    log.info("=== [%s] fim: achou %d/%d | com imagem %d ===", provider, found, total, with_img)
    return results


def needs_token(service: EANPicturesService, provider: str) -> bool:
    """Provedor autenticado sem token ESPECÍFICO -> não testável agora."""
    env_name = service._PROVIDER_TOKEN_ENV.get(provider)
    if not env_name:
        return False
    return not os.getenv(env_name)


def write_report(provider: str, results: list[dict] | None, skipped_reason: str | None):
    path = REPORTS_DIR / f"{provider}.md"
    lines = [f"# Relatório — `{provider}`", ""]
    lines.append(f"_Gerado em {datetime.now():%d/%m/%Y %H:%M} por `tests/benchmark.py`._")
    lines.append("")

    if skipped_reason:
        lines += [
            "## Status: ⏭️ Não testado",
            "",
            f"> {skipped_reason}",
            "",
            "Configure o token e rode `python tests/benchmark.py` novamente.",
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return

    assert results is not None
    total = len(results)
    found = sum(1 for r in results if r["status"] == "OK")
    with_img = sum(1 for r in results if r["has_image"])
    img_rate = round(100 * with_img / total)
    ok_lat = [r["latency_ms"] for r in results if r["status"] in ("OK", "NAO_ENCONTRADO")]
    avg_lat = round(sum(ok_lat) / len(ok_lat)) if ok_lat else 0
    rate_limited = sum(1 for r in results if "429" in (r["name"] or ""))
    auth_failed = sum(1 for r in results if "401" in (r["name"] or "") or "403" in (r["name"] or ""))

    lines += [
        "## Resumo",
        "",
        f"- **Encontrados:** {found}/{total}",
        f"- **Com imagem:** {with_img}/{total}  (**{img_rate}%**) ← métrica principal",
        f"- **Latência média:** {avg_lat} ms",
        "",
    ]
    if rate_limited:
        lines += [
            f"> ⚠️ **{rate_limited}/{total} consultas tomaram HTTP 429 (rate limit).** "
            "Os números estão subestimados; rode mais tarde para um resultado limpo.",
            "",
        ]
    if auth_failed:
        lines += [
            f"> 🔑 **{auth_failed}/{total} consultas retornaram HTTP 401/403.** "
            "Pode ser token inválido/expirado OU **cota/rate limit esgotado** "
            "(a RSC GTIN, p.ex., responde 403 ao estourar a cota). Verifique a "
            "chave e/ou aguarde a renovação da cota.",
            "",
        ]
    lines += [
        "## Detalhe por EAN",
        "",
        "| EAN | Produto | Categoria | Status | Imagem | Latência | Nome retornado |",
        "|-----|---------|-----------|--------|--------|----------|----------------|",
    ]
    icon = {"OK": "✅", "NAO_ENCONTRADO": "❌", "INDISPONIVEL": "⚠️"}
    for r in results:
        img = "🖼️ sim" if r["has_image"] else "—"
        name = (r["name"] or "")[:38]
        lines.append(
            f"| {r['ean']} | {r['label']} | {r['category']} | {icon[r['status']]} "
            f"{r['status']} | {img} | {r['latency_ms']} ms | {name} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_summary(tested: list[dict], skipped: list[dict], eans: list[tuple[str, str, str]]):
    path = REPORTS_DIR / "_RESUMO.md"
    total = len(eans)
    categories = sorted({c for _, _, c in eans})

    # Ranking pela métrica principal: % com imagem.
    ranked = sorted(tested, key=lambda s: s["with_img"], reverse=True)

    lines = [
        "# Resumo comparativo — melhor API (produto + imagem)",
        "",
        f"_Gerado em {datetime.now():%d/%m/%Y %H:%M}._",
        "",
        f"Conjunto: **{total} produtos populares** de várias categorias.",
        "**Métrica principal: % encontrado COM imagem** (traz produto e foto certos).",
        "",
        "## 🏆 Ranking por imagem",
        "",
        "| # | Provedor | Com imagem | Encontrados | Latência média | Observação |",
        "|---|----------|-----------|-------------|----------------|------------|",
    ]
    medal = {0: "🥇", 1: "🥈", 2: "🥉"}
    for i, s in enumerate(ranked):
        rate = round(100 * s["with_img"] / total)
        lines.append(
            f"| {medal.get(i, i + 1)} | `{s['provider']}` | "
            f"**{s['with_img']}/{total}** ({rate}%) | {s['found']}/{total} | "
            f"{s['avg_lat']} ms | {s.get('note', '')} |"
        )
    for s in skipped:
        lines.append(f"| – | `{s['provider']}` | — | — | — | ⏭️ {s['reason']} |")

    # Matriz por categoria: quantos COM imagem por provedor.
    lines += [
        "",
        "## Imagem por categoria",
        "",
        "Quantos produtos vieram **com imagem** em cada categoria (por provedor).",
        "",
        "| Provedor | " + " | ".join(categories) + " |",
        "|----------|" + "|".join(["---"] * len(categories)) + "|",
    ]
    cat_totals = {c: sum(1 for _, _, cc in eans if cc == c) for c in categories}
    for s in ranked:
        cells = []
        for c in categories:
            img = sum(1 for r in s["results"] if r["category"] == c and r["has_image"])
            cells.append(f"{img}/{cat_totals[c]}")
        lines.append(f"| `{s['provider']}` | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## Como ler",
        "",
        "- **Com imagem** é o que importa: o produto retornado traz foto utilizável.",
        "- A matriz por categoria mostra em quê cada API é forte.",
        "- Provedores ⏭️ exigem token válido e não entraram no ranking.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Modo CASCATA (get_product completo: cascata + merge + fallback de imagem)
# --------------------------------------------------------------------------- #
def _img_origin(row: dict, searcher_label: str | None) -> str | None:
    """Classifica de onde veio a imagem: provedor, merge (outro provedor) ou busca-nome."""
    if not row["has_image"]:
        return None
    src = row.get("image_source") or ""
    if not src:
        return "provedor"
    if searcher_label and src == searcher_label:
        return "busca-nome"
    return "merge"


def run_cascade(
    service: EANPicturesService,
    eans: list[tuple[str, str, str]],
    delay: float,
    page_size: int = 0,
    page_pause: float = 0,
    retries: int = 0,
    retry_wait: float = 0,
) -> list[dict]:
    """Roda a cascata completa (service.get_product) — o caminho que a app web usa."""
    total = len(eans)
    searcher = service.image_searcher.label if service.image_searcher else "off"
    # Pagina se a cascata inclui algum provedor que limita por minuto.
    paged = page_size > 0 and bool(set(service.providers) & RATE_LIMITED)
    extra = f" | páginas de {page_size} (pausa {page_pause:.0f}s)" if paged else ""
    log.info(
        "=== modo CASCATA | %d EANs | cascata=%s | fallback-imagem=%s%s ===",
        total, ",".join(service.providers), searcher, extra,
    )
    results = []
    for idx, (ean, label, category) in enumerate(eans):
        _pause_for_page(idx, paged, page_size, page_pause, delay)
        row: dict[str, object] = {"ean": ean, "label": label, "category": category}
        t0 = time.perf_counter()
        try:
            p = _call_with_retry(lambda: service.get_product(ean), retries, retry_wait)
            row.update(
                status="OK", name=p.get("name", ""), has_image=bool(p.get("image")),
                source=p.get("source", ""), image_source=p.get("image_source", "") or "",
            )
        except InvalidEANError:
            row.update(status="INVALIDO", name="", has_image=False, source="", image_source="")
        except ProductNotFoundError:
            row.update(status="NAO_ENCONTRADO", name="", has_image=False, source="", image_source="")
        except APIUnavailableError as exc:
            row.update(status="INDISPONIVEL", name=str(exc), has_image=False, source="", image_source="")
        row["latency_ms"] = round((time.perf_counter() - t0) * 1000)
        results.append(row)

        icon = {"OK": "✅", "NAO_ENCONTRADO": "❌", "INDISPONIVEL": "⚠️", "INVALIDO": "🚫"}[row["status"]]
        origin = _img_origin(row, service.image_searcher.label if service.image_searcher else None)
        img = {"provedor": "🖼️", "merge": "🔀", "busca-nome": "🔍"}.get(origin, "  ")
        log.info(
            "[cascata] %3d/%d %-14s %s %s %4dms %s",
            idx + 1, total, ean, icon, img, row["latency_ms"], (row["name"] or "")[:42],
        )
    found = sum(1 for r in results if r["status"] == "OK")
    with_img = sum(1 for r in results if r["has_image"])
    log.info("=== [cascata] fim: achou %d/%d | com imagem %d ===", found, total, with_img)
    return results


def write_cascade_report(
    service: EANPicturesService,
    results: list[dict],
    union_map: dict[str, bool] | None,
) -> None:
    """Gera reports/_cascata.md com cobertura de imagem e origem das fotos."""
    path = REPORTS_DIR / "_cascata.md"
    total = len(results)
    found = sum(1 for r in results if r["status"] == "OK")
    with_img = sum(1 for r in results if r["has_image"])
    rate = round(100 * with_img / total) if total else 0

    label = service.image_searcher.label if service.image_searcher else None
    origins = {"provedor": 0, "merge": 0, "busca-nome": 0}
    for r in results:
        o = _img_origin(r, label)
        if o:
            origins[o] += 1

    lines = [
        "# Cascata completa — produto + imagem (com merge e fallback)",
        "",
        f"_Gerado em {datetime.now():%d/%m/%Y %H:%M} por `tests/benchmark.py --mode cascade`._",
        "",
        f"Cascata: `{','.join(service.providers)}`  ·  "
        f"Fallback de imagem: `{label or 'desligado'}`",
        "",
        "## Resumo",
        "",
        f"- **Encontrados:** {found}/{total}",
        f"- **Com imagem:** {with_img}/{total}  (**{rate}%**) ← métrica principal",
        "",
        "### Origem da imagem",
        "",
        f"- 🖼️ Do próprio provedor: **{origins['provedor']}**",
        f"- 🔀 De outro provedor (merge): **{origins['merge']}**",
        f"- 🔍 Da busca por nome (fallback): **{origins['busca-nome']}**",
        "",
    ]

    # Comparação com o teto sem fallback (união dos provedores isolados).
    if union_map is not None:
        ceiling = sum(1 for r in results if union_map.get(r["ean"]))
        ceil_rate = round(100 * ceiling / total) if total else 0
        gain = with_img - ceiling
        lines += [
            "## Ganho sobre os provedores isolados",
            "",
            f"- **Teto sem fallback** (algum provedor isolado tinha foto): "
            f"{ceiling}/{total} ({ceil_rate}%)",
            f"- **Cascata completa:** {with_img}/{total} ({rate}%)",
            f"- **Ganho:** {'+' if gain >= 0 else ''}{gain} produtos "
            f"({'+' if gain >= 0 else ''}{rate - ceil_rate} p.p.) — graças ao "
            "merge + busca por nome.",
            "",
        ]

    # Matriz por categoria.
    categories = sorted({r["category"] for r in results})
    cat_totals = {c: sum(1 for r in results if r["category"] == c) for c in categories}
    lines += [
        "## Imagem por categoria",
        "",
        "| Categoria | Com imagem |",
        "|-----------|-----------|",
    ]
    for c in categories:
        img = sum(1 for r in results if r["category"] == c and r["has_image"])
        lines.append(f"| {c} | {img}/{cat_totals[c]} |")

    # Detalhe por EAN.
    lines += [
        "",
        "## Detalhe por EAN",
        "",
        "| EAN | Produto | Status | Fonte dados | Imagem | Latência |",
        "|-----|---------|--------|-------------|--------|----------|",
    ]
    icon = {"OK": "✅", "NAO_ENCONTRADO": "❌", "INDISPONIVEL": "⚠️", "INVALIDO": "🚫"}
    origin_tag = {"provedor": "🖼️ provedor", "merge": "🔀 merge", "busca-nome": "🔍 busca"}
    for r in results:
        o = _img_origin(r, label)
        img = origin_tag.get(o, "—")
        lines.append(
            f"| {r['ean']} | {r['label']} | {icon[r['status']]} {r['status']} | "
            f"{r.get('source') or '—'} | {img} | {r['latency_ms']} ms |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Relatório da cascata: %s", path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Benchmark das APIs de EAN, com logs em tempo real.")
    p.add_argument("--debug", action="store_true", help="logs DEBUG (mostra cada requisição HTTP)")
    p.add_argument("--mode", choices=["providers", "cascade", "both"], default="providers",
                   help="providers: cada API isolada (padrão) | cascade: cascata completa "
                        "(merge + fallback de imagem) | both: roda os dois e compara")
    p.add_argument("--pdf", nargs="?", const="produtos.pdf", metavar="ARQ",
                   help="usa os EANs extraídos de um PDF (padrão: produtos.pdf)")
    p.add_argument("--provider", "-p", action="append", metavar="NOME",
                   help="testa só este(s) provedor(es) (repetível). Ex.: -p cosmos -p gtin")
    p.add_argument("--delay", type=float, default=DELAY_BETWEEN_CALLS,
                   help=f"pausa entre requisições em segundos (padrão: {DELAY_BETWEEN_CALLS})")
    p.add_argument("--page-size", type=int, default=PAGE_SIZE, metavar="N",
                   help=f"tamanho da página p/ provedores que limitam por minuto "
                        f"(cosmos/gtin/ean-search). 0 desliga (padrão: {PAGE_SIZE}, máx 90)")
    p.add_argument("--page-pause", type=float, default=PAGE_PAUSE, metavar="S",
                   help=f"descanso entre páginas, em segundos (padrão: {PAGE_PAUSE})")
    p.add_argument("--retries", type=int, default=RETRIES, metavar="N",
                   help=f"tentativas extras quando um EAN toma 429 (padrão: {RETRIES})")
    p.add_argument("--retry-wait", type=float, default=RETRY_WAIT, metavar="S",
                   help=f"espera antes de cada retry, em segundos (padrão: {RETRY_WAIT})")
    p.add_argument("--limit", "-n", type=int, metavar="N",
                   help="limita aos N primeiros EANs (rodadas rápidas)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    setup_logging(args.debug)
    REPORTS_DIR.mkdir(exist_ok=True)
    # Benchmark mede APIs AO VIVO: força cache em memória para o SQLite
    # persistente não devolver resultados de rodadas anteriores.
    os.environ["EAN_CACHE_BACKEND"] = "memory"
    service = EANPicturesService(cache_ttl=0)

    # Escolhe o conjunto de EANs: do PDF ou a lista padrão de produtos populares.
    if args.pdf:
        eans = load_pdf_eans(ROOT / args.pdf)
    else:
        eans = TEST_EANS
        log.info("Conjunto padrão: %d produtos populares variados.", len(eans))

    if args.limit:
        eans = eans[: args.limit]
        log.info("Limitado aos %d primeiros EANs.", len(eans))

    providers = args.provider or PROVIDERS
    log.info("Provedores a testar: %s", ", ".join(providers))

    # Limita a página a 90 (espelha o teto de per_page das APIs REST).
    page_size = max(0, min(args.page_size, 90))
    if page_size != args.page_size:
        log.info("page-size ajustado para %d (máx 90).", page_size)
    paging = dict(page_size=page_size, page_pause=args.page_pause,
                  retries=args.retries, retry_wait=args.retry_wait)

    # Aviso de EANs com dígito verificador inválido (não atrapalha, só informa).
    invalid = [e for e, _, _ in eans if not luhn_gtin_valid(e)]
    if invalid:
        log.warning("EANs com checksum inválido (consultados mesmo assim): %s", invalid)

    tested, skipped = [], []
    free = {"upcitemdb", "openfoodfacts"}
    union_map: dict[str, bool] | None = None

    # ---- Modo por provedor (isolado) ----
    if args.mode in ("providers", "both"):
        for provider in providers:
            if needs_token(service, provider):
                env = service._PROVIDER_TOKEN_ENV[provider]
                log.warning("[%s] PULADO — exige %s, não configurado.", provider, env)
                write_report(provider, None, f"Provedor `{provider}` exige `{env}`, não configurado.")
                skipped.append({"provider": provider, "reason": "requer token"})
                continue

            results = run_provider(service, provider, eans, args.delay, **paging)
            write_report(provider, results, None)
            ok_lat = [r["latency_ms"] for r in results if r["status"] in ("OK", "NAO_ENCONTRADO")]
            tested.append(
                {
                    "provider": provider,
                    "results": results,
                    "found": sum(1 for r in results if r["status"] == "OK"),
                    "with_img": sum(1 for r in results if r["has_image"]),
                    "avg_lat": round(sum(ok_lat) / len(ok_lat)) if ok_lat else 0,
                    "note": "grátis (sem token)" if provider in free else "",
                }
            )

        write_summary(tested, skipped, eans)

        # Teto sem fallback: por EAN, algum provedor isolado trouxe imagem?
        union_map = {e: False for e, _, _ in eans}
        for s in tested:
            for r in s["results"]:
                if r["has_image"]:
                    union_map[r["ean"]] = True

    # ---- Modo cascata (caminho da app web: cascata + merge + fallback) ----
    if args.mode in ("cascade", "both"):
        # --provider também define a cadeia da cascata (senão usa EAN_API_PROVIDER).
        if args.provider:
            service.providers = [p.strip().lower() for p in args.provider if p.strip()]
        cascade_results = run_cascade(service, eans, args.delay, **paging)
        # Só compara com o teto quando rodamos os provedores na mesma execução.
        write_cascade_report(service, cascade_results, union_map if args.mode == "both" else None)

    log.info("Relatórios gerados em: %s", REPORTS_DIR)


if __name__ == "__main__":
    main()
