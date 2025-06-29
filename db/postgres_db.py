# postgres_db.py
import logging
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
from config import settings

logger = logging.getLogger(__name__)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


class PostgresDB:
    def __init__(self):
        self.database_url = (
            f"postgresql+asyncpg://{settings.PG_USER}:{settings.PG_PASSWORD}"
            f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DATABASE}"
        )
        self.engine: AsyncEngine = create_async_engine(
            self.database_url, 
            echo=True,
            pool_size=10,
            max_overflow=20
        )
        self.session_factory = sessionmaker(
            self.engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
    # 🔧 SQLAlchemy 로거들 비활성화
    logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.ERROR)
    logging.getLogger('sqlalchemy.dialects').setLevel(logging.ERROR)
    logging.getLogger('sqlalchemy.orm').setLevel(logging.ERROR)
        
    async def initialize(self):
        """테이블 자동 생성"""
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
            logger.info("✅ DB 테이블 생성 완료")

    @asynccontextmanager
    async def get_session(self):
        """컨텍스트 매니저로 세션 제공 - 자동으로 세션 닫기"""
        session = self.session_factory()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def get_raw_session(self) -> AsyncSession:
        """원시 세션 제공 (수동으로 관리해야 함)"""
        return self.session_factory()
          
    async def close_db(self):
        """비동기 엔진 종료 (커넥션 풀 반납 포함)"""
        await self.engine.dispose()
        logger.info("🛑 DB 커넥션 풀 종료 완료")

    async def health_check(self) -> bool:
        """DB 연결 상태 확인"""
        try:
            async with self.get_session() as session:
                await session.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"DB 연결 실패: {e}")
            return False