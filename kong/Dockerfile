# Começa com a imagem oficial do Kong
FROM kong:3.4

# Mude temporariamente para o usuário root para ter permissão de instalar pacotes
USER root

# A imagem oficial pode variar entre Debian/Ubuntu e Alpine conforme a tag.
# Instala apenas o cliente PostgreSQL usado pelo container de migrações.
RUN if command -v apk >/dev/null 2>&1; then \
      apk add --no-cache postgresql-client; \
    elif command -v apt-get >/dev/null 2>&1; then \
      apt-get update \
      && apt-get install -y --no-install-recommends postgresql-client \
      && rm -rf /var/lib/apt/lists/*; \
    else \
      echo "Nenhum gerenciador de pacotes suportado encontrado" >&2; \
      exit 1; \
    fi


# IMPORTANTE: Retorna para o usuário padrão 'kong' por segurança
USER kong
