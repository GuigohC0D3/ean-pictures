# 📦 EAN Pictures

Aplicação web em **Python + Flask** que recebe um código de barras (EAN/UPC),
consulta automaticamente os dados do produto na **API EAN Pictures** e exibe
nome, código, imagem e demais informações em uma interface moderna e responsiva.

> **Sobre a "API EAN Pictures":** não existe um serviço público com esse nome
> exato. Por isso o projeto foi construído de forma **agnóstica de provedor**,
> com **fallback em cascata** para cobrir EANs em geral (não só alimentos).
> Por padrão consulta o **UPCitemdb** (cobertura geral, sem token) e, se não
> encontrar, tenta o **Open Food Facts**. Tudo já funciona ao clonar; você pode
> trocar/adicionar o **EAN-Search** via variáveis de ambiente (veja
> [Configuração](#configuração)).

---

## ✨ Funcionalidades

- 🔎 Campo para digitar o EAN + botão **Buscar Produto**
- 🖼️ Exibição da imagem e dos dados do produto em **card**
- ✅ Validação do EAN (EAN-8, EAN-13, UPC-A, GTIN-14) pelo dígito verificador
- ⏳ Indicador de carregamento durante a busca
- 🧯 Tratamento de erros: EAN inválido, produto não encontrado e API indisponível
- 🕑 Histórico das **últimas 10 consultas** (persistido em JSON)
- ⚡ **Cache em 2 camadas** (memória + SQLite em disco) — sobrevive a reinícios
- 📦 **Consulta em lote**: cole vários EANs ou suba **PDF/CSV/XLSX** e exporte o resultado em **CSV/XLSX**
- 🖼️ **Merge de imagem na cascata**: usa o nome do provedor preferido + a foto de outro
- 🔍 **Fallback de imagem por nome** (Google CSE / SerpAPI) p/ produtos sem foto
- 🔌 Endpoint **REST** público: `GET /api/product/<ean>` + `POST /api/batch`
- 🐳 Pronto para **Docker + Gunicorn**
- 📱 Interface responsiva (celular e desktop)

---

## 🗂️ Estrutura do projeto

```
ean-pictures/
│
├── app.py                  # Aplicação Flask (rotas, histórico, tratamento de erros)
├── requirements.txt        # Dependências
├── README.md
│
├── Dockerfile              # Imagem de produção (Gunicorn)
├── docker-compose.yml      # Orquestração + volume persistente
│
├── services/
│   ├── __init__.py
│   ├── ean_service.py      # EANPicturesService (integração + cache + validação)
│   ├── cache.py            # Cache persistente em SQLite (camada L2)
│   └── batch.py            # Lote: extração de EANs + lookup paralelo + export
│
├── static/
│   ├── style.css           # Estilos (tema escuro, responsivo)
│   └── script.js           # Front-end (abas individual/lote, fetch, render)
│
├── templates/
│   └── index.html          # Página principal (abas: individual e em lote)
│
├── tests/                  # pytest: service, batch, rotas + benchmark
│
└── data/
    ├── history.json        # Histórico persistido (criado automaticamente)
    └── cache.db            # Cache SQLite (criado automaticamente)
```

---

## 🚀 Como instalar

Pré-requisitos: **Python 3.12+**.

```bash
# 1. Clone / entre na pasta do projeto
cd ean-pictures

# 2. Crie e ative um ambiente virtual
python -m venv venv
# Windows (PowerShell):
venv\Scripts\Activate.ps1
# Linux / macOS:
source venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt
```

---

## ▶️ Como executar

```bash
python app.py
```

Acesse no navegador: **http://localhost:5000**

> Dica: experimente o EAN `7891000100103` (Leite Moça) ou `3017620422003` (Nutella).

---

## ⚙️ Configuração

O serviço é configurável por **variáveis de ambiente** (todas opcionais):

| Variável           | Padrão                          | Descrição                                                        |
|--------------------|---------------------------------|------------------------------------------------------------------|
| `EAN_API_PROVIDER` | `upcitemdb,openfoodfacts`       | Provedores em cascata (vírgula). Opções: `cosmos`, `ean-db`, `upcitemdb`, `openfoodfacts`, `ean-search` |
| `EAN_API_TOKEN`    | _(vazio)_                       | Token global (fallback p/ provedores autenticados)               |
| `COSMOS_TOKEN`     | _(vazio)_                       | Token específico da Bluesoft Cosmos                              |
| `EAN_DB_TOKEN`     | _(vazio)_                       | Token (JWT) específico da EAN-DB                                 |
| `EAN_SEARCH_TOKEN` | _(vazio)_                       | Token específico do EAN-Search                                  |
| `EAN_API_BASE_URL` | URL padrão do provedor          | Sobrescreve o endpoint base do 1º provedor, se necessário        |
| `EAN_CACHE_TTL`    | `3600`                          | TTL do cache em segundos (`0` = nunca expira)                    |
| `RATE_LIMIT_MAX`   | `30`                            | Máx. de requisições por IP na janela (endpoints `/api/*`)        |
| `RATE_LIMIT_WINDOW`| `60`                            | Tamanho da janela do rate limit, em segundos                     |
| `FLASK_DEBUG`      | `0`                             | `1` liga o modo debug (use só em desenvolvimento)                |
| `HOST`             | `127.0.0.1`                     | Interface de bind (`0.0.0.0` para expor na rede)                 |
| `PORT`             | `5000`                          | Porta do servidor                                                |

> O valor de `EAN_API_PROVIDER` aceita **lista separada por vírgula**: os
> provedores são consultados na ordem até um encontrar o produto. Ex.:
> `upcitemdb,openfoodfacts,ean-search`.

### 🇧🇷 Produtos brasileiros (farmácia, mercado, etc.)

UPCitemdb e Open Food Facts são bases **internacionais** e têm cobertura fraca
de medicamentos e produtos brasileiros. Para esses casos, use a **Bluesoft
Cosmos**, que indexa GTINs do Brasil (inclui farmácia) e traz imagem:

1. Crie uma conta gratuita em <https://cosmos.bluesoft.com.br> e copie seu token.
2. Configure o provedor com o Cosmos **na frente** da cascata:

```powershell
$env:EAN_API_PROVIDER = "cosmos,upcitemdb,openfoodfacts"
$env:EAN_API_TOKEN = "SEU_TOKEN_COSMOS"
python app.py
```

Assim ele tenta primeiro a base brasileira e só recorre às internacionais se não
encontrar. Sem token, o `cosmos` é ignorado automaticamente na cascata.

### 🌐 Cobertura internacional ampla (EAN-DB)

Para reforçar produtos internacionais (eletrônicos, livros, importados), a
**EAN-DB** tem uma das maiores bases. Crie um token JWT gratuito em
<https://ean-db.com> e encadeie:

```powershell
$env:EAN_API_PROVIDER = "cosmos,ean-db,upcitemdb,openfoodfacts"
$env:COSMOS_TOKEN = "TOKEN_COSMOS"   # base BR
$env:EAN_DB_TOKEN = "JWT_EAN_DB"     # base internacional
python app.py
```

> Cada provedor autenticado lê seu **token específico** (`COSMOS_TOKEN`,
> `EAN_DB_TOKEN`, `EAN_SEARCH_TOKEN`); na falta dele, usa o `EAN_API_TOKEN`
> global. Isso permite encadear vários serviços com chaves diferentes.

Exemplo usando o EAN-Search (PowerShell):

```powershell
$env:EAN_API_PROVIDER = "ean-search"
$env:EAN_API_TOKEN = "SEU_TOKEN_AQUI"
python app.py
```

### 🔍 Fallback de imagem por nome

Quando a cascata acha o produto mas **sem foto**, o serviço pode procurar uma
imagem por busca textual (marca + nome). Desligado por padrão; ative com um
backend e suas credenciais:

```powershell
# Google Custom Search (100 buscas/dia grátis): crie a key e um "cx" com
# "Buscar imagens" ligado em https://programmablesearchengine.google.com
$env:IMAGE_SEARCH_PROVIDER = "google"
$env:GOOGLE_CSE_KEY = "SUA_KEY"
$env:GOOGLE_CSE_CX  = "SEU_CX"
python app.py

# Alternativa: SerpAPI
$env:IMAGE_SEARCH_PROVIDER = "serpapi"
$env:SERPAPI_KEY = "SUA_KEY"
```

A imagem encontrada fica salva no cache junto com o produto (não repete a busca)
e o card mostra a origem em `image_source`.

---

## 🔌 Como consumir a API REST

### `GET /api/product/<ean>`

Retorna os dados enxutos do produto:

```bash
curl http://localhost:5000/api/product/7891000100103
```

```json
{
  "ean": "7891000100103",
  "name": "Leite Condensado Moça",
  "image": "https://images.openfoodfacts.org/...",
  "description": "Leite condensado"
}
```

Erros retornam o status HTTP adequado e um corpo com `error` e `code`:

| Situação                | Status | `code`            |
|-------------------------|--------|-------------------|
| EAN inválido            | 400    | `invalid_ean`     |
| Produto não encontrado  | 404    | `not_found`       |
| API externa indisponível| 503    | `api_unavailable` |

### `GET /api/history`

Retorna as últimas 10 consultas registradas (JSON).

### `POST /api/batch`

Consulta vários EANs de uma vez. Aceita **JSON** ou **upload de arquivo**:

```bash
# JSON (lista ou texto colado)
curl -X POST http://localhost:5000/api/batch \
  -H "Content-Type: application/json" \
  -d '{"eans": ["7891000100103", "3017620422003"], "provider": "auto"}'

# Upload de PDF/CSV/XLSX/TXT (extrai e valida os EANs do arquivo)
curl -X POST http://localhost:5000/api/batch -F "file=@produtos.pdf"
```

Resposta: `{ ok, results[], summary{total,found,not_found,with_image}, history[] }`.
Quando o arquivo é PDF, cada item de `results` também recebe
`cosmos_image_url`, no formato
`https://cdn-cosmos.bluesoft.com.br/products/{ean}`. A interface usa essa URL
como alternativa quando os provedores consultados não retornam uma imagem.

### `POST /api/batch/export.{csv|xlsx}`

Reconsulta uma lista de EANs e devolve um arquivo para download:

```bash
curl -X POST http://localhost:5000/api/batch/export.xlsx \
  -H "Content-Type: application/json" \
  -d '{"eans": ["7891000100103"]}' -o produtos.xlsx
```

---

## 🧪 Testes

```bash
pip install -r requirements-dev.txt
pytest -q
```

Cobrem validação de EAN, cache (memória + SQLite), cascata/merge de imagem,
extração de EANs (texto/CSV) e todas as rotas Flask (serviço externo mockado).

### Benchmark de cobertura (APIs ao vivo)

`tests/benchmark.py` compara as fontes em produtos reais. Três modos:

```bash
# Cada API isolada (gera reports/<provedor>.md + _RESUMO.md) — padrão
python tests/benchmark.py

# Cascata completa (merge + fallback de imagem) — o caminho da app web
python tests/benchmark.py --mode cascade

# Roda os dois e mede o GANHO da cascata sobre os provedores isolados
python tests/benchmark.py --mode both        # -> reports/_cascata.md
```

Úteis: `--pdf produtos.pdf` (usa EANs de um PDF), `-n 20` (limita), `-p cosmos`
(só um provedor). O benchmark sempre usa cache em memória — mede chamadas ao vivo.

### Benchmark direto da CDN Cosmos

O benchmark separado abaixo testa as URLs
`https://cdn-cosmos.bluesoft.com.br/products/{ean}` sem consultar a API Cosmos
e sem sobrescrever os relatórios do benchmark original:

```powershell
.\venv\Scripts\python.exe tests\benchmark_cosmos_cdn.py --pdf produtos.pdf
.\venv\Scripts\python.exe tests\benchmark_cosmos_cdn.py --pdf novos_produtos.pdf -n 20
```

O resultado é gravado em `reports/cosmos-cdn.md`. Uma URL só conta como imagem
quando responde HTTP 200 e o corpo tem tipo ou assinatura binária de imagem.

**Rate limit (Cosmos/GTIN/EAN-Search):** esses provedores limitam por minuto.
O benchmark processa os EANs em **páginas** (lotes) com pausa entre elas e faz
**retry quando toma 429**, aplicado só a esses provedores:

```bash
# 30 EANs por página, 60s de descanso entre páginas, 2 retries de 60s
python tests/benchmark.py --mode both --pdf produtos.pdf \
  --page-size 30 --page-pause 60 --retries 2 --retry-wait 60
```

| Flag | Padrão | O que faz |
|------|--------|-----------|
| `--page-size N` | 30 | EANs por página (máx 90; `0` desliga a paginação) |
| `--page-pause S` | 60 | segundos de descanso entre páginas |
| `--retries N` | 2 | tentativas extras quando um EAN recebe 429 |
| `--retry-wait S` | 60 | espera antes de cada retry |

> ⚠️ Paginação resolve limite **por minuto**. Se a **cota diária** do tier grátis
> já estourou (429 em toda chamada mesmo após a pausa), aguarde o reset ou rode
> sem aquele provedor (ex.: `-p openfoodfacts -p gtin`).

---

## 🐳 Deploy com Docker

```bash
# build + run (Gunicorn na porta 8000, cache e histórico persistidos em ./data)
docker compose up --build
```

Acesse **http://localhost:8000**. Configure tokens/provedores via `.env`
(o `docker-compose.yml` já o carrega).

---

## 🧱 Arquitetura

- **`services/ean_service.py`** — toda a integração externa fica isolada na classe
  `EANPicturesService`, que:
  - valida o EAN pelo dígito verificador;
  - consulta o provedor configurado;
  - **formata** a resposta em um dicionário padrão (`ean`, `name`, `image`,
    `description`, `extra`, `source`);
  - mantém um **cache em memória** thread-safe;
  - traduz falhas em exceções de domínio (`InvalidEANError`,
    `ProductNotFoundError`, `APIUnavailableError`).
- **`app.py`** — camada web: rotas, persistência do histórico e tratamento
  centralizado de erros (`consultar_produto`).
- **Front-end** — `index.html` + `style.css` + `script.js` consomem `/buscar`
  via `fetch` e renderizam o card e o histórico sem recarregar a página.

---

## 🔮 Possíveis melhorias futuras

Já implementados:

- ✅ Cache persistente em **SQLite** (TTL) além do dicionário em memória.
- ✅ **Múltiplos provedores em cascata** (fallback automático) + merge de imagem.
- ✅ Testes automatizados (`pytest`) para o service, o batch e os endpoints.
- ✅ *Rate limiting* na API REST.
- ✅ **Consulta em lote** (texto/PDF/CSV/XLSX) + export CSV/XLSX.
- ✅ Deploy com **Gunicorn + Docker**.

- ✅ **Fallback de imagem por nome** (Google CSE / SerpAPI) p/ os ~77% sem foto.

Em aberto:

- Cache distribuído (**Redis**) para múltiplas instâncias.
- Paginação e busca por **nome do produto**, não só por EAN.
- Autenticação (API key) na API REST.
- Internacionalização (i18n) da interface.
- Histórico por usuário (banco de dados em vez de JSON).
```
