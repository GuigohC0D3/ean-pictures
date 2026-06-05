# Relatórios de provedores de EAN

Objetivo: **achar a melhor API geral — a que traz o produto E a imagem certos.**
Relatórios gerados por `tests/benchmark.py` testando cada provedor com o mesmo
conjunto de **14 produtos populares de várias categorias** (alimento, bebida,
eletrônico, livro, limpeza, saúde). Métrica principal: **% encontrado COM imagem**.

| Relatório | Provedor | Token | Testado |
|-----------|----------|-------|---------|
| [_RESUMO.md](_RESUMO.md) | — | — | Comparativo geral |
| [upcitemdb.md](upcitemdb.md) | UPCitemdb (trial) | Não | ✅ |
| [openfoodfacts.md](openfoodfacts.md) | Open Food Facts | Não | ✅ |
| [cosmos.md](cosmos.md) | Bluesoft Cosmos | Sim | ✅ (cota curta: toma 429) |
| [ean-db.md](ean-db.md) | EAN-DB | Sim | ⚠️ token rejeitado (403) |
| [gtin.md](gtin.md) | RSC Sistemas GTIN | Sim | ✅ (cota diária curta: toma 403) |
| [ean-search.md](ean-search.md) | EAN-Search | Sim | ⏭️ falta token |

## Como reproduzir

```bash
python tests/benchmark.py
```

Para testar os provedores autenticados, exporte os tokens antes:

```powershell
$env:COSMOS_TOKEN = "..."; $env:EAN_DB_TOKEN = "..."; $env:EAN_SEARCH_TOKEN = "..."
python tests/benchmark.py
```

---

## 📊 Quadro consolidado (com Farmácia) — melhores rodadas limpas

Como os tiers grátis rate-limitam ao re-rodar, esta tabela junta a **melhor
rodada limpa de cada provedor** (o `_RESUMO.md` mostra só a última execução).
Valor = **encontrados COM imagem / total da categoria**.

| Categoria | Open Food Facts | Cosmos | RSC GTIN | EAN-DB | UPCitemdb |
|-----------|-----------------|--------|----------|--------|-----------|
| Alimento (global) | **3/3** | 1/3 | 0/3 | n/d (403) | n/d (429) |
| Alimento BR | **2/2** | **2/2** | **2/2** | n/d | n/d |
| Bebida | **1/1** | 1/1 | **1/1** | n/d | 1/1 |
| Bebida BR | 1/2 | 0/2 | **1/2** | n/d | n/d |
| Eletrônico | 0/2 | 0/2 (acha s/ foto) | 0/1 | n/d | 0/2 |
| **Farmácia BR** | 1/5 | acha ~12/14, foto só ~3 | **acha c/ foto** (ex.: Sonrisal)¹ | n/d | 0 |
| Livro / Limpeza / Cosmético | 0 | 0 | n/d (cota)¹ | n/d | 0 |

¹ RSC GTIN: a cota diária grátis estourou (403) antes de varrer farmácia/livro,
mas no teste direto achou **Sonrisal COM imagem** — e **100% do que encontra vem
com foto**. Precisa de cota maior para uma avaliação completa.

**Leitura rápida:**
- **Comida/bebida → Open Food Facts** (grátis, foto boa) ou **RSC GTIN** (BR, sempre com foto).
- **Mercado/farmácia BR → Cosmos** (cobertura) **+ RSC GTIN** (imagem). A Cosmos
  acha mais, mas sem foto; a RSC traz foto do que tem.
- **Eletrônico/livro/cosmético com foto → ninguém grátis entrega bem**; depende de
  EAN-DB (403) ou EAN-Search (sem token).
- n/d = não avaliável agora (403/429 cota ou token rejeitado).

## Conclusões — melhor API para produto + imagem (03/06/2026)

> ⚠️ Os tiers gratuitos **rate-limitam** (HTTP 429) ao re-rodar o benchmark
> várias vezes no mesmo dia. Os números abaixo consolidam as **melhores rodadas
> limpas** de cada provedor; quando há 429/403, está sinalizado.

### 🥇 Open Food Facts — melhor para alimento/bebida (grátis)
**7/14 com imagem (50%)**, e dentro do que cobre é impecável: **Alimento 3/3,
Alimento BR 2/2, Bebida 1/1**. Pontos fracos: **não tem eletrônico, livro,
limpeza nem cosmético**. É a melhor escolha gratuita — desde que seu catálogo
seja comida/bebida.

### 🥈 Bluesoft Cosmos — melhor cobertura BR, imagem irregular
Em rodada limpa achou produtos de mercado BR **com imagem** (ex.: Leite Moça,
açúcar). Cobre MUITO produto brasileiro (inclusive farmácia), mas a **foto falta
com frequência** fora de mercearia, e o **plano grátis tem cota curta** (tomou
429 rápido). Ótima como base BR, não como fonte primária de imagem.

### 🖼️ RSC Sistemas GTIN — sempre traz foto do que acha (base BR)
**100% dos produtos encontrados vieram COM imagem** (Coca, Leite Moça, Açúcar,
Coca 2L) — e no teste direto achou **Sonrisal (farmácia) com foto**, justamente o
que falta na Cosmos. É BR-focada (não acha Nutella/Kinder/Lindt/iPhone).
**Dois poréns:**
1. **Cota diária grátis curta** — responde **403** ao estourar (não é token ruim);
   impediu varrer farmácia/livro nesta execução.
2. **A imagem exige token** (`/api/gtin/img/...` dá 401 sem Bearer), então **não
   carrega direto no `<img>`** do navegador — precisa de um **proxy no backend**.

### 💊 Farmácia — Cosmos acha, mas quase sem foto (RSC complementa)
A Cosmos encontra **~12 de 14** medicamentos do PDF (nenhuma outra chega perto:
OFF acha 3, UPCitemdb 0). Porém **só ~3 vêm com imagem** — a foto de remédio
simplesmente **não existe na maioria das bases**. Para um catálogo que inclui
farmácia, conte com a Cosmos para o **dado/nome** e planeje uma **fonte própria
de imagem** (fabricante/distribuidor) para os SKUs sem foto.

### 🔑 EAN-DB — não avaliada (token rejeitado, HTTP 403)
É o candidato mais promissor para **cobertura internacional ampla COM imagem**
(eletrônico, livro, etc.), mas **todas as consultas deram 403** — token inválido,
expirado ou sem permissão. **Gere uma chave nova em <https://ean-db.com>** e rode
o benchmark; provavelmente assume a liderança no geral.

### ⚠️ UPCitemdb — inviável no plano trial
Cota diária (~100/dia) estoura só com testes; deu **429** na maioria. Tem
imagem de eletrônico quando funciona, mas não dá para depender dele sem plano pago.

### Lacuna atual
Categorias **eletrônico, livro, limpeza e cosmético** ficaram **0 com imagem**
em todos os provedores testáveis — exatamente porque os dois melhores candidatos
para elas (**EAN-DB** e **EAN-Search**) estão sem token válido. Resolver isso é o
próximo passo para responder em definitivo "qual a melhor API geral".

## Recomendação

- **Catálogo de comida/bebida:** `openfoodfacts` resolve sozinho, de graça.
- **Catálogo brasileiro variado:** `cosmos` (cobertura) — mas assuma que muitas
  fotos faltarão; considere plano pago para subir a cota.
- **Catálogo geral com imagem (eletrônico/livro/cosmético):** valide o token da
  **EAN-DB** (ou teste **Go-UPC**) — sem isso, nenhum provedor gratuito entrega.

Cascata sugerida (a app já prioriza o resultado COM imagem):

```
EAN_API_PROVIDER = ean-db,cosmos,openfoodfacts,upcitemdb
```
