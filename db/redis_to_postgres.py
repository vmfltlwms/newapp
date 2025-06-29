import logging
from config import settings
logger = logging.getLogger(__name__)

class RedisToPostgres:
    """Redis 데이터를 PostgreSQL로 저장하는 개선된 워커"""
    
    def __init__(self, interval_seconds: int = 30, batch_size: int = 1000):
        """
        워커 초기화
        
        Args:
            interval_seconds: 워커 실행 간격 (초) - 짧게 설정하여 데이터 손실 방지
            batch_size: 한 번에 처리할 최대 레코드 수
        """
        self.interval_seconds = interval_seconds
        self.batch_size = batch_size
        self.is_running = False
        self.worker_task = None
        
        # 데이터베이스 연결 정보
        self.db_params = {
            "dbname": settings.PG_DATABASE,
            "user": settings.PG_USER,
            "password": settings.PG_PASSWORD,
            "host": settings.PG_HOST,
            "port": settings.PG_PORT
        }
        
        # 처리된 키를 추적하기 위한 세트
        self.processed_keys = set()
    