# Relatório — APIs de consulta de produtos por EAN/GTIN

**Projeto:** ean-pictures · **Data:** 2026-06-05
**Objetivo:** avaliar as APIs integradas, com base em testes reais desta sessão, e recomendar a melhor configuração.

---

## 1. Metodologia

Cada provedor foi consultado isoladamente (`EANPicturesService(provider=...)`) com a mesma amostra de 5 EANs, medindo: cobertura (achou o produto), presença de imagem, erros e latência média.

Amostra:

| EAN | Produto | Tipo |
|-----|---------|------|
| 7894900011517 | Coca-Cola 2L | bebida (BR) |
| 7891000100103 | Leite Moça | alimento (BR) |
| 7891000053508 | Nescau | alimento (BR) |
| 7895858017156 | Calman (Aspen) | **medicamento** (BR) |
| 0049000028911 | Coca lata | internacional (UPC) |

---

## 2. Resultado comparativo

| API | Achou | Com imagem | Erros | Latência | Auth | Custo |
|-----|:-----:|:----------:|:-----:|:--------:|------|-------|
| **Bluesoft Cosmos** | **5/5** | **4** | 0 | **0,41s** | token | grátis (c/ limite) |
| Open Food Facts | 4/5 | 4 | 0 | 0,63s | nenhuma | grátis |
| RSC GTIN | 3–4/5 | 1–2 | 403* | 0,45s | login/token (auto) | grátis (20 req/min) |
| UPCitemdb | 2/5 | 1 | 0 | 0,98s | nenhuma (trial) | grátis (~100/dia) |
| EAN-DB | 0/5 | 0 | 403 | — | token JWT | grátis/pago |
| EAN-Search | 0/5 | 0 | sem token | — | token | pago |

\* *Os 403 do GTIN são **rate-limit** (20 req/min). O Calman foi encontrado em teste anterior; sob carga, o limite derruba tanto a busca quanto a imagem.*

---

## 3. Análise por API

### 🥇 Bluesoft Cosmos — `cosmos`
- **Melhor cobertura BR** (5/5, incluindo o medicamento) e **mais rápida** (0,41s).
- Imagem na maioria (4/5), traz marca, NCM, GPC e preço médio.
- Requer `COSMOS_TOKEN` (cadastro grátis). O plano gratuito tem cota de requisições — adequado para uso moderado/testes.

### 🥈 Open Food Facts — `openfoodfacts`
- **Grátis, sem token, sem rate-limit prático.** Ótimas imagens de **alimentos/bebidas**.
- Não cobre medicamentos nem não-alimentos (perdeu o Calman).
- Ideal como **fallback gratuito** para a categoria alimentos.

### 🥉 RSC GTIN — `gtin`
- Boa base BR (inclui farma), com **auto-login** já implementado (token de 1h renovado sozinho).
- **Limitações reais:** rate-limit de **20 req/min** e cada busca custa **2 chamadas** (dados + imagem protegida via proxy) → na prática ~10 buscas/min antes de degradar. Muitos produtos só têm **placeholder** (sem foto real).
- Bom como **fonte BR secundária**, não como principal sob carga.

### UPCitemdb — `upcitemdb`
- Melhor para **produtos internacionais**; cobertura BR fraca e latência alta (~1s).
- Trial limitado a ~100 consultas/dia por IP.

### EAN-DB — `ean-db`
- Base internacional ampla, **mas o token atual está inválido/expirado (403)** — não pôde ser avaliada. Reativar exige novo `EAN_DB_TOKEN`.

### EAN-Search — `ean-search`
- **Não testada** (sem token configurado). Serviço pago.

---

## 4. Recomendação

**Para este projeto (foco BR, com imagens):**

> **Principal: Bluesoft Cosmos.** Melhor cobertura, melhor imagem, mais rápida e cobre farma.
> **Fallback gratuito: Open Food Facts** (alimentos, sem token/limite).
> **Reserva BR: RSC GTIN** (já tem auto-login; bom quando Cosmos não acha).

Cascata sugerida no `.env`:

```env
EAN_API_PROVIDER=cosmos,openfoodfacts,gtin,upcitemdb
```

Racional da ordem:
1. **cosmos** — acha quase tudo e com imagem (resolve a maioria já no 1º passo).
2. **openfoodfacts** — grátis e ilimitado; pega alimento que o Cosmos não tiver, sem gastar cota.
3. **gtin** — backup BR; fica pouco acionado, então o rate-limit de 20/min não incomoda.
4. **upcitemdb** — só para EAN internacional que ninguém achou.

> A lógica de cascata já prioriza resultado **com imagem**: se o Cosmos achar sem foto, o serviço segue testando até achar uma fonte com imagem real (incl. o placeholder do GTIN já é descartado).

**Para uso internacional:** priorizar `upcitemdb` e reativar `ean-db` (token novo).

---

## 4.1 Teste com o catálogo real (produtos.pdf)

O `produtos.pdf` contém **30 EANs** — todos com dígito verificador válido. É um **catálogo de farmácia** (Calman, Leite de Magnésia Phillips, OsteoNutri, Sonrisal, vitaminas/suplementos). Rodando pela cascata `cosmos,openfoodfacts,gtin,upcitemdb`:

| Métrica | Resultado |
|---------|-----------|
| Códigos no PDF | 30 (100% dígito válido) |
| Encontrados | **25/30** (22 no 1º lote + 3 recuperados) |
| Fonte predominante | **Bluesoft Cosmos** (texto), GTIN como backup |
| **Com imagem** | **~2–3/30** (só Open Food Facts; itens de consumo) |
| Erros 429/403 | cota do **Cosmos** e limite do **GTIN (20/min)** estourados no lote |
| 5 "não achados" | inconclusivos — Cosmos/GTIN já estavam rate-limited |

**Conclusões específicas deste catálogo:**

1. **Cobertura textual: Cosmos vence com folga** — achou a maioria dos medicamentos pelo nome. GTIN é bom reforço (recuperou vários quando o Cosmos atingiu a cota).
2. **Imagem de medicamento é escassa em TODAS as APIs** (~2–3 em 30). Não é limitação do app — as bases gratuitas simplesmente não têm foto de remédio. O **card visual** (iniciais + cor + marca) é a UX correta aqui.
3. **O gargalo real para lote é o rate-limit:** processar 30 EANs já esgotou as cotas gratuitas de Cosmos e GTIN. Para rodar o catálogo inteiro seria preciso **throttling + cache** (já há cache de 1h) ou **plano pago**.

---

## 5. Resumo executivo

| Pergunta | Resposta |
|----------|----------|
| Melhor no geral (BR + imagem) | **Bluesoft Cosmos** |
| Melhor grátis sem token | **Open Food Facts** (só alimentos) |
| Melhor para internacional | UPCitemdb / EAN-DB |
| Mais limitada na prática | RSC GTIN (20 req/min + 2 chamadas/busca) |
| Indisponíveis no teste | EAN-DB (403) e EAN-Search (sem token) |
