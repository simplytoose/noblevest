import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "NobleVest API"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "replace-with-random-64-char-string"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://noblevest:strongpassword123@db:5432/noblevest"
    
    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # JWT
    JWT_ACCESS_SECRET: str = "replace-with-random-access-secret-64-chars"
    JWT_REFRESH_SECRET: str = "replace-with-random-refresh-secret-64-chars"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Email
    SMTP_HOST: str = "smtp.sendgrid.net"
    SMTP_PORT: int = 587
    SMTP_USER: str = "apikey"
    SMTP_PASSWORD: str = "your-sendgrid-api-key"
    EMAIL_FROM: str = "noreply@noblevest.com"
    ADMIN_EMAIL: str = "admin@noblevest.com"

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,https://noblevest.com,http://localhost:8000,http://127.0.0.1:3000"

    # Market Data
    MARKET_DATA_PROVIDER: str = "simulation"
    MARKET_DATA_API_KEY: str = ""

    # Admin Seeding
    FIRST_ADMIN_EMAIL: str = "admin@noblevest.com"
    FIRST_ADMIN_PASSWORD: str = "Admin123!"

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env") if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")) else None,
        extra="ignore"
    )

settings = Settings()
