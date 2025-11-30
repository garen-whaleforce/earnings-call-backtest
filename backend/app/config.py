from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # FMP API
    fmp_api_key: str = ""
    fmp_base_url: str = "https://financialmodelingprep.com/api/v3"

    # OpenAI
    openai_api_key: str = ""

    # Finnhub API
    finnhub_api_key: str = ""
    finnhub_base_url: str = "https://finnhub.io/api/v1"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "earnings-backtest"
    minio_secure: bool = False

    # App settings
    min_market_cap: float = 1_000_000_000  # 1B
    price_change_threshold: float = 0.10  # 10%

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
