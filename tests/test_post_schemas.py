"""
Testes para STORY-API-003: Schemas Pydantic para endpoints POST.

Valida que os 3 endpoints POST usam classes Pydantic dedicadas (não Body(...)
inline) com exemplos visíveis no Swagger (OpenAPI), conforme SPEC-RULE
Regra 2.3 e GUIDE-development.md seção 2.1.2.

Estratégia (TDD / DDD):
- AST: garante que nenhum parâmetro de rota POST em api/main.py usa Body(...)
  como default (refatoração obrigatória).
- OpenAPI runtime: garante que o requestBody de cada POST referencia um
  schema nomeado ($ref -> componente Pydantic) e que o exemplo está visível
  no schema do componente (Swagger mostra o exemplo).
"""
import ast
import os

import pytest
from fastapi.testclient import TestClient
from api.main import app

MAIN_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api", "main.py")

HTTP_DECORATORS = {"get", "post", "put", "delete", "patch", "options", "head"}

# path -> nome da classe Pydantic esperada como corpo da requisição
POST_ENDPOINTS = {
    "/api/v1/admin/populate-database": "PopulateDatabaseRequest",
    "/api/v1/public/bi/curva-abc": "CurvaABCRequest",
    "/api/v1/public/bi/curva-abc/por-classificacao": "CurvaABCRequest",
}


def _post_route_functions():
    """Retorna os nós FunctionDef das rotas POST definidas em api/main.py."""
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
                and dec.func.attr == "post"
            ):
                funcs.append(node)
                break
    return funcs


def _has_inline_body(func_node):
    """True se algum parâmetro da função tem default Body(...)."""
    defaults = list(func_node.args.defaults)
    defaults += [d for d in func_node.args.kw_defaults if d is not None]
    for d in defaults:
        if (
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Name)
            and d.func.id == "Body"
        ):
            return True
    return False


def _resolve_schema(openapi, schema):
    """Resolve o schema referenciado por $ref, se aplicável."""
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return name, openapi["components"]["schemas"][name]
    return None, schema


@pytest.fixture
def openapi():
    client = TestClient(app)
    return client.get("/openapi.json").json()


class TestPostSchemasNoInlineBody:
    def test_exactly_three_post_endpoints_exist(self):
        """STORY exige exatamente 3 endpoints POST refatorados."""
        assert len(_post_route_functions()) == 3

    def test_no_post_endpoint_uses_inline_body(self):
        """Nenhum parâmetro de rota POST pode ter default Body(...)."""
        for func in _post_route_functions():
            assert not _has_inline_body(func), (
                f"Rota POST '{func.name}' ainda usa Body(...) inline. "
                "Use uma classe Pydantic dedicada (SPEC-RULE Regra 2.3)."
            )


class TestPostSchemasOpenAPI:
    def test_request_bodies_reference_named_schemas(self, openapi):
        for path, expected_name in POST_ENDPOINTS.items():
            post = openapi["paths"][path]["post"]
            assert "requestBody" in post, f"{path}: sem requestBody"
            content = post["requestBody"]["content"]
            assert "application/json" in content, f"{path}: sem content application/json"
            schema = content["application/json"]["schema"]
            assert "$ref" in schema, (
                f"{path}: requestBody deve referenciar um schema Pydantic nomeado "
                f"($ref), não ser inline (Body(...))."
            )
            name = schema["$ref"].split("/")[-1]
            assert name == expected_name, (
                f"{path}: esperado schema '{expected_name}', obtido '{name}'"
            )

    def test_referenced_schemas_have_visible_example(self, openapi):
        components = openapi["components"]["schemas"]
        for schema_name in set(POST_ENDPOINTS.values()):
            assert schema_name in components, f"{schema_name} ausente em components"
            comp = components[schema_name]
            assert "example" in comp, (
                f"{schema_name}: schema deve conter 'example' visível no Swagger "
                "(json_schema_extra)."
            )

    def test_populate_database_schema_shape(self, openapi):
        comp = openapi["components"]["schemas"]["PopulateDatabaseRequest"]
        example = comp["example"]
        assert set(example.keys()) >= {"year", "month", "state"}
        props = comp["properties"]
        assert "year" in props and "month" in props and "state" in props
        # state preserva restrição de tamanho (UF de 2 letras)
        assert props["state"].get("maxLength") == 2
        assert props["state"].get("minLength") == 2

    def test_curva_abc_schema_shape(self, openapi):
        comp = openapi["components"]["schemas"]["CurvaABCRequest"]
        example = comp["example"]
        assert "codigos" in example
        props = comp["properties"]
        assert "codigos" in props
        assert props["codigos"].get("type") == "array"


class TestPostSchemasFunctional:
    """Smoke funcional: garante que os modelos Pydantic estão ativos e validando."""

    @pytest.fixture(autouse=True)
    def _admin_token(self, monkeypatch):
        # Endpoint admin exige ADMIN_API_TOKEN + header desde ADR/STORY-GOLIVE-03
        monkeypatch.setattr("api.main.settings.ADMIN_API_TOKEN", "test-admin-token")
        self.admin_headers = {"Authorization": "Bearer test-admin-token"}

    def test_populate_database_rejects_invalid_state(self):
        client = TestClient(app)
        # state "S" viola min_length=2 -> 422 de validação Pydantic
        resp = client.post(
            "/api/v1/admin/populate-database",
            headers=self.admin_headers,
            json={"year": 2025, "month": 9, "state": "S"},
        )
        assert resp.status_code == 422

    def test_populate_database_accepts_valid_body(self):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/admin/populate-database",
            headers=self.admin_headers,
            json={"year": 2025, "month": 9, "state": "SP"},
        )
        # Validação OK => não deve ser 422 (Redis/ETL pode dar 202 ou 409)
        assert resp.status_code != 422

    def test_curva_abc_rejects_non_list_codigos(self):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/public/bi/curva-abc"
            "?uf=SP&data_referencia=2025-09&regime=NAO_DESONERADO",
            json={"codigos": "nao-e-lista"},
        )
        assert resp.status_code == 422

    def test_curva_abc_accepts_valid_body(self):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/public/bi/curva-abc"
            "?uf=SP&data_referencia=2025-09&regime=NAO_DESONERADO",
            json={"codigos": [92711, 88307]},
        )
        # Validação OK => não deve ser 422 (DB pode ausentar dados -> 404/500)
        assert resp.status_code != 422
