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
- ⚡ **Cache em memória** para evitar consultas repetidas
- 🔌 Endpoint **REST** público: `GET /api/product/<ean>`
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
├── services/
│   ├── __init__.py
│   └── ean_service.py      # Classe EANPicturesService (integração + cache + validação)
│
├── static/
│   ├── style.css           # Estilos (tema escuro, responsivo)
│   └── script.js           # Lógica do front-end (fetch, loading, render)
│
├── templates/
│   └── index.html          # Página principal
│
└── data/
    └── history.json        # Histórico persistido (criado automaticamente)
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

- Cache com **TTL / Redis** em vez de dicionário em memória.
- Paginação e busca por **nome do produto**, não só por EAN.
- Suporte a **múltiplos provedores em cascata** (fallback automático).
- Testes automatizados (`pytest`) para o service e os endpoints.
- Autenticação e *rate limiting* na API REST.
- Internacionalização (i18n) da interface.
- Histórico por usuário (banco de dados em vez de JSON).
- Deploy com **Gunicorn + Docker**.
```
