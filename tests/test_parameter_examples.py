"""
Testes para STORY-API-004 (corrigida via SPEC-2.2.1 / ADR-006, opção A):
Exemplos consistentes em parâmetros de domínio finito.

Conforme SPEC-RULE Regra 2.2 + Regra 2.2.1 (correção de compatibilidade com
FastAPI >= 0.115 / 0.135.1): a forma recomendada e NÃO-depreciada para
parâmetros de domínio finito é `examples={...}` (plural, media type do
OpenAPI), e NÃO mais `example=` (singular, depreciado pela biblioteca).

Estratégia (TDD / DDD):
- AST: todo parâmetro de domínio finito (`uf`, `regime`, `data_referencia`,
  `data_fim`) em `Query(...)` DEVE usar a keyword `examples=` (plural) e NUNCA
  a keyword `example=` (singular, depreciada).
- OpenAPI runtime: todo parâmetro de domínio finito expõe `examples` (plural)
  no nível do parâmetro, com valor; e NÃO expõe `example` (singular).
- `data_referencia` e `data_fim` sempre carregam exemplo no formato AAAA-MM.
"""
import ast
import os

import pytest
from fastapi.testclient import TestClient
from api.main import app

MAIN_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api", "main.py")

# Domínios finitos do modelo de negócio SINAPI (DDD): parâmetros cujo valor
# pertence a um conjunto enumerável e, portanto, exigem exemplo no contrato.
FINITE_DOMAIN_PARAMS = {"uf", "regime", "data_referencia", "data_fim"}

# Parâmetros de data cuja presença de exemplo é critério de aceitação.
DATE_PARAMS = {"data_referencia", "data_fim"}

HTTP_DECORATORS = {"get", "post", "put", "delete", "patch", "options", "head"}


def _route_functions():
    with open(MAIN_PATH, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    funcs = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and isinstance(dec.func.value, ast.Name)
                and dec.func.value.id == "app"
                and dec.func.attr in HTTP_DECORATORS
            ):
                funcs.append(node)
                break
    return funcs


def _all_query_params():
    """Yield (param_name, kwargs_dict) para todo param de rota com default Query(...)."""
    out = []
    for func in _route_functions():
        args = func.args.args
        defaults = func.args.defaults
        start = len(args) - len(defaults)
        for idx in range(len(args)):
            dflt = defaults[idx - start] if idx >= start else None
            if dflt is None:
                continue
            if (
                isinstance(dflt, ast.Call)
                and isinstance(dflt.func, ast.Name)
                and dflt.func.id == "Query"
            ):
                kw = {kw.arg: kw.value for kw in dflt.keywords if kw.arg}
                out.append((args[idx].arg, kw))
        for arg, dflt in zip(func.args.kwonlyargs, func.args.kw_defaults):
            if (
                dflt is not None
                and isinstance(dflt, ast.Call)
                and isinstance(dflt.func, ast.Name)
                and dflt.func.id == "Query"
            ):
                kw = {kw.arg: kw.value for kw in dflt.keywords if kw.arg}
                out.append((arg.arg, kw))
    return out


def _example_values(param):
    """Extrai valores de exemplo de `examples` (plural, media type).

    Em FastAPI 0.135.1 o `examples=` (plural) é emitido dentro de
    `schema.examples`; em versões futuras pode ir para o nível do parâmetro.
    Cobrimos ambos para resiliência a versão.
    """
    vals = []
    for container in (param.get("examples"), (param.get("schema") or {}).get("examples")):
        if not isinstance(container, dict):
            continue
        for entry in container.values():
            if isinstance(entry, dict):
                if "value" in entry:
                    vals.append(entry["value"])
                else:
                    vals.append(entry)
            else:
                vals.append(entry)
    return vals


def _has_singular_example(param):
    if param.get("example") is not None:
        return True
    return (param.get("schema") or {}).get("example") is not None


def _is_aaaa_mm(value):
    value = str(value)
    if len(value) != 7 or value[4] != "-":
        return False
    y, m = value.split("-")
    return y.isdigit() and m.isdigit() and 2000 <= int(y) <= 2100 and 1 <= int(m) <= 12


@pytest.fixture
def openapi():
    client = TestClient(app)
    return client.get("/openapi.json").json()


class TestSourceUsesPluralExamples:
    def test_finite_domain_query_uses_examples_not_example(self):
        for name, kw in _all_query_params():
            if name not in FINITE_DOMAIN_PARAMS:
                continue
            assert "example" not in kw, (
                f"Param '{name}': usa `example=` (singular, depreciado). "
                "Use `examples=` (plural) conforme SPEC-2.2.1 / ADR-006 (opção A)."
            )
            assert "examples" in kw, (
                f"Param '{name}': domínio finito deve usar `examples=` (plural)."
            )

    def test_no_singular_example_keyword_anywhere(self):
        """Nenhuma chamada Query(...) pode usar `example=` (singular)."""
        with open(MAIN_PATH, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Query"
            ):
                for kw in node.keywords:
                    assert kw.arg != "example", (
                        f"Query(...) com keyword `example` (singular) em {MAIN_PATH}. "
                        "Use `examples=` plural (SPEC-2.2.1 / ADR-006)."
                    )


class TestFiniteDomainParamsUseExamples:
    def test_finite_domain_has_plural_examples(self, openapi):
        violations = []
        for path, methods in openapi["paths"].items():
            for method, details in methods.items():
                if method == "parameters":
                    continue
                for param in details.get("parameters", []):
                    if param.get("name") not in FINITE_DOMAIN_PARAMS:
                        continue
                    if _has_singular_example(param):
                        violations.append(
                            f"{method.upper()} {path} {param['name']}: "
                            "tem `example` (singular) — proibido"
                        )
                        continue
                    if not _example_values(param):
                        violations.append(
                            f"{method.upper()} {path} {param['name']}: "
                            "sem `examples` (plural)"
                        )
        assert not violations, "Violações:\n" + "\n".join(violations)

    def test_date_params_have_example_everywhere(self, openapi):
        missing = []
        for path, methods in openapi["paths"].items():
            for method, details in methods.items():
                if method == "parameters":
                    continue
                for param in details.get("parameters", []):
                    if param.get("name") in DATE_PARAMS and not _example_values(param):
                        missing.append(f"{method.upper()} {path} ({param['name']})")
        assert not missing, (
            f"Parâmetros de data sem exemplo: {missing}"
        )

    def test_date_example_format_is_aaaa_mm(self, openapi):
        bad = []
        for path, methods in openapi["paths"].items():
            for method, details in methods.items():
                if method == "parameters":
                    continue
                for param in details.get("parameters", []):
                    if param.get("name") not in DATE_PARAMS:
                        continue
                    for v in _example_values(param):
                        if not _is_aaaa_mm(v):
                            bad.append(
                                f"{method.upper()} {path} ({param['name']}): "
                                f"exemplo='{v}'"
                            )
        assert not bad, f"Exemplos de data fora do padrão AAAA-MM: {bad}"
