# ADR 003 — Transição para Programação Assíncrona (FastAPI + asyncpg)

## Status
Aprovado

## Contexto
O AutoSINAPI foi projetado para atuar como uma API de alta concorrência em leituras (Read-Heavy), precisando suportar picos de tráfego de até 10.000 requisições por minuto de construtoras, ERPs e agentes de IA.

Atualmente, todos os endpoints do FastAPI e as consultas de banco de dados são síncronos. Sob alta carga de requisições, o loop de eventos do FastAPI fica com suas threads de processamento bloqueadas aguardando o I/O do banco de dados (PostgreSQL síncrono via `psycopg2`). Isso gera gargalos significativos de concorrência, alto consumo de memória e timeouts, comprometendo a escalabilidade e a eficiência energética do servidor.

## Decisão
Adotaremos programação assíncrona de ponta a ponta na API:
1.  Redefinir todos os endpoints de `/api/` como `async def`.
2.  Substituir o engine síncrono do SQLAlchemy em `database.py` por uma sessão assíncrona (`create_async_engine` + `async_sessionmaker`) utilizando o driver **`asyncpg`** (dialeto: `postgresql+asyncpg`).
3.  Migrar as queries lógicas do `crud.py` para utilizar await em chamadas de banco (ex: `await db.execute(query)`).

## Consequências
*   **Positivas:**
    *   **Alta Concorrência:** O FastAPI consegue gerenciar milhares de conexões simultâneas em uma única thread de CPU, sem bloquear o loop de eventos.
    *   **Eficiência de Recursos:** Redução massiva do consumo de memória RAM e ciclos de CPU por requisição, otimizando o gasto energético do servidor.
    *   **Menor Latência:** O driver `asyncpg` é significativamente mais rápido em benchmarks do que o driver síncrono `psycopg2`.
*   **Negativas:**
    *   Exige refatoração de todo o código atual do `crud.py` e rotas do `main.py`.
    *   Aumento da complexidade do código devido ao uso explícito de `async`/`await`.
