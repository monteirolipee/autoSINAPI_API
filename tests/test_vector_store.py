"""
Testes unitários da camada vetorial (ADR-006 / STORY-SRC-004, Fase 4).

Cobrem a lógica pura do vector_store sem exigir Postgres/SQL real:
  - naming de tabelas `vec_<dims>_<slug>`
  - parsing da resposta do Ollama `/api/embed`
  - fallback do provider quando o primário falha (mock de urllib)
  - naming invariante dos modelos registry
"""
import pytest

from api import vector_store
from api.vector_store import EmbeddingProvider, _ollama_embed, table_name


class TestNaming:
    def test_table_name_bge_m3(self):
        assert table_name(1024, "bge_m3") == "vec_1024_bge_m3"

    def test_table_name_nomic(self):
        assert table_name(768, "nomic_embed_text") == "vec_768_nomic_embed_text"

    def test_registry_slugs_have_dimensions(self):
        for slug, meta in vector_store.VECTOR_MODELS.items():
            assert meta["dims"] > 0
            assert meta["model_name"]
            assert table_name(meta["dims"], slug).startswith("vec_")


class TestOllamaEmbedParsing:
    def test_parses_embeddings_array(self, monkeypatch):
        class FakeResp:
            def read(self):
                return b'{"model":"bge-m3","embeddings":[[0.1,0.2],[0.3,0.4]]}'
            def __exit__(self, *a):
                return False
            def __enter__(self):
                return self

        class FakeUrlopen:
            def __init__(self, req, timeout):
                self.req = req
                assert req.get_header("Content-type") == "application/json"
                assert req.get_method() == "POST"
            def __enter__(self):
                return FakeResp()
            def __exit__(self, *a):
                return False

        monkeypatch.setattr(vector_store.urllib.request, "urlopen", FakeUrlopen)
        out = _ollama_embed("http://x:11434", "bge-m3", ["a", "b"], 5)
        assert out == [[0.1, 0.2], [0.3, 0.4]]

    def test_supports_dict_style_data(self, monkeypatch):
        class FakeUrlopen:
            def __init__(self, req, timeout):
                pass
            def __enter__(self):
                return type(
                    "R", (), {"read": lambda self: b'{"data":[{"embedding":[1.0]},{"embedding":[2.0]}]}'}
                )()
            def __exit__(self, *a):
                return False

        monkeypatch.setattr(vector_store.urllib.request, "urlopen", FakeUrlopen)
        out = _ollama_embed("http://x:11434", "bge-m3", ["a"], 5)
        assert out == [[1.0], [2.0]]

    def test_empty_input_returns_empty(self):
        assert _ollama_embed("http://x:11434", "bge-m3", [], 5) == []


class TestProviderFallback:
    def test_primary_failure_falls_back(self, monkeypatch):
        server_state = {"calls": []}

        def fake_urlopen(req, timeout):
            server_state["calls"].append(req.full_url)
            if "100.69.111.112" in req.full_url:
                raise RuntimeError("primário fora")
            return type(
                "R",
                (),
                {
                    "read": lambda self: b'{"embeddings":[[9.0,9.0]]}',
                    "__enter__": lambda self: self,
                    "__exit__": lambda self, *a: False,
                },
            )()

        monkeypatch.setattr(vector_store.urllib.request, "urlopen", fake_urlopen)
        provider = EmbeddingProvider(
            primary_url="http://100.69.111.112:11434",
            primary_model="bge-m3",
            fallback_url="http://server-ollama:11434",
            fallback_model="nomic-embed-text",
        )
        out = provider.embed(["texto"])
        assert out == [[9.0, 9.0]]
        assert server_state["calls"][0].startswith("http://100.69.111.112")
        assert server_state["calls"][1].startswith("http://server-ollama")

    def test_both_primary_and_fallback_fail_returns_empty(self, monkeypatch):
        def fake_urlopen(req, timeout):
            raise RuntimeError("fora do ar")

        monkeypatch.setattr(vector_store.urllib.request, "urlopen", fake_urlopen)
        provider = EmbeddingProvider(
            primary_url="http://p:1", fallback_url="http://f:1",
        )
        assert provider.embed(["x"]) == []

    def test_empty_texts_skips_network(self, monkeypatch):
        def fake_urlopen(req, timeout):
            raise AssertionError("não deveria chamar a rede")

        monkeypatch.setattr(vector_store.urllib.request, "urlopen", fake_urlopen)
        provider = EmbeddingProvider(primary_url="http://p:1")
        assert provider.embed([]) == []