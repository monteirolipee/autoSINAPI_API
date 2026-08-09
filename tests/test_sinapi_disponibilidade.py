"""
Testes para o módulo compartilhado de disponibilidade da base SINAPI
(ADR-034 / SPEC-RULE-BASE-MONITORING).

Cobre:
  - expected_latest_competence: calendário de publicação (competência M publicada
    ~dia 15 de M+1).
  - build_urls: padrão canônico da Caixa desde 2025
    (SINAPI-{year}-{month}-formato-xlsx.zip e -formato-pdf.zip).
  - resolve_status: comparação disponível × consumida.
  - compute_target_month: dirigido por calendário (não lookback fixo).

Funções puras: não dependem de banco nem de rede.
"""

import os
import sys
from datetime import date

import pytest

_AUTOSINAPI_PATH = os.path.join(os.path.dirname(__file__), "..", "AutoSINAPI")
if _AUTOSINAPI_PATH not in sys.path:
    sys.path.insert(0, _AUTOSINAPI_PATH)

from api.sinapi_disponibilidade import (  # noqa: E402
    expected_latest_competence,
    build_urls,
    resolve_status,
    compute_target_month,
    probe_url,
    discover_available_base,
)


# ─────────────────────────────────────────────────────────────
# B2.1 Calendário de publicação
# ─────────────────────────────────────────────────────────────

class TestExpectedLatestCompetence:
    def test_day_before_publish_returns_mminus2(self):
        # 08/08/2026 (antes do dia 15): competência publicada mais recente = junho/2026
        assert expected_latest_competence(date(2026, 8, 8)) == "2026-06"

    def test_day_after_publish_returns_mminus1(self):
        # 20/08/2026 (após dia 15): julho/2026 publicado
        assert expected_latest_competence(date(2026, 8, 20)) == "2026-07"

    def test_january_before_publish_rolls_year(self):
        # 05/01/2027: competência de novembro/2026 (rollover de ano)
        assert expected_latest_competence(date(2027, 1, 5)) == "2026-11"

    def test_march_after_publish_rolls_year(self):
        # 20/03/2027: fevereiro/2027
        assert expected_latest_competence(date(2027, 3, 20)) == "2027-02"

    def test_exact_publish_day(self):
        # Exatamente no dia 15: considera publicado (>= publish_day)
        assert expected_latest_competence(date(2026, 8, 15)) == "2026-07"


# ─────────────────────────────────────────────────────────────
# B1 Padrão canônico de arquivo
# ─────────────────────────────────────────────────────────────

class TestBuildUrls:
    def test_returns_xlsx_and_pdf_candidates(self):
        urls = build_urls("2026-07")
        assert urls == [
            "https://www.caixa.gov.br/Downloads/sinapi-a-vista-composicoes/SINAPI-2026-07-formato-xlsx.zip",
            "https://www.caixa.gov.br/Downloads/sinapi-a-vista-composicoes/SINAPI-2026-07-formato-pdf.zip",
        ]

    def test_uses_dash_and_formato_pattern_not_legacy(self):
        # Regressão: não deve gerar o padrão legado SINAPI_REFERENCIA_MM_YYYY
        urls = build_urls("2026-07")
        assert all("SINAPI_REFERENCIA" not in u for u in urls)
        assert all("SINAPI-2026-07-formato-" in u for u in urls)


# ─────────────────────────────────────────────────────────────
# B3.2 resolve_status
# ─────────────────────────────────────────────────────────────

class TestResolveStatus:
    def test_equal_is_current(self):
        assert resolve_status("2026-06", "2026-06") == "current"

    def test_available_newer_is_new_base_available(self):
        assert resolve_status("2026-07", "2026-06") == "new-base-available"

    def test_available_older_is_suspicious(self):
        assert resolve_status("2026-05", "2026-06") == "suspicious"

    def test_available_none_is_unknown(self):
        assert resolve_status(None, "2026-06") == "unknown"

    def test_both_none_is_unknown(self):
        assert resolve_status(None, None) == "unknown"


# ─────────────────────────────────────────────────────────────
# B5 ETL dirigido por calendário
# ─────────────────────────────────────────────────────────────

class TestComputeTargetMonth:
    def test_target_before_publish_is_mminus2(self):
        # 08/08/2026 → competência 2026-06
        assert compute_target_month(date(2026, 8, 8)) == (2026, 6)

    def test_target_after_publish_is_mminus1(self):
        # 20/08/2026 → competência 2026-07
        assert compute_target_month(date(2026, 8, 20)) == (2026, 7)

    def test_target_uses_injected_today(self):
        assert compute_target_month(date(2027, 1, 5)) == (2026, 11)


# ─────────────────────────────────────────────────────────────
# B2.2 Probe de URL (nunca crasha; 200 → confirmado)
# ─────────────────────────────────────────────────────────────

class TestProbeUrl:
    def test_returns_true_on_200(self, monkeypatch):
        class _Resp:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
        def _open(req, timeout=None):
            assert req.method == "HEAD"
            return _Resp()
        monkeypatch.setattr("api.sinapi_disponibilidade._urlopen", _open)
        assert probe_url("https://example.invalid/SINAPI-2026-07-formato-xlsx.zip") is True

    def test_falls_back_to_get_when_head_fails(self, monkeypatch):
        calls = {"n": 0}
        class _Resp:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
        def _open(req, timeout=None):
            calls["n"] += 1
            if req.method == "HEAD":
                raise OSError("head blocked")
            return _Resp()
        monkeypatch.setattr("api.sinapi_disponibilidade._urlopen", _open)
        assert probe_url("https://example.invalid/x.zip") is True
        assert calls["n"] == 2  # HEAD + fallback GET

    def test_returns_false_when_all_fail(self, monkeypatch):
        def _open(req, timeout=None):
            raise OSError("boom")
        monkeypatch.setattr("api.sinapi_disponibilidade._urlopen", _open)
        assert probe_url("https://example.invalid/x.zip") is False


# ─────────────────────────────────────────────────────────────
# B2.3/B4.3 discover_available_base (ordem de precedência)
# ─────────────────────────────────────────────────────────────

class TestDiscoverAvailableBase:
    def test_calendar_confirmed_by_probe_wins(self):
        comp, source, sources = discover_available_base(
            today=date(2026, 8, 20),
            probe_fn=lambda c: True,
        )
        assert comp == "2026-07"
        assert source == "portal"
        assert "portal" in sources

    def test_probe_blocked_keeps_calendar_unconfirmed(self):
        comp, source, sources = discover_available_base(
            today=date(2026, 8, 8),
            probe_fn=lambda c: False,
        )
        assert comp == "2026-06"  # calendário mantido (B4.3)
        assert source == "calendar"
        assert sources == ["calendar"]

    def test_sources_list_only_calendar_when_blocked(self):
        comp, source, sources = discover_available_base(
            today=date(2026, 8, 8),
            probe_fn=lambda c: False,
        )
        assert sources == ["calendar"]
