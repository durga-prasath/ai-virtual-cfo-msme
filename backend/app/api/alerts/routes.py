# backend/app/api/alerts/routes.py

"""
ALERTS API ROUTES

Prefix: /api/v1/alerts  (mounted in main.py)

  GET   /api/v1/alerts                    — List alerts (filter: unread, severity, type)
  GET   /api/v1/alerts/summary            — Alert counts by severity
  POST  /api/v1/alerts/mark-read          — Bulk mark alerts as read
  POST  /api/v1/alerts/mark-all-read      — Mark ALL alerts as read
  POST  /api/v1/alerts/{id}/dismiss       — Dismiss a single alert
  POST  /api/v1/alerts/scan               — Manually trigger alert scan
"""

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.forecast_schema import (
    AlertResponseSchema,
    AlertMarkReadSchema,
    AlertsSummarySchema,
)
from app.services import alert_service

router = APIRouter(prefix="/alerts", tags=["Smart Alerts"])


@router.get("", response_model=List[AlertResponseSchema])
def list_alerts(
    unread_only: bool = Query(False),
    severity: Optional[str] = Query(None, description="low/medium/high/critical"),
    alert_type: Optional[str] = Query(None),
    include_dismissed: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List alerts for the current user with optional filters."""
    return alert_service.list_alerts(
        db, current_user.id,
        unread_only=unread_only,
        severity=severity,
        alert_type=alert_type,
        include_dismissed=include_dismissed,
        skip=skip,
        limit=limit,
    )


@router.get("/summary", response_model=AlertsSummarySchema)
def get_alerts_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns alert counts by severity (for dashboard badge counts)."""
    return alert_service.get_alerts_summary(db, current_user.id)


@router.post("/mark-read")
def mark_alerts_read(
    data: AlertMarkReadSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk mark specific alert IDs as read."""
    count = alert_service.mark_alerts_read(db, current_user.id, data.alert_ids)
    return {"marked_read": count}


@router.post("/mark-all-read")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all unread alerts as read."""
    count = alert_service.mark_all_read(db, current_user.id)
    return {"marked_read": count}


@router.post("/{alert_id}/dismiss", response_model=AlertResponseSchema)
def dismiss_alert(
    alert_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dismiss (soft-delete) a single alert."""
    return alert_service.dismiss_alert(db, current_user.id, alert_id)


@router.post("/scan")
def run_alert_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger the alert scan engine (idempotent — safe to call multiple times)."""
    count = alert_service.run_alert_scan(db, current_user.id)
    return {"new_alerts_created": count, "message": f"{count} new alert(s) generated."}
