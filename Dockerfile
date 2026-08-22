# Dockerfile

# Estágio 1: Imagem base
FROM python:3.10-slim

# Invalidates the application layer on every published commit.
ARG BUILD_REV=dev
ENV BUILD_REV=${BUILD_REV}

# Variáveis de ambiente
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Estágio 2: Instalação de dependências
WORKDIR /app
COPY requirements.txt .
# Copy AutoSINAPI toolkit before pip install for local install
COPY ./AutoSINAPI /app/AutoSINAPI
RUN python - <<'PY'
from pathlib import Path

config = Path('/app/AutoSINAPI/autosinapi/config.py')
text = config.read_text()
text = text.replace(
    '"DOWNLOAD_FILENAME_TEMPLATE": "SINAPI_{type}_{month}_{year}",',
    '"DOWNLOAD_FILENAME_TEMPLATE": "SINAPI-{year}-{month}-formato-xlsx",',
)
config.write_text(text)

downloader = Path('/app/AutoSINAPI/autosinapi/core/downloader.py')
text = downloader.read_text()
text = text.replace(
    'file_name = self.config.DOWNLOAD_FILENAME_TEMPLATE.format(type=tipo, month=mes, year=ano)',
    'file_name = self.config.DOWNLOAD_FILENAME_TEMPLATE.format(month=mes, year=ano)',
)
downloader.write_text(text)
PY
RUN apt-get update && \
    apt-get install -y git --no-install-recommends && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_AUTOSINAPI=0.1.0 pip install --no-cache-dir ./AutoSINAPI && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Estágio 3: Cópia do código da aplicação
COPY ./api /app/api
COPY alembic.ini /app/alembic.ini
COPY ./alembic /app/alembic
COPY ./docker/entrypoint.sh /app/entrypoint.sh

# Estágio 4: Segurança e Execução
RUN apt-get update && apt-get install -y wget procps --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chmod +x /app/entrypoint.sh
USER appuser

# Expõe a porta que o Uvicorn usará
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
# Inicia o servidor Uvicorn
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
