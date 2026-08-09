"""sinapi_disponibilidade.py — Comparação da base SINAPI disponível × consumida.

Módulo compartilhado (SSOT) para o monitoramento da disponibilidade da base SINAPI
(ADR-034 / SPEC-RULE-BASE-MONITORING). Usado pela API (`api/main.py`) e pelo alerter
(kong) — sem duplicação de lógica.

Funções puras (sem banco/rede) permitem TDD completo e reutilização em ambos os
ambientes:

- `expected_latest_competence`: calendário de publicação (competência M publicada
  ~dia 15 de M+1).
- `build_urls`: padrão canônico da Caixa desde 2025
  (`SINAPI-{year}-{month}-formato-xlsx.zip` / `-formato-pdf.zip`).
- `resolve_status`: comparação disponível × consumida.
- `compute_target_month`: dirigido por calendário (não lookback fixo).
"""

import os
import urllib.request
from datetime import date
from typing import Callable, List, Optional, Tuple

# Portal de downloads da Caixa (SSOT com autodinapi/config.py BASE_URL).
PORTAL_BASE_URL = os.getenv(
    "SINAPI_PORTAL_BASE_URL",
    "https://www.caixa.gov.br/Downloads/sinapi-a-vista-composicoes",
)

# Padrão canônico de arquivo (B1.1): a Caixa publica desde 2025 os relatórios em
# dois ZIPs com este padrão. O template legado `SINAPI_{type}_{month}_{year}` não
# deve ser usado para URLs (B1.2).
_FILE_TEMPLATES = (
    "SINAPI-{year}-{month}-formato-xlsx.zip",
    "SINAPI-{year}-{month}-formato-pdf.zip",
)

# Dia de publicação aproximado (B2.1): a competência M é publicada ~dia 15 de M+1.
PUBLISH_DAY = 15


def _shift_month(year: int, month: int, delta: int) -> Tuple[int, int]:
    """Retorna (year, month) deslocados por `delta` meses (suporta rollover)."""
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def expected_latest_competence(today: date, publish_day: int = PUBLISH_DAY) -> str:
    """Competência publicada mais recente, conforme calendário SINAPI (B2.1).

    A competência `M` (mês de referência dos dados) é publicada ~dia 15 de `M+1`.
    Logo:
      - `today.day >= publish_day` → a competência do mês anterior foi publicada;
      - senão → a última publicada é a de dois meses atrás.

    Ex.: 08/08/2026 → "2026-06"; 20/08/2026 → "2026-07".
    """
    delta = -1 if today.day >= publish_day else -2
    year, month = _shift_month(today.year, today.month, delta)
    return f"{year:04d}-{month:02d}"


def build_urls(competencia: str, base_url: str = PORTAL_BASE_URL) -> List[str]:
    """URLs candidatas do relatório no portal da Caixa (B1).

    Usa o padrão canônico `SINAPI-{year}-{month}-formato-{xlsx,pdf}.zip`.
    """
    year, month = competencia.split("-")
    return [
        f"{base_url}/{template.format(year=year, month=month)}"
        for template in _FILE_TEMPLATES
    ]


def resolve_status(
    available: Optional[str], consumed: Optional[str]
) -> str:
    """Status da base comparando disponível × consumida (B3.2).

    - `current`           → disponível == consumida;
    - `new-base-available`→ disponível > consumida (relatório novo para ingerir);
    - `suspicious`        → disponível < consumida (regressão/inconsistência);
    - `unknown`           → disponível desconhecida.
    """
    if available is None:
        return "unknown"
    if consumed is None:
        return "new-base-available" if available else "unknown"
    if available == consumed:
        return "current"
    if available > consumed:
        return "new-base-available"
    return "suspicious"


def compute_target_month(today: Optional[date] = None) -> Tuple[int, int]:
    """Mês-alvo do ETL dirigido por calendário (B5.1).

    Em vez de `lookback` fixo, usa a competência realmente publicada.
    Retorna `(year, month)` da competência-alvo (ex.: 08/08/2026 → (2026, 6)).
    """
    today = today or date.today()
    comp = expected_latest_competence(today)
    year, month = comp.split("-")
    return int(year), int(month)


def _urlopen(req, timeout=None):
    return urllib.request.urlopen(req, timeout=timeout)


def probe_url(url: str, timeout: float = 5.0) -> bool:
    """Confirma se uma URL responde 200 (B2.2).

    Primeiro tenta HEAD; se o servidor bloquear HEAD (WAF/Azion), cai para GET
    raso. Toda exceção é capturada — o probe NUNCA crasha o chamador
    (ADR-033 R2.3). 200 → confirmado; 429/302/timeout → False.
    """
    for method in ("HEAD", "GET"):
        try:
            with _urlopen(urllib.request.Request(url, method=method), timeout=timeout) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            continue
    return False


def discover_available_base(
    today: Optional[date] = None,
    probe_fn: Optional[Callable[[str], bool]] = None,
    base_url: str = PORTAL_BASE_URL,
) -> Tuple[Optional[str], str, List[str]]:
    """Descobre a base disponível seguindo a ordem de precedência (B2.3).

    1. `calendar` — calendário de publicação (fonte principal, B2.1);
    2. `portal` — calendário confirmado por probe (200, B2.2).

    Quando o probe está bloqueado (429/302/timeout), a competência do
    calendário permanece como `available_base` com `source == "calendar"`
    (B4.3) — não se degrada para `db_max`, pois isso esconderia a chegada de
    uma base mais nova (status viraria `current` incorretamente).

    Retorna `(competencia, source, sources)`. `sources` registra a cadeia de
    fontes consultadas para a API reportar origem (B4.3).
    """
    today = today or date.today()
    calendar_comp = expected_latest_competence(today)
    if probe_fn is None:
        probe_fn = lambda c: any(probe_url(u, timeout=5.0) for u in build_urls(c, base_url))

    if probe_fn(calendar_comp):
        return calendar_comp, "portal", ["calendar", "portal"]
    return calendar_comp, "calendar", ["calendar"]
