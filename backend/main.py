"""from fastapi import FastAPI
from app.api.billing.routes import router as billing_router

app = FastAPI()

app.include_router(billing_router, prefix="/billing", tags=["Billing"])

@app.get("/")
def home():
    return {"message": "AI Virtual CFO Backend Running"}"""
# backend/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.db.init_db import init_db

# Import routers (keep your existing ones)
from app.api.billing.routes import router as billing_router

from app.api.auth.routes import router as auth_router
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Initializing database...")
    init_db()
    yield
    # Shutdown (cleanup if needed)
    print("Application shutting down...")


app = FastAPI(
    title="AI Virtual CFO - MSME Platform",
    version="0.3.0",
    lifespan=lifespan,
    description="ERP-integrated fintech backend with GST, OCR & forecasting"
)

# Include your existing routers
app.include_router(billing_router, prefix="/api/v1")

# Public routes — no token needed
app.include_router(auth_router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "virtual-cfo-api"}


@app.get("/db-status")
def db_status():
    """Quick check that tables exist."""
    from app.db.database import engine
    from app.db.base import Base
    tables = list(Base.metadata.tables.keys())
    return {"tables_created": tables, "count": len(tables)}