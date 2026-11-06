# app/core/config.py
import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Virtual CFO Platform"
    VERSION: str = "0.8.0"
    
    # PostgreSQL Connection (Render/Supabase will supply DATABASE_URL env variable)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:1974@localhost:5432/ai_cfo_db"
    )
    
    # Security & JWT (Render env will override SECRET_KEY)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "1974-virtual-cfo-dev-insecure-key")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Gemini AI Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    # Frontend URL (for CORS)
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000,http://localhost:5173")

    class Config:
        case_sensitive = True

settings = Settings()

if settings.DATABASE_URL and settings.DATABASE_URL.startswith("postgres://"):
    settings.DATABASE_URL = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)
