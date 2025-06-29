# crud/user_crud.py
from typing import List, Optional
from sqlmodel import select
from models.models import User
from db.postgres_db import PostgresDB
from services.base_crud import BaseCRUD
from schemas.user_schema import UserCreate, UserUpdate  # 스키마는 별도로 정의


class UserCRUD(BaseCRUD[User, UserCreate, UserUpdate]):
    def __init__(self, db: PostgresDB):
        super().__init__(User, db)

    async def get_by_email(self, email: str) -> Optional[User]:
        """이메일로 사용자 조회"""
        async with self.db.get_session() as session:
            statement = select(User).where(User.email == email)
            result = await session.execute(statement)
            return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        """사용자명으로 사용자 조회"""
        async with self.db.get_session() as session:
            statement = select(User).where(User.username == username)
            result = await session.execute(statement)
            return result.scalar_one_or_none()

    async def get_active_users(self) -> List[User]:
        """활성 사용자들 조회"""
        async with self.db.get_session() as session:
            statement = select(User).where(User.is_active == True)
            result = await session.execute(statement)
            return result.scalars().all()

    async def search_users(self, search_term: str) -> List[User]:
        """사용자 검색 (이름 또는 이메일)"""
        async with self.db.get_session() as session:
            statement = select(User).where(
                (User.username.contains(search_term)) | 
                (User.email.contains(search_term))
            )
            result = await session.execute(statement)
            return result.scalars().all()

    async def deactivate_user(self, user_id: int) -> Optional[User]:
        """사용자 비활성화"""
        async with self.db.get_session() as session:
            user = await self.get(user_id)
            if user:
                user.is_active = False
                session.add(user)
                await session.commit()
                await session.refresh(user)
            return user

    async def activate_user(self, user_id: int) -> Optional[User]:
        """사용자 활성화"""
        async with self.db.get_session() as session:
            user = await self.get(user_id)
            if user:
                user.is_active = True
                session.add(user)
                await session.commit()
                await session.refresh(user)
            return user