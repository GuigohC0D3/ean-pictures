# Resumo comparativo — melhor API (produto + imagem)

_Gerado em 09/06/2026 10:00._

Conjunto: **25 produtos populares** de várias categorias.
**Métrica principal: % encontrado COM imagem** (traz produto e foto certos).

## 🏆 Ranking por imagem

| # | Provedor | Com imagem | Encontrados | Latência média | Observação |
|---|----------|-----------|-------------|----------------|------------|
| 🥇 | `openfoodfacts` | **10/25** (40%) | 12/25 | 644 ms | grátis (sem token) |
| 🥈 | `cosmos` | **6/25** (24%) | 24/25 | 482 ms |  |
| 🥉 | `gtin` | **0/25** (0%) | 6/25 | 423 ms |  |
| 4 | `ean-db` | **0/25** (0%) | 0/25 | 0 ms |  |
| 5 | `upcitemdb` | **0/25** (0%) | 0/25 | 10073 ms | grátis (sem token) |
| – | `ean-search` | — | — | — | ⏭️ requer token |

## Imagem por categoria

Quantos produtos vieram **com imagem** em cada categoria (por provedor).

| Provedor | PDF |
|----------|---|
| `openfoodfacts` | 10/25 |
| `cosmos` | 6/25 |
| `gtin` | 0/25 |
| `ean-db` | 0/25 |
| `upcitemdb` | 0/25 |

## Como ler

- **Com imagem** é o que importa: o produto retornado traz foto utilizável.
- A matriz por categoria mostra em quê cada API é forte.
- Provedores ⏭️ exigem token válido e não entraram no ranking.
