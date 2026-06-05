# Relatório — APIs de consulta de produtos por EAN/GTIN

**Projeto:** ean-pictures · **Data:** 2026-06-05 (atualizado)
**Base:** benchmark automatizado (`tests/benchmark.py`) sobre **316 EANs** do catálogo `novos_produtos.pdf` (farmácia: absorventes, xaropes, antialérgicos, analgésicos etc.).

---

## 1. Metodologia

Cada provedor foi consultado **isoladamente** com os mesmos 316 EANs, medindo cobertura (achou o produto), **presença de imagem** (métrica principal), latência e erros. Relatórios brutos por provedor em `reports/<provedor>.md`; ranking em `reports/_RESUMO.md`.

> ⚠️ **Aviso importante sobre este lote:** rodar 316 EANs de uma vez **estoura as cotas/limites gratuitos**. Só o Open Food Facts (sem token, sem limite prático) rodou limpo. Os demais números estão **subestimados** por rate-limit/cota/token e **não devem ser lidos como cobertura real** — veja a coluna "Confiabilidade".

---

## 2. Resultado do benchmark (316 EANs)

| API | Achou | Com imagem | Erros no lote | Latência | Confiabilidade do número |
|-----|:-----:|:----------:|---------------|:--------:|--------------------------|
| **Open Food Facts** | **81/316** | **73/316 (23%)** | 0 | 548 ms | ✅ **limpo** (sem limite) |
| RSC GTIN | 40/316 | 5/316 | 245× HTTP 403 | 377 ms | ⚠️ subestimado (rate-limit 20/min) |
| UPCitemdb | 3/316 | 0 | 245× HTTP 429 | 388 ms | ⚠️ subestimado (trial ~100/dia) |
| Bluesoft Cosmos | 0/316 | 0 | **316× HTTP 429** | — | ❌ inválido (cota esgotada antes) |
| EAN-DB | 0/316 | 0 | 316× HTTP 403 | — | ❌ inválido (token expirado) |
| EAN-Search | — | — | sem token | — | ⏭️ não testado |

**Leitura honesta:**
- **Open Food Facts foi o único confiável** neste lote e foi muito bem: dos 81 que achou, **73 tinham foto (90%)** — alto até para medicamento.
- **GTIN** achou 40 nas primeiras chamadas e depois levou 403 em série (limite 20/min). Quase sem imagem (5), como esperado p/ farma.
- **Cosmos** marcou 0 porque a cota já estava esgotada de rodadas anteriores — **não reflete a capacidade real dele** (no teste menor de 30 EANs, o Cosmos foi o líder de cobertura). Precisa rodar sozinho, depois da cota renovar.
- **EAN-DB**: token inválido (403) — não avaliável até renovar `EAN_DB_TOKEN`.

---

## 3. O achado principal: o gargalo é rate-limit, não cobertura

Para um **catálogo grande (316+ itens)**, o fator decisivo deixou de ser "quem tem mais dados" e passou a ser **"quem aguenta o volume"**:

| API | Limite gratuito | Aguenta lote grande? |
|-----|-----------------|----------------------|
| Open Food Facts | sem limite prático | ✅ sim |
| RSC GTIN | 20 req/min (+2 chamadas/busca) | ❌ não (403 em série) |
| Bluesoft Cosmos | cota gratuita limitada | ❌ não (429) |
| UPCitemdb | ~100/dia (trial) | ❌ não (429) |
| EAN-DB / EAN-Search | conforme plano (pago) | depende do plano |

---

## 4. Recomendação

### Para processar catálogo em lote (caso deste PDF)
> **Workhorse: Open Food Facts.** É o único que roda o catálogo inteiro sem estourar limite, e ainda traz foto em ~90% do que encontra. Use como base.
> **Enriquecimento alvo: Cosmos + GTIN**, só para os EANs que o OFF *não* achou, com **throttling** (respeitar 20/min do GTIN e a cota do Cosmos) e aproveitando o **cache de 1h** já existente.

Cascata sugerida no `.env` (ordem por confiabilidade sob volume):

```env
EAN_API_PROVIDER=openfoodfacts,cosmos,gtin,upcitemdb
```

> Coloquei **openfoodfacts primeiro** de propósito: grátis, ilimitado e com ótima taxa de imagem — resolve a maioria sem gastar cota das outras. Cosmos/GTIN entram só no que sobrar, preservando suas cotas.

### Para consultas avulsas (uso interativo no front)
Aí o volume é baixo e o melhor é a **cobertura BR**: `cosmos,openfoodfacts,gtin` (Cosmos lidera quando não está sob carga).

### Pré-requisitos para um benchmark limpo
1. Rodar **um provedor por vez** com `--delay` alto (ex.: `--delay 3.5` no GTIN).
2. Aguardar a renovação da **cota do Cosmos** e testá-lo sozinho.
3. Renovar o **`EAN_DB_TOKEN`** (hoje 403).

```bash
# exemplo de rodada limpa só do GTIN, respeitando o limite de 20/min
./venv/Scripts/python.exe tests/benchmark.py --pdf novos_produtos.pdf -p gtin --delay 3.5 --debug
```

---

## 5. Resumo executivo

| Pergunta | Resposta |
|----------|----------|
| Melhor para **lote grande** | **Open Food Facts** (único sem limite; 90% de imagem no que acha) |
| Melhor **cobertura BR avulsa** | Bluesoft Cosmos (quando não sob carga) |
| Backup BR | RSC GTIN (com throttling; pouca imagem) |
| Gargalo real do projeto | **rate-limit/cota** — não a cobertura |
| Inválidos neste lote | Cosmos (429), EAN-DB (403), EAN-Search (sem token) |
| Imagem de medicamento | escassa em geral; OFF é a melhor fonte disponível |
