# Relatório completo — Benchmark de APIs de EAN (produto + imagem)

_Gerado em 09/06/2026, a partir da última execução de `tests/benchmark.py`._

**Objetivo:** identificar qual(is) provedor(es) trazem **produto correto + imagem utilizável** para um conjunto de 25 EANs reais (medicamentos, higiene e correlatos extraídos de PDFs).

**Métrica principal:** `% encontrado COM imagem` — só interessa o resultado que devolve a foto certa do produto. "Encontrado sem imagem" é um resultado parcial.

---

## 1. Sumário executivo

| Posição | Provedor | Com imagem | Encontrados | Latência média | Custo / token |
|:---:|---|:---:|:---:|:---:|---|
| 🥇 | `openfoodfacts` | **10/25 (40%)** | 12/25 | 584 ms | grátis, sem token |
| 🥈 | `cosmos` | **6/25 (24%)** | 24/25 | **462 ms** | token (ativo) |
| 🥉 | `gtin` | 1/25 (4%) | 6/25 | 583 ms | token (cota estourada) |
| 4 | `ean-db` | 0/25 (0%) | 0/25 | — | token (401/403) |
| 5 | `upcitemdb` | 0/25 (0%) | 0/25 | 7762 ms | grátis, sem token |

**Cascata** `gtin → upcitemdb → openfoodfacts` (com merge entre provedores): **10/25 (40%) com imagem**, 15/25 encontrados.

### Conclusões rápidas

- **Melhor cobertura de imagem:** `openfoodfacts` (grátis) — empata com a cascata completa, sozinho.
- **Melhor cobertura de produto (nome):** `cosmos` — acha 24/25, mas só 6 trazem foto.
- **`gtin` e `ean-db` estão com cota/token estourados** (HTTP 401/403 em massa) — resultado atual não reflete a capacidade real dessas APIs.
- **`upcitemdb` é inviável neste cenário:** 0 acertos e latência catastrófica (3 requisições passaram de 60s — provável rate limit/backoff).
- A **combinação ideal** observada: `cosmos` para o **nome** do produto + `openfoodfacts`/merge para a **imagem**.

---

## 2. Conjunto de teste

- **25 produtos** (rotulados `PDF #1`…`PDF #25`), categoria única **PDF**.
- Predominância de medicamentos e itens de higiene de marcas BR (Intimus, EMS, Allegra, Ambroxol, Aspdip, etc.).
- Vários EANs são de produtos farmacêuticos nacionais — daí a vantagem de bases BR (`cosmos`) e a fraqueza de bases internacionais (`upcitemdb`).

---

## 3. Resultado por provedor

### 🥇 openfoodfacts — 40% com imagem (10/25)

- **Encontrados:** 12/25 · **Com imagem:** 10/25 · **Latência:** 584 ms · **grátis, sem token**.
- Quando acha, quase sempre traz foto: **10 dos 12 encontrados (83%) vêm com imagem**.
- Forte em medicamentos com registro em base aberta (Acetilcisteína, Allegra, Ambroxol, barra proteica).
- Fraqueza: não cobre itens de higiene Intimus (PDF #1–#4) nem alguns genéricos (PDF #18–#24).
- Nomes às vezes imprecisos ("Produto sem nome" no PDF #9), mas a **imagem** está presente.

### 🥈 cosmos — 24% com imagem, mas 96% de cobertura de nome (24/25)

- **Encontrados:** 24/25 · **Com imagem:** 6/25 · **Latência:** 462 ms (a **mais rápida**).
- Imbatível para **identificar o produto**: só falhou no PDF #18.
- Porém entrega **foto em poucos casos** (PDF #1–#4 Intimus, #20 aparelho, #25 barra proteica).
- Papel ideal: **fonte de nome/descrição canônica**, complementada por imagem de outra fonte.

### 🥉 gtin — degradado por cota (1/25 com imagem)

- **Encontrados:** 6/25 · **Com imagem:** 1/25 · **Latência:** 583 ms.
- ⚠️ **19/25 consultas retornaram HTTP 401/403** — cota/rate limit da RSC GTIN esgotado.
- Os 6 acertos (PDF #1–#3, #13–#15) sugerem que **com cota ativa o desempenho seria muito maior**.
- **Ação:** reavaliar após renovação de cota antes de descartar.

### 4. ean-db — indisponível (0/25)

- **25/25 consultas com HTTP 403.** Token inválido/expirado ou cota esgotada.
- Sem dados úteis nesta rodada. **Não avaliável** no estado atual.

### 5. upcitemdb — inviável (0/25)

- **Encontrados:** 0/25 · **Latência média:** 7762 ms.
- Três requisições estouraram **>60s** (PDF #11, #17, #23) — rate limit/backoff do tier grátis.
- Base internacional, sem cobertura dos EANs BR deste conjunto. **Descartar para este caso de uso.**

### – ean-search — não testado

- Requer `EAN_SEARCH_TOKEN`, não configurado. Fora do ranking.

---

## 4. Modo cascata (merge + fallback)

Cadeia: `gtin → upcitemdb → openfoodfacts` · fallback de imagem por nome: **desligado**.

| Métrica | Valor |
|---|---|
| Encontrados | 15/25 |
| **Com imagem** | **10/25 (40%)** |
| Imagem do próprio provedor | 9 |
| Imagem via merge (outro provedor) | 1 |
| Imagem via busca por nome | 0 (fallback off) |

**Observação importante:** a cascata atual (10/25) **não supera** `openfoodfacts` sozinho (10/25), e fica **abaixo do teto teórico** de 15/25 (60%) que seria alcançável se todos os provedores estivessem com cota ativa. O ganho negativo (-5 produtos vs. teto) é consequência direta de **`gtin` e `ean-db` em 403** — não de falha da estratégia de cascata.

### Por que a cascata não brilhou nesta rodada

1. `gtin` (primeiro da cadeia) está em 403 → quase não contribui.
2. `upcitemdb` (segundo) acha 0 → não contribui.
3. Sobra `openfoodfacts` carregando sozinho → resultado ≈ openfoodfacts isolado.
4. Fallback de imagem por nome estava **desligado** → perdeu-se a chance de casar nomes do `cosmos` com imagens de busca.

---

## 5. Recomendações

### Configuração recomendada (curto prazo, sem custo)

```
Cascata: cosmos → openfoodfacts
Fallback de imagem por nome: LIGADO
```

- `cosmos` resolve o **nome** em 24/25 casos.
- `openfoodfacts` cobre **10/25 com imagem** de graça.
- O **merge** combina nome do cosmos + imagem do OFF; o **fallback por nome** tende a recuperar parte dos 14 sem foto.

### Ações pendentes

1. **Renovar/validar cota de `gtin` e `ean-db`** e re-rodar — são as APIs com maior potencial inexplorado nesta rodada (alta cobertura BR esperada).
2. **Ligar o fallback de imagem por nome** na cascata (`--mode cascade`) — estava off e zerou esse caminho.
3. **Configurar `EAN_SEARCH_TOKEN`** para avaliar o 6º provedor.
4. **Remover `upcitemdb` da cascata** para este conjunto BR — só adiciona latência (até 60s) sem retorno.
5. Tratar o caso `cosmos` "encontra nome mas sem foto": acionar busca de imagem por nome como fonte secundária.

---

## 6. Anexo — detalhe por EAN (consolidado)

Legenda: ✅ encontrado · ❌ não encontrado · ⚠️ indisponível (403) · 🖼️ com imagem

| EAN | openfoodfacts | cosmos | gtin | ean-db | upcitemdb |
|---|:---:|:---:|:---:|:---:|:---:|
| 7896007550906 | ❌ | ✅🖼️ | ✅ | ⚠️ | ❌ |
| 7896007550890 | ❌ | ✅🖼️ | ✅ | ⚠️ | ❌ |
| 7896007544059 | ❌ | ✅🖼️ | ✅ | ⚠️ | ❌ |
| 7896007544042 | ❌ | ✅🖼️ | ⚠️ | ⚠️ | ❌ |
| 7896004708706 | ✅🖼️ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7896004715292 | ❌ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7896004713366 | ❌ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7896004713342 | ✅🖼️ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7896004710891 | ✅🖼️ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7891142115492 | ✅🖼️ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7891058002589 | ✅🖼️ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7891058004354 | ✅🖼️ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7891058004347 | ✅🖼️ | ✅ | ✅🖼️ | ⚠️ | ❌ |
| 7896523207681 | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| 7896523207667 | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| 7896523207636 | ✅🖼️ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7896523207643 | ✅🖼️ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7891058021740 | ❌ | ❌ | ⚠️ | ⚠️ | ❌ |
| 7891058021665 | ❌ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7501843502926 | ❌ | ✅🖼️ | ⚠️ | ⚠️ | ❌ |
| 7891106916653 | ❌ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7891106916660 | ❌ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7891106916684 | ❌ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7891106916639 | ❌ | ✅ | ⚠️ | ⚠️ | ❌ |
| 7896045115709 | ✅🖼️ | ✅🖼️ | ⚠️ | ⚠️ | ❌ |

> Relatórios individuais por provedor: `reports/openfoodfacts.md`, `reports/cosmos.md`, `reports/gtin.md`, `reports/ean-db.md`, `reports/upcitemdb.md`. Comparativos: `reports/_RESUMO.md` e `reports/_cascata.md`.
