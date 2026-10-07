from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Ikigai API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:4321",
        "https://ikigai.local",
    ]

    # Supabase Infrastructure Configuration
    SUPABASE_URL: Optional[str] = "https://placeholder-project.supabase.co"
    SUPABASE_ANON_KEY: Optional[str] = "placeholder-anon-key"
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_JWT_SECRET: Optional[str] = "development-secret-for-jwt-verification-min-32-chars-long"

    # Database URL (Direct or Supabase Transaction Pooler)
    DATABASE_URL: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
