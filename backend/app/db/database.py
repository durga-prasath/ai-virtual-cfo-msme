# app/db/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Create engine with connection pooling
# pool_pre_ping=True verifies connections before using them (prevents stale connections)
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False  # Set True to see SQL queries in console (good for debugging)
)

# Session factory
# autocommit=False: We control transactions manually (critical for financial data)
# autoflush=False: Don't auto-send to DB until we explicitly commit
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()

# FastAPI dependency - provides a session per request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()