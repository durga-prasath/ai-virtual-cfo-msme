# backend/main.py

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.db.init_db import init_db
from app.api.auth.routes import router as auth_router
from app.api.billing.routes import router as billing_router
from app.api.payments.routes import router as payments_router
from app.api.gst.routes import router as gst_router
from app.api.invoices.routes import router as purchases_router
from app.api.forecasting.routes import router as forecasting_router
from app.api.alerts.routes import router as alerts_router
from app.api.erp.routes import router as erp_router
from app.api.ocr.routes import router as ocr_router
from app.api.chatbot.routes import router as chatbot_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing database...")
    init_db()
    yield
    print("Application shutting down...")


app = FastAPI(
    title="AI Virtual CFO - MSME Platform",
    version="0.8.0",
    lifespan=lifespan,
    description="ERP-integrated fintech backend with GST, OCR, Forecasting, Smart Alerts & Revenue Ledger"
)


frontend_url_env = os.getenv("FRONTEND_URL", "http://localhost:3000,http://localhost:5173")
allowed_origins = [origin.strip() for origin in frontend_url_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(billing_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")
app.include_router(gst_router, prefix="/api/v1")
app.include_router(purchases_router, prefix="/api/v1")
app.include_router(forecasting_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(erp_router, prefix="/api/v1")
app.include_router(ocr_router, prefix="/api/v1")
app.include_router(chatbot_router, prefix="/api/v1")



@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "virtual-cfo-api"}


@app.get("/db-status")
def db_status():
    from app.db.base import Base
    tables = list(Base.metadata.tables.keys())
    return {"tables_created": tables, "count": len(tables)}
