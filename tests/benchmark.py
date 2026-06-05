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
    Configura logs em tempo real no stdout, com timestamp.

    INFO (padrão): progresso por EAN, decisões de cascata, login, imagem.
    DEBUG (--debug): inclui cada requisição HTTP (GET url -> status, bytes).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%H:%M:%S"))
    level = logging.DEBUG if debug else logging.INFO
    for name in ("benchmark", "ean_service"):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.handlers = [handler]
        lg.propagate = False

# Carrega tokens do .env (se python-dotenv estiver instalado).
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ModuleNotFoundError:
    pass

from services.ean_service import (  # noqa: E402
    EANPicturesService,
    ProductNotFoundError,
    APIUnavailableError,
)

REPORTS_DIR = ROOT / "reports"

# Pausa entre requisições (segundos) para não tomar rate limit (HTTP 429).
DELAY_BETWEEN_CALLS = 1.2

PROVIDERS = ["gtin", "cosmos", "ean-db", "upcitemdb", "openfoodfacts", "ean-search"]

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


def run_provider(service: EANPicturesService, provider: str, eans: list[tuple[str, str, str]], delay: float) -> list[dict]:
    base_url = service._base_for(provider, is_first=False)
    total = len(eans)
    log.info("=== provedor [%s] | %d EANs | delay %.1fs | base=%s ===", provider, total, delay, base_url or "(default)")
    results = []
    for idx, (ean, label, category) in enumerate(eans):
        if idx and delay:
            time.sleep(delay)
        row: dict[str, object] = {"ean": ean, "label": label, "category": category}
        t0 = time.perf_counter()
        try:
            product = service._fetch_one(provider, ean, base_url)
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Benchmark das APIs de EAN, com logs em tempo real.")
    p.add_argument("--debug", action="store_true", help="logs DEBUG (mostra cada requisição HTTP)")
    p.add_argument("--pdf", nargs="?", const="produtos.pdf", metavar="ARQ",
                   help="usa os EANs extraídos de um PDF (padrão: produtos.pdf)")
    p.add_argument("--provider", "-p", action="append", metavar="NOME",
                   help="testa só este(s) provedor(es) (repetível). Ex.: -p cosmos -p gtin")
    p.add_argument("--delay", type=float, default=DELAY_BETWEEN_CALLS,
                   help=f"pausa entre requisições em segundos (padrão: {DELAY_BETWEEN_CALLS})")
    p.add_argument("--limit", "-n", type=int, metavar="N",
                   help="limita aos N primeiros EANs (rodadas rápidas)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    setup_logging(args.debug)
    REPORTS_DIR.mkdir(exist_ok=True)
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

    # Aviso de EANs com dígito verificador inválido (não atrapalha, só informa).
    invalid = [e for e, _, _ in eans if not luhn_gtin_valid(e)]
    if invalid:
        log.warning("EANs com checksum inválido (consultados mesmo assim): %s", invalid)

    tested, skipped = [], []
    free = {"upcitemdb", "openfoodfacts"}

    for provider in providers:
        if needs_token(service, provider):
            env = service._PROVIDER_TOKEN_ENV[provider]
            log.warning("[%s] PULADO — exige %s, não configurado.", provider, env)
            write_report(provider, None, f"Provedor `{provider}` exige `{env}`, não configurado.")
            skipped.append({"provider": provider, "reason": "requer token"})
            continue

        results = run_provider(service, provider, eans, args.delay)
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
    log.info("Relatórios gerados em: %s", REPORTS_DIR)


if __name__ == "__main__":
    main()
