import os
from pathlib import Path
from functools import lru_cache
from dotenv import load_dotenv

# Resolve .env relative to this file's directory (backend/), not CWD
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

class Settings:
    PROJECT_NAME: str = "Universal Support Brain"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/v1"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/universal_support_brain")
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey")
    # CORS Origins: comma separated list of origins
    ALLOWED_CORS_ORIGINS: list[str] = [
        origin.strip() for origin in os.getenv("ALLOWED_CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
    ]
    API_KEY_HEADER_NAME: str = "X-API-Key"
    ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "admin-secret-key")

    # Integrations
    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    PINECONE_ENV: str = os.getenv("PINECONE_ENV", "us-east-1-aws")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Model Config
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_CHAT_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-4o-mini")
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-small")
    
@lru_cache()
def get_settings():
    return Settings()
