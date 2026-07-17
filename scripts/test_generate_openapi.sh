#!/usr/bin/env bash
# ============================================================
# AutoSINAPI (API) — Teste de integração da geração OpenAPI
#
# STORY-INFRA-004 — TDD de integração (runtime via Docker).
#
# Sobe a API em staging (docker compose: db + api), aguarda o
# endpoint /openapi.json ficar disponível, roda o gerador
# (scripts/generate_openapi.sh) e valida:
#   1. O YAML produzido é parseável e semanticamente igual ao schema
#      servido em runtime (sem perda de informação na conversão).
#   2. (Opcional) Passa no Spectral se disponível no PATH (espelha o
#      gate bloqueante do CI da STACK — SPEC-RULE 6.1).
#
# Uso:
#   ./scripts/test_generate_openapi.sh
#
# Requer: docker + docker compose no PATH.
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$API_REPO_DIR"

CONTAINER="${API_CONTAINER:-sinapi_api}"
OUTPUT="$(mktemp /tmp/openapi_test.XXXXXX.yaml)"
RULESET="${RULESET:-}"
MAX_WAIT="${MAX_WAIT:-60}"

cleanup() { rm -f "$OUTPUT"; }
trap cleanup EXIT

echo "→ Subindo staging (db + api)..."
# FIXME(INFRA-004): usa o compose do repo da API (sinapi_api). Em ambiente
# SSL o container real chama-se autosinapi_api; ajuste via API_CONTAINER.
docker compose up -d db redis
docker compose up -d --build api

echo "→ Aguardando /openapi.json (max ${MAX_WAIT}s)..."
elapsed=0
until docker exec "$CONTAINER" python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/openapi.json', timeout=5)" >/dev/null 2>&1; do
  if [ "$elapsed" -ge "$MAX_WAIT" ]; then
    echo "ERRO: timeout aguardando a API" >&2
    docker compose logs api | tail -30 >&2
    exit 1
  fi
  sleep 3
  elapsed=$((elapsed + 3))
done

echo "→ Rodando gerador..."
bash "$SCRIPT_DIR/generate_openapi.sh" "$OUTPUT"

echo "→ Validando YAML parseável e fidelidade ao runtime..."
python3 - "$OUTPUT" <<'PY'
import json, sys, yaml, urllib.request
out = sys.argv[1]
with open(out) as f:
    generated = yaml.safe_load(f)
runtime = json.loads(urllib.request.urlopen("http://localhost:8000/openapi.json", timeout=15).read())

def norm(o):
    if isinstance(o, dict): return {k: norm(v) for k, v in o.items()}
    if isinstance(o, list): return [norm(x) for x in o]
    if isinstance(o, str): return o.replace("\n", " ").strip()
    return o

assert norm(generated) == norm(runtime), "spec gerada diverge do runtime!"
assert generated.get("openapi", "").startswith("3."), "openapi version ausente"
assert len(generated.get("paths", {})) > 0, "paths ausentes"
print(f"OK: YAML fiel ao runtime ({len(generated['paths'])} paths)")
PY

if [ -n "$RULESET" ]; then
  if command -v spectral >/dev/null 2>&1; then
    echo "→ Spectral lint (gate SPEC-RULE 6.1)..."
    spectral lint --ruleset "$RULESET" "$OUTPUT"
  else
    echo "→ Spectral não instalado; usando npx (download temporário)..."
    npx --yes @stoplight/spectral-cli@6.16.1 lint --ruleset "$RULESET" "$OUTPUT"
  fi
fi

echo "✅ test_generate_openapi.sh passou"

# Encerra o staging para não deixar containers órfãos (soft).
docker compose down >/dev/null 2>&1 || true
