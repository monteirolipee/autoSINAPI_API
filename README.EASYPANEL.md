# Deploy no EasyPanel

Use este repositório como um fork de implantação. O submódulo `AutoSINAPI` deve apontar para um commit existente; a versão original apontava para um commit removido e não era reproduzível.

O workflow `.github/workflows/publish-easypanel-image.yml` publica a imagem de API/worker no GHCR. No EasyPanel, defina `AUTOSINAPI_IMAGE` com a imagem do seu fork, por exemplo `ghcr.io/seu-usuario/autosinapi-api:main`. Se o pacote for privado, configure a credencial do registry no EasyPanel.

## Serviço Compose

No EasyPanel, crie um serviço **Compose** apontando para este repositório e selecione `docker-compose.easypanel.yml` como arquivo Compose. Copie `.env.easypanel.example` para as variáveis do serviço e substitua todos os segredos.

Configure um único domínio HTTPS para o serviço interno `kong`, porta `8000`. Não publique PostgreSQL, Redis, API, worker ou Kong Admin.

O arquivo mantém volumes nomeados para:

- `postgres_data`: bancos `sinapi` e `kong`;
- `autosinapi_downloads`: arquivos baixados e processados pelo ETL;
- `celery_schedule`: estado do Celery Beat.

## Chave do Estakha

Gere uma chave alfanumérica, configure o mesmo valor em `ESTAKHA_SINAPI_API_KEY` nesta stack e em `SINAPI_API_KEY` no Estakha. Todas as rotas da API passam pelo `X-API-KEY`.

## Primeira carga

Depois do deploy, execute uma carga pela API administrativa:

```bash
curl -X POST https://sinapi-api.seudominio.com/api/v1/admin/populate-database \
  -H "Authorization: Bearer SEU_ADMIN_API_TOKEN" \
  -H "X-API-KEY: SUA_CHAVE_DO_ESTAKHA" \
  -H "Content-Type: application/json" \
  -d '{"year":2025,"month":10,"state":"SP"}'
```

O endpoint retorna um `task_id`. Consulte o status em `/api/v1/admin/tasks/{task_id}` com os mesmos headers. O Celery Beat executa o ETL mensal conforme `ETL_STATES` e `ETL_LOOKBACK_MONTHS`.

## Verificação

```bash
curl -H "X-API-KEY: SUA_CHAVE_DO_ESTAKHA" \
  "https://sinapi-api.seudominio.com/api/v1/public/filters"
```

As rotas sem `X-API-KEY` devem responder `401`.
