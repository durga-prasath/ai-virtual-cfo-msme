# backend/app/api/forecasting/routes.py

"""
FORECASTING & DASHBOARD API ROUTES

Prefix: /api/v1/cfo  (mounted in main.py)

  POST  /api/v1/cfo/forecast          — Generate cash flow forecast (1–12 periods)
  GET   /api/v1/cfo/forecasts         — List saved forecasts
  GET   /api/v1/cfo/dashboard         — Full Virtual CFO dashboard snapshot
"""

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.forecast_schema import (
    ForecastRequestSchema,
    ForecastListResponse,
    ForecastResponseSchema,
    CashFlowDashboardSchema,
)
from app.services import forecasting_service, alert_service

router = APIRouter(prefix="/cfo", tags=["Virtual CFO — Forecasting & Dashboard"])


@router.post("/forecast", response_model=ForecastListResponse, status_code=201)
def generate_forecast(
    request: ForecastRequestSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a multi-period cash flow forecast using historical data.
    - Uses moving average + trend on past 12 months of payments and purchases.
    - Scenario: optimistic (+15% inflow), baseline, or pessimistic (-15% inflow).
    - Auto-creates alerts if negative or thin cash flow is predicted.
    - Returns all period forecasts + summary totals.
    """
    return forecasting_service.generate_forecast(db, current_user.id, request)


@router.get("/forecasts", response_model=List[ForecastResponseSchema])
def list_forecasts(
    forecast_type: Optional[str] = Query(None, description="daily/weekly/monthly/quarterly"),
    scenario: Optional[str] = Query(None, description="optimistic/baseline/pessimistic"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List previously generated forecasts for this user."""
    return forecasting_service.list_forecasts(
        db, current_user.id, forecast_type=forecast_type,
        scenario=scenario, limit=limit,
    )


@router.get("/dashboard", response_model=CashFlowDashboardSchema)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full Virtual CFO Dashboard snapshot.
    Aggregates: YTD revenue, receivables aging, GST payable, payables, cash position,
    monthly revenue trend, upcoming obligations, and active alert counts.
    Also runs the auto-alert scan (idempotent — no duplicate alerts per day).
    """
    # Run alert scan before building dashboard (so counts are up to date)
    alert_service.run_alert_scan(db, current_user.id)
    return forecasting_service.get_dashboard(db, current_user.id)
