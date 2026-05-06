# app/core/config.py
import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Virtual CFO Platform"
    VERSION: str = "0.1.0"
    
    # PostgreSQL Connection
    DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:1974@localhost:5432/virtual_cfo_db"
)
    
    # Security (for later when you add JWT auth)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "1974")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        case_sensitive = True

settings = Settings()