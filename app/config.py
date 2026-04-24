from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/app.db"
    API_KEY: str = "changeme"
    MAX_UPLOAD_MB: int = 50
    ANTHROPIC_API_KEY: str = ""
    ODOO_ENABLED: bool = False
    ODOO_URL: str = ""
    ODOO_DB: str = ""
    ODOO_USERNAME: str = ""
    ODOO_PASSWORD: str = ""
    DUPLICATE_AMOUNT_TOLERANCE: float = 1.00
    PAGE_DPI: int = 120
    MAX_CONCURRENT_PAGES: int = 4
    BASIC_AUTH_USER: str = ""
    BASIC_AUTH_PASS: str = ""

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
