# EAN Pictures — imagem de produção (Flask + Gunicorn)
FROM python:3.12-slim

# Não gera .pyc e força stdout/stderr sem buffer (logs em tempo real).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instala dependências primeiro (melhor cache de camadas).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante da aplicação.
COPY . .

# data/ guarda history.json e cache.db em runtime.
RUN mkdir -p data

EXPOSE 8000

# 3 workers gthread cobrem bem I/O-bound (consultas HTTP externas).
# host 0.0.0.0 para aceitar conexões de fora do container.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", \
     "--threads", "4", "--timeout", "60", "app:app"]
