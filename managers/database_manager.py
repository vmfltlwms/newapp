# crud/base_crud.py
from typing import Generic, TypeVar, Type, List, Optional, Any, Dict
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from db.postgres_db import PostgresDB

# Generic 타입 정의
ModelType = TypeVar("ModelType", bound=SQLModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=SQLModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=SQLModel)


class BaseCRUD(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType], db: PostgresDB):
        self.model = model
        self.db = db

    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        """새로운 레코드 생성"""
        async with self.db.get_session() as session:
            db_obj = self.model.from_orm(obj_in) if hasattr(self.model, 'from_orm') else self.model(**obj_in.dict())
            session.add(db_obj)
            await session.commit()
            await session.refresh(db_obj)
            return db_obj

    async def get(self, id: Any) -> Optional[ModelType]:
        """ID로 단일 레코드 조회"""
        async with self.db.get_session() as session:
            statement = select(self.model).where(self.model.id == id)
            result = await session.execute(statement)
            return result.scalar_one_or_none()

    async def get_multi(
        self, 
        skip: int = 0, 
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ModelType]:
        """여러 레코드 조회 (페이징 및 필터링 지원)"""
        async with self.db.get_session() as session:
            statement = select(self.model)
            
            # 필터 적용
            if filters:
                for key, value in filters.items():
                    if hasattr(self.model, key):
                        statement = statement.where(getattr(self.model, key) == value)
            
            statement = statement.offset(skip).limit(limit)
            result = await session.execute(statement)
            return result.scalars().all()

    async def update(self, id: Any, obj_in: UpdateSchemaType) -> Optional[ModelType]:
        """기존 레코드 업데이트"""
        async with self.db.get_session() as session:
            db_obj = await self.get(id)
            if not db_obj:
                return None
            
            obj_data = obj_in.dict(exclude_unset=True)
            for key, value in obj_data.items():
                setattr(db_obj, key, value)
            
            session.add(db_obj)
            await session.commit()
            await session.refresh(db_obj)
            return db_obj

    async def delete(self, id: Any) -> bool:
        """레코드 삭제"""
        async with self.db.get_session() as session:
            db_obj = await self.get(id)
            if not db_obj:
                return False
            
            await session.delete(db_obj)
            await session.commit()
            return True

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """레코드 개수 세기"""
        async with self.db.get_session() as session:
            statement = select(self.model)
            
            if filters:
                for key, value in filters.items():
                    if hasattr(self.model, key):
                        statement = statement.where(getattr(self.model, key) == value)
            
            result = await session.execute(statement)
            return len(result.scalars().all())

    async def exists(self, id: Any) -> bool:
        """레코드 존재 여부 확인"""
        db_obj = await self.get(id)
        return db_obj is not None