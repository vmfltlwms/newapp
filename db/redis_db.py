import redis.asyncio as redis
import logging
from config import settings

logger = logging.getLogger(__name__)

class RedisDB:
    """Redis 연결 및 작업을 관리하는 모듈"""
    
    def __init__(self):
        self.redis_db = None
    
    async def initialize(self):
        """Redis 연결을 초기화합니다."""
        try:
            self.redis_db = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                decode_responses=True
            )
            # Redis 연결 테스트
            result = await self.redis_db.ping()
            logger.info("Redis connection established")
            logging.info("✅ Redis 연결 초기화 완료")
            return self.redis_db
        except Exception as e:
            logger.error(f"Redis connection error: {e}")
            raise
    
    async def close(self):
        """Redis 연결을 종료합니다."""
        if self.redis_db:
            await self.redis_db.close()
            self.redis_db = None
            logger.info("Redis connection closed")
    
    def get_connection(self):
        """현재 Redis 연결을 반환합니다."""
        if self.redis_db is None:
            raise Exception("Redis connection not initialized")
        return self.redis_db