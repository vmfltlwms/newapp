from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import List

load_dotenv()  # .env 파일 수동 로드 (옵션)

# 기본 host 설정
REAL_HOST = 'https://api.kiwoom.com'
MOCK_HOST = 'https://mockapi.kiwoom.com'
REAL_SOCKET = 'wss://api.kiwoom.com:10000/api/dostk/websocket'
MOCK_SOCKET = 'wss://mockapi.kiwoom.com:10000/api/dostk/websocket'

class Settings(BaseSettings):
    APP_NAME: str = "키움 트레이딩 API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # 키움 API 설정 
    KIWOOM_APP_KEY: str
    KIWOOM_SECRET_KEY: str
    KIWOOM_SERVER: bool = False

    # 환경 설정
    WEBSOCKET_TIMEOUT: int = 30
    RECONNECT_MAX_RETRIES: int = 5
    RECONNECT_DELAY: int = 5
    KEEP_ALIVE_INTERVAL: int = 60

    LOG_LEVEL: str = "INFO"
    WS_HEARTBEAT_INTERVAL: int = 30

    @property
    def HOST(self) -> str:
        return REAL_HOST if self.KIWOOM_SERVER else MOCK_HOST

    @property
    def SOCKET(self) -> str:
        return REAL_SOCKET if self.KIWOOM_SERVER else MOCK_SOCKET

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # PostgreSQL
    PG_USER: str = "postgres"
    PG_PASSWORD: str = "1111"
    PG_HOST: str = "localhost"
    PG_PORT: str = "5432"
    PG_DATABASE: str = "kiwoomdb"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    class Config:
        env_file = ".env"
        extra = "ignore"
settings = Settings()
