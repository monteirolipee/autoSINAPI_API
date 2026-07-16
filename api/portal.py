import os
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import schemas
from .database import get_db

router = APIRouter(tags=["tier_1", "Portal"])


@router.get(
    "/api/v1/portal/me",
    summary="Obter dados do portal do assinante",
    response_description="Plano, validade, quota usada/limite, features e links de upgrade/downgrade",
    response_model=schemas.PortalResponse,
    responses={
        401: {"description": "API key ausente ou inválida (header X-API-KEY)."},
    },
)
def portal_me(
    x_api_key: str = Header(..., alias="X-API-KEY"),
    db: Session = Depends(get_db),
):
    key_row = db.execute(
        text("""
            SELECT k.id as key_id, k.client_id, k.subscription_id,
                   k.status as key_status,
                   s.status as sub_status,
                   s.current_period_start, s.current_period_end,
                   p.slug as plan_slug, p.name as plan_name,
                   p.max_requests, p.duration_days,
                   p.price_cents, p.features::text as features
            FROM saas.api_keys k
            JOIN saas.subscriptions s ON s.id = k.subscription_id
            JOIN saas.plans p ON p.id = s.plan_id
            WHERE k.key_value = :key_value
        """),
        {"key_value": x_api_key},
    ).mappings().first()

    if not key_row:
        raise HTTPException(status_code=401, detail="API key inválida ou não encontrada")

    import json
    features = key_row["features"]
    if isinstance(features, str):
        features = json.loads(features)

    usage_row = db.execute(
        text("""
            SELECT COUNT(*) as total
            FROM saas.usage_logs
            WHERE api_key_id = :key_id
              AND requested_at >= :period_start
              AND requested_at <= :period_end
        """),
        {
            "key_id": key_row["key_id"],
            "period_start": key_row["current_period_start"],
            "period_end": key_row["current_period_end"],
        },
    ).mappings().first()

    total_used = usage_row["total"] if usage_row else 0
    limit = key_row["max_requests"]
    pct = round((total_used / limit) * 100, 1) if limit > 0 else 0.0

    frontend_base = os.getenv("FRONTEND_BASE_URL", "https://autosinapi.mundoaec.com")

    plan_slug = key_row["plan_slug"]
    upgrade_links = {}
    if plan_slug == "starter":
        upgrade_links = {
            "pro": f"{frontend_base}/checkout?plan=pro",
            "business": f"{frontend_base}/checkout?plan=business",
        }
    elif plan_slug == "pro":
        upgrade_links = {
            "business": f"{frontend_base}/checkout?plan=business",
        }

    def _fmt_ts(ts):
        return ts.isoformat() if ts else None

    return schemas.PortalResponse(
        client_id=key_row["client_id"],
        plan=schemas.PlanInfo(
            slug=plan_slug,
            name=key_row["plan_name"],
            price_cents=key_row["price_cents"],
        ),
        subscription={
            "status": key_row["sub_status"],
            "current_period_start": _fmt_ts(key_row["current_period_start"]),
            "current_period_end": _fmt_ts(key_row["current_period_end"]),
        },
        quota=schemas.QuotaInfo(
            used=total_used,
            limit=limit,
            percentage=pct,
        ),
        features=features,
        links=schemas.PortalLinks(
            upgrade=upgrade_links,
            downgrade=f"{frontend_base}/checkout?plan=starter"
            if plan_slug != "starter"
            else None,
            renew=f"{frontend_base}/checkout?plan={plan_slug}",
        ),
    )
