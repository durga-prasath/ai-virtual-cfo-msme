# backend/app/db/init_db.py
from app.db.database import engine
from app.db.base import Base

# This import triggers all models to register with Base.metadata
from app.models import *  # noqa: F401


def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    print("✅ All database tables initialized successfully.")


if __name__ == "__main__":
    init_db()