# api/realtime_group_module.py
from typing import List, Optional
from dependency_injector.wiring import inject, Provide
from sqlmodel import select
from db.postgres_db import PostgresDB
from container.postgres_container import Postgres_Container
from schemas.realtime_group_schema import Realtime_Group

@inject
class RealtimeGroupModule():
    def __init__(self, 
                postgres_db: PostgresDB = Provide[Postgres_Container.postgres_db],):
        self.postgres_db = postgres_db

    async def initialize(self):
        pass
    
    async def shutdown(self):
        pass

    async def create_new(self, 
                        group: int, 
                        data_type: List[str], 
                        stock_code: List[str],
                        strategy: int = 1) -> Optional[Realtime_Group]:
        """새로운 실시간 그룹 생성"""
        async with self.postgres_db.get_session() as session:
            # 해당 그룹이 이미 존재하는지 확인
            existing_group = await self.get_by_group(group)
            
            if existing_group:
                raise ValueError(f"그룹 {group}이 이미 존재합니다")
            
            # 새 실시간 그룹 생성
            new_group = Realtime_Group(
                group=group,
                strategy=strategy,
                data_type=data_type,
                stock_code=stock_code
            )
            
            session.add(new_group)
            await session.commit()
            await session.refresh(new_group)
            return new_group

    async def update_by_group(self, 
                              group: int, 
                              strategy: Optional[int] = None,
                              data_type: Optional[List[str]] = None, 
                              stock_code: Optional[List[str]] = None) -> Optional[Realtime_Group]:
        """특정 그룹의 전략, 데이터 타입 및 종목 코드 업데이트"""
        async with self.postgres_db.get_session() as session:
            # 기존 그룹 조회
            statement = select(Realtime_Group).where(Realtime_Group.group == group)
            result = await session.execute(statement)
            existing_group = result.scalar_one_or_none()
            
            if not existing_group:
                return None
            
            # 업데이트할 필드가 있으면 업데이트
            if strategy is not None:
                existing_group.strategy = strategy
            if data_type is not None:
                existing_group.data_type = data_type
            if stock_code is not None:
                existing_group.stock_code = stock_code
            
            session.add(existing_group)
            await session.commit()
            await session.refresh(existing_group)
            return existing_group

    async def get_by_group(self, group: int) -> Optional[Realtime_Group]:
        """특정 그룹 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(Realtime_Group).where(Realtime_Group.group == group)
            result = await session.execute(statement)
            return result.scalar_one_or_none()

    async def get_all_groups(self) -> List[Realtime_Group]:
        """모든 실시간 그룹 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(Realtime_Group)
            result = await session.execute(statement)
            return result.scalars().all()
          
    async def delete_by_group(self, group: int) -> bool:
        """특정 그룹 삭제"""
        async with self.postgres_db.get_session() as session:
            statement = select(Realtime_Group).where(Realtime_Group.group == group)
            result = await session.execute(statement)
            existing_group = result.scalar_one_or_none()
            
            if not existing_group:
                return False
            
            await session.delete(existing_group)
            await session.commit()
            return True

    async def update_strategy(self, group: int, new_strategy: int) -> Optional[Realtime_Group]:
        """특정 그룹의 전략만 업데이트"""
        async with self.postgres_db.get_session() as session:
            statement = select(Realtime_Group).where(Realtime_Group.group == group)
            result = await session.execute(statement)
            existing_group = result.scalar_one_or_none()
            
            if not existing_group:
                return None
            
            existing_group.strategy = new_strategy
            session.add(existing_group)
            await session.commit()
            await session.refresh(existing_group)
            return existing_group
        """모든 실시간 그룹 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(Realtime_Group)
            result = await session.execute(statement)
            return result.scalars().all()

    async def add_stock_to_group(self, group: int, new_stock_code: str) -> Optional[Realtime_Group]:
        """특정 그룹에 종목 코드 추가"""
        async with self.postgres_db.get_session() as session:
            statement = select(Realtime_Group).where(Realtime_Group.group == group)
            result = await session.execute(statement)
            existing_group = result.scalar_one_or_none()
            
            if not existing_group:
                return None
            
            # 중복 확인 후 추가
            if new_stock_code not in existing_group.stock_code:
                existing_group.stock_code = existing_group.stock_code + [new_stock_code]
                session.add(existing_group)
                await session.commit()
                await session.refresh(existing_group)
            
            return existing_group

    async def remove_stock_from_group(self, group: int, stock_code_to_remove: str) -> Optional[Realtime_Group]:
        """특정 그룹에서 종목 코드 제거"""
        async with self.postgres_db.get_session() as session:
            statement = select(Realtime_Group).where(Realtime_Group.group == group)
            result = await session.execute(statement)
            existing_group = result.scalar_one_or_none()
            
            if not existing_group:
                return None
            
            # 해당 종목 코드가 있으면 제거
            if stock_code_to_remove in existing_group.stock_code:
                updated_stock_codes = [code for code in existing_group.stock_code if code != stock_code_to_remove]
                existing_group.stock_code = updated_stock_codes
                session.add(existing_group)
                await session.commit()
                await session.refresh(existing_group)
            
            return existing_group
