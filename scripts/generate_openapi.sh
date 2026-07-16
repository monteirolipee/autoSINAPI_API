#!/usr/bin/env bash
# ============================================================
# AutoSINAPI (API) — Gerador de OpenAPI Spec versionada
#
# STORY-INFRA-004 / SPEC-RULE Regra 2.6 + GUIDE-development.md 3.3
#
# Extrai a spec em runtime da API AutoSINAPI e converte para YAML
# versionado. A lógica de GERAÇÃO vive neste repo (API), respeitando
# a separação por camada; o artefato resultante (SSOT) é versionado
# no repo da STACK (stacks/autosinapi/docs/openapi.yaml) — ver ADR-010.
#
# Origens suportadas (precedência):
#   1. API_URL  -> HTTP GET (ex.: http://localhost:8000/openapi.json)
#   2. docker exec no container (default: sinapi_api, via API_CONTAINER)
#
# Uso:
#   ./scripts/generate_openapi.sh [OUTPUT]
#   API_URL=http://localhost:8000 ./scripts/generate_openapi.sh docs/openapi.yaml
#   API_CONTAINER=sinapi_api ./scripts/generate_openapi.sh
#
# Requer: python3 com PyYAML (disponível na imagem da API e no host de CI).
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# scripts/ -> raiz do repo da API
API_REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

OUTPUT="${1:-$API_REPO_DIR/docs/openapi.yaml}"
CONTAINER="${API_CONTAINER:-sinapi_api}"
API_URL="${API_URL:-}"
OPENAPI_PATH="${OPENAPI_PATH:-/openapi.json}"
MAX_RETRIES="${MAX_RETRIES:-5}"
RETRY_DELAY="${RETRY_DELAY:-3}"

mkdir -p "$(dirname "$OUTPUT")"
TMP_JSON="$(mktemp /tmp/openapi_runtime.XXXXXX.json)"

cleanup() { rm -f "$TMP_JSON"; }
trap cleanup EXIT

fetch_openapi() {
  # Tenta até MAX_RETRIES (resiliência: a API pode estar inicializando).
  local attempt=1
  while :; do
    if [ -n "$API_URL" ]; then
      if curl -fsS --max-time 15 "$API_URL$OPENAPI_PATH" > "$TMP_JSON" 2>/tmp/openapi_err.txt; then
        return 0
      fi
    else
      if docker exec "$CONTAINER" python3 -c \
          "import urllib.request,sys; sys.stdout.write(urllib.request.urlopen('http://localhost:8000$OPENAPI_PATH', timeout=15).read().decode())" \
          > "$TMP_JSON" 2>/tmp/openapi_err.txt; then
        return 0
      fi
    fi
    if [ "$attempt" -ge "$MAX_RETRIES" ]; then
      echo "ERRO: falha ao extrair spec (tentativa $attempt/$MAX_RETRIES)" >&2
      cat /tmp/openapi_err.txt >&2
      return 1
    fi
    echo "→ tentativa $attempt falhou; retry em ${RETRY_DELAY}s..." >&2
    sleep "$RETRY_DELAY"
    attempt=$((attempt + 1))
  done
}

echo "→ Extraindo spec de runtime (origem: ${API_URL:-container $CONTAINER}) ..."
if ! fetch_openapi; then
  exit 1
fi

echo "→ Convertendo para YAML: $OUTPUT"
python3 - "$TMP_JSON" "$OUTPUT" <<'PY'
import json, sys, yaml

src, dst = sys.argv[1], sys.argv[2]
with open(src) as f:
    spec = json.load(f)

spec.setdefault("openapi", "3.1.0")

# Reordena chaves principais para legibilidade e diff estável (idempotente).
ORDER = ("openapi", "info", "servers", "paths", "components")
ordered = {}
for k in ORDER:
    if k in spec:
        ordered[k] = spec.pop(k)
ordered.update(spec)  # preserva quaisquer chaves extras

with open(dst, "w") as f:
    # width=88 casa o wrap da spec versionada (SSOT em stacks/autosinapi/docs/
    # openapi.yaml), garantindo diff estável e mínimo a cada regeneração.
    yaml.safe_dump(
        ordered, f,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=88,
    )
print("OK ->", dst)
PY

echo "✅ Spec OpenAPI atualizada em $OUTPUT"
