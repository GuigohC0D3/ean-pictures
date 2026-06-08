# Cascata completa — produto + imagem (com merge e fallback)

_Gerado em 08/06/2026 11:15 por `tests/benchmark.py --mode cascade`._

Cascata: `gtin,upcitemdb,openfoodfacts`  ·  Fallback de imagem: `desligado`

## Resumo

- **Encontrados:** 3/3
- **Com imagem:** 3/3  (**100%**) ← métrica principal

### Origem da imagem

- 🖼️ Do próprio provedor: **1**
- 🔀 De outro provedor (merge): **2**
- 🔍 Da busca por nome (fallback): **0**

## Ganho sobre os provedores isolados

- **Teto sem fallback** (algum provedor isolado tinha foto): 3/3 (100%)
- **Cascata completa:** 3/3 (100%)
- **Ganho:** +0 produtos (+0 p.p.) — graças ao merge + busca por nome.

## Imagem por categoria

| Categoria | Com imagem |
|-----------|-----------|
| Alimento | 2/2 |
| Bebida | 1/1 |

## Detalhe por EAN

| EAN | Produto | Status | Fonte dados | Imagem | Latência |
|-----|---------|--------|-------------|--------|----------|
| 3017620422003 | Nutella 400g | ✅ OK | Open Food Facts | 🖼️ provedor | 1527 ms |
| 5449000000996 | Coca-Cola lata 330ml | ✅ OK | RSC GTIN | 🔀 merge | 815 ms |
| 8000500310427 | Kinder Bueno | ✅ OK | UPCitemdb | 🔀 merge | 1732 ms |
