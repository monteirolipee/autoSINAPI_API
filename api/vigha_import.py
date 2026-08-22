"""Importador em lote dos catálogos SINAPI publicados pelo portal VIGHA."""

import json
import logging
from datetime import date
from urllib.request import Request, urlopen

from sqlalchemy import text

from .database import engine

logger = logging.getLogger("autosinapi.vigha_import")

UFs = ("AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO")
BASE_URL = "https://sinapi.vighapp.com/data"


def _get_json(url: str):
    request = Request(url, headers={"User-Agent": "AutoSINAPI/1.0"})
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def _chunks(rows, size=500):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def _upsert_catalog(connection, table: str, rows: list[dict]):
    if not rows:
        return 0
    if table == "composicoes":
        query = text("""
            INSERT INTO composicoes (codigo, descricao, unidade, status)
            VALUES (:codigo, :descricao, :unidade, 'ATIVO')
            ON CONFLICT (codigo) DO UPDATE SET
              descricao = EXCLUDED.descricao, unidade = EXCLUDED.unidade,
              updated_at = now()
        """)
    else:
        query = text("""
            INSERT INTO insumos (codigo, descricao, unidade, classificacao, status)
            VALUES (:codigo, :descricao, :unidade, :classificacao, 'ATIVO')
            ON CONFLICT (codigo) DO UPDATE SET
              descricao = EXCLUDED.descricao, unidade = EXCLUDED.unidade,
              classificacao = EXCLUDED.classificacao, updated_at = now()
        """)
    count = 0
    for batch in _chunks(rows):
        connection.execute(query, batch)
        count += len(batch)
    return count


def _upsert_prices(connection, table: str, rows: list[dict]):
    if not rows:
        return 0
    is_supply = table.startswith("precos")
    code_column = "insumo_codigo" if is_supply else "composicao_codigo"
    value_column = "preco_mediano" if is_supply else "custo_total"
    query = text(f"""
        INSERT INTO {table} ({code_column}, uf, data_referencia, regime, {value_column})
        VALUES (:codigo, :uf, :data_referencia, :regime, :valor)
        ON CONFLICT DO UPDATE SET {value_column} = EXCLUDED.{value_column}, updated_at = now()
    """)
    count = 0
    for batch in _chunks(rows):
        connection.execute(query, batch)
        count += len(batch)
    return count


def import_vigha_catalog(year: int = 2026, months: list[int] | None = None, states: list[str] | None = None, include_desonerado: bool = True) -> dict:
    months = months or list(range(1, 7))
    states = [s.upper() for s in (states or list(UFs))]
    regimes = (("", "NAO_DESONERADO"), ("D", "DESONERADO")) if include_desonerado else (("", "NAO_DESONERADO"),)
    totals = {"composicoes": 0, "insumos": 0, "custos_composicoes": 0, "precos_insumos": 0, "arquivos": 0}
    errors = []

    with engine.begin() as connection:
        for month in months:
            reference_date = date(year, month, 1)
            period = f"{year}{month:02d}"
            for uf in states:
                for suffix, regime in regimes:
                    prefix = f"{uf}{suffix}"
                    try:
                        compositions = _get_json(f"{BASE_URL}/composicao/{prefix}{period}.json")
                        supplies = _get_json(f"{BASE_URL}/insumo/{prefix}/{period}/{prefix}{period}.json")
                        comp_catalog = []
                        comp_prices = []
                        for item in compositions:
                            code = int(item["Codigo"])
                            comp_catalog.append({"codigo": code, "descricao": item.get("Descricao", ""), "unidade": item.get("Unidade") or "UN"})
                            if item.get("Custo") is not None:
                                comp_prices.append({"codigo": code, "uf": uf, "data_referencia": reference_date, "regime": regime, "valor": item["Custo"]})
                        supply_catalog = []
                        supply_prices = []
                        for item in supplies:
                            code = int(item["Codigo"])
                            supply_catalog.append({"codigo": code, "descricao": item.get("Descricao", ""), "unidade": item.get("Unidade") or "UN", "classificacao": item.get("Tipo")})
                            if item.get("Custo") is not None:
                                supply_prices.append({"codigo": code, "uf": uf, "data_referencia": reference_date, "regime": regime, "valor": item["Custo"]})
                        totals["composicoes"] += _upsert_catalog(connection, "composicoes", comp_catalog)
                        totals["insumos"] += _upsert_catalog(connection, "insumos", supply_catalog)
                        totals["custos_composicoes"] += _upsert_prices(connection, "custos_composicoes_mensal", comp_prices)
                        totals["precos_insumos"] += _upsert_prices(connection, "precos_insumos_mensal", supply_prices)
                        totals["arquivos"] += 2
                    except Exception as exc:
                        errors.append({"uf": uf, "year": year, "month": month, "regime": regime, "error": str(exc)})
                        logger.warning("Falha VIGHA %s %s/%s (%s): %s", uf, month, year, regime, exc)
    return {"status": "SUCESSO" if not errors else "SUCESSO_COM_AVISOS", **totals, "erros": errors[:50], "total_erros": len(errors)}
