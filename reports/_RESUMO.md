# Resumo comparativo — melhor API (produto + imagem)

_Gerado em 05/06/2026 12:53._

Conjunto: **316 produtos populares** de várias categorias.
**Métrica principal: % encontrado COM imagem** (traz produto e foto certos).

## 🏆 Ranking por imagem

| # | Provedor | Com imagem | Encontrados | Latência média | Observação |
|---|----------|-----------|-------------|----------------|------------|
| 🥇 | `openfoodfacts` | **73/316** (23%) | 81/316 | 548 ms | grátis (sem token) |
| 🥈 | `gtin` | **5/316** (2%) | 40/316 | 377 ms |  |
| 🥉 | `cosmos` | **0/316** (0%) | 0/316 | 0 ms |  |
| 4 | `ean-db` | **0/316** (0%) | 0/316 | 0 ms |  |
| 5 | `upcitemdb` | **0/316** (0%) | 3/316 | 388 ms | grátis (sem token) |
| – | `ean-search` | — | — | — | ⏭️ requer token |

## Imagem por categoria

Quantos produtos vieram **com imagem** em cada categoria (por provedor).

| Provedor | PDF |
|----------|---|
| `openfoodfacts` | 73/316 |
| `gtin` | 5/316 |
| `cosmos` | 0/316 |
| `ean-db` | 0/316 |
| `upcitemdb` | 0/316 |

## Como ler

- **Com imagem** é o que importa: o produto retornado traz foto utilizável.
- A matriz por categoria mostra em quê cada API é forte.
- Provedores ⏭️ exigem token válido e não entraram no ranking.
