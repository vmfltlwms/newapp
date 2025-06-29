# crud/baseline_crud.py (싱글톤 버전) - Updated with low_price and high_price
from asyncio.log import logger
from typing import List, Optional, Dict, Any
from dependency_injector.wiring import inject, Provide
from sqlmodel import select
from db.postgres_db import PostgresDB
from container.postgres_container import Postgres_Container
from models.models import BaseLine

@inject
class BaselineModule():
    def __init__(self, 
                postgres_db: PostgresDB = Provide[Postgres_Container.postgres_db]):
      self.postgres_db = postgres_db


    async def initialize(self):
      pass
    
    async def shutdown(self):
      pass


    # 기존 메서드들은 그대로 유지
    async def create_new(self, 
                        stock_code: str, 
                        decision_price: int, 
                        quantity: int,
                        low_price: Optional[int] = None,
                        high_price: Optional[int] = None) -> Optional[BaseLine]:
        """해당 코드에 베이스라인이 없다면 step 0으로 새로운 베이스라인 생성"""
        async with self.postgres_db.get_session() as session:
            # 해당 종목의 베이스라인이 존재하는지 확인
            existing_baselines = await self.get_all_by_code(stock_code)
            
            if existing_baselines:
                raise ValueError(f"종목 {stock_code}에 이미 베이스라인이 존재합니다")
            
            # step 0으로 새 베이스라인 생성
            new_baseline = BaseLine(
                stock_code=stock_code,
                step=0,
                decision_price=decision_price,
                quantity=quantity,
                low_price=low_price,
                high_price=high_price
            )
            
            session.add(new_baseline)
            await session.commit()
            await session.refresh(new_baseline)
            return new_baseline

    async def get_all_by_code(self, stock_code: str) -> List[BaseLine]:
        """특정 종목 코드로 모든 베이스라인 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(BaseLine).where(BaseLine.stock_code == stock_code)
            result = await session.execute(statement)
            return result.scalars().all()
          
    async def get_last_step(self, stock_code: str) -> Optional[int]:
        """특정 종목 코드의 마지막(최대) step 반환"""
        async with self.postgres_db.get_session() as session:
            statement = select(BaseLine.step).where(
                BaseLine.stock_code == stock_code
            ).order_by(BaseLine.step.desc()).limit(1)
            result = await session.execute(statement)
            last_step = result.scalar_one_or_none()
            return last_step

    async def get_last_baseline(self, stock_code: str) -> Optional[BaseLine]:
        """특정 종목 코드의 마지막 step에 해당하는 베이스라인 객체 반환"""
        async with self.postgres_db.get_session() as session:
            statement = select(BaseLine).where(
                BaseLine.stock_code == stock_code
            ).order_by(BaseLine.step.desc()).limit(1)
            result = await session.execute(statement)
            return result.scalar_one_or_none()
          
    async def get_by_step(self, stock_code: str, step: int) -> Optional[BaseLine]:
        """종목 코드와 단계로 특정 베이스라인 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(BaseLine).where(
                (BaseLine.stock_code == stock_code) & 
                (BaseLine.step == step)
            )
            result = await session.execute(statement)
            return result.scalar_one_or_none()

    async def delete_by_code(self, stock_code: str) -> int:
        """특정 종목의 모든 베이스라인 삭제"""
        async with self.postgres_db.get_session() as session:
            statement = select(BaseLine).where(BaseLine.stock_code == stock_code)
            result = await session.execute(statement)
            baselines = result.scalars().all()
            
            count = len(baselines)
            for baseline in baselines:
                await session.delete(baseline)
            
            await session.commit()
            logger.info(f"{stock_code} 삭삭제완료")
            
            return count

    async def delete_by_step(self, stock_code: str, step: int) -> bool:
        """특정 종목의 특정 step 베이스라인 삭제"""
        async with self.postgres_db.get_session() as session:
            statement = select(BaseLine).where(
                (BaseLine.stock_code == stock_code) & 
                (BaseLine.step == step)
            )
            result = await session.execute(statement)
            baseline = result.scalar_one_or_none()
            
            if not baseline:
                return False
            
            await session.delete(baseline)
            await session.commit()
            return True

    async def add_step(self, 
                      stock_code: str, 
                      decision_price: int, 
                      quantity: int,
                      low_price: Optional[int] = None,
                      high_price: Optional[int] = None) -> BaseLine:
        """특정 종목에 새로운 step의 베이스라인 추가 (자동으로 다음 step 번호 부여)"""
        async with self.postgres_db.get_session() as session:
            # 현재 마지막 step 조회
            last_step = await self.get_last_step(stock_code)
            next_step = (last_step + 1) if last_step else 1
            
            # 새 베이스라인 생성
            new_baseline = BaseLine(
                stock_code=stock_code,
                step=next_step,
                decision_price=decision_price,
                quantity=quantity,
                low_price=low_price,
                high_price=high_price
            )
            
            session.add(new_baseline)
            await session.commit()
            await session.refresh(new_baseline)
            return new_baseline
     
    async def update_by_step(self, 
                            stock_code: str, 
                            step: int, 
                            new_price: int, 
                            new_quantity: int,
                            low_price: Optional[int] = None,
                            high_price: Optional[int] = None) -> Optional[BaseLine]:
        """특정 종목과 단계의 수량 업데이트"""
        baseline = await self.get_by_step(stock_code, step)
        if not baseline:
            return None
        
        async with self.postgres_db.get_session() as session:
            baseline.decision_price = new_price
            baseline.quantity = new_quantity
            baseline.low_price = low_price
            baseline.high_price = high_price
            session.add(baseline)
            await session.commit()
            await session.refresh(baseline)
            return baseline
          
    async def delete_last_step(self, stock_code: str) -> bool:
        """특정 종목의 마지막 step 베이스라인 삭제"""
        async with self.postgres_db.get_session() as session:
            # 마지막 step 조회
            last_step = await self.get_last_step(stock_code)
            
            if last_step is None:
                return False
            
            # 마지막 step의 베이스라인 조회 및 삭제
            statement = select(BaseLine).where(
                (BaseLine.stock_code == stock_code) & 
                (BaseLine.step == last_step)
            )
            result = await session.execute(statement)
            baseline = result.scalar_one_or_none()
            
            if not baseline:
                return False
            
            await session.delete(baseline)
            await session.commit()
            return True

    async def get_all_baseline(self) -> List[BaseLine]:
        """모든 베이스라인 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(BaseLine)
            result = await session.execute(statement)
            return result.scalars().all()

    # 추가적으로 유용할 수 있는 메서드들

    async def get_all_baseline_ordered_by_code(self) -> List[BaseLine]:
        """모든 베이스라인을 종목 코드 순으로 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(BaseLine).order_by(BaseLine.stock_code, BaseLine.step)
            result = await session.execute(statement)
            return result.scalars().all()

    async def get_all_stock_codes(self) -> List[str]:
        """베이스라인에 등록된 모든 종목 코드 조회 (중복 제거)"""
        async with self.postgres_db.get_session() as session:
            statement = select(BaseLine.stock_code).distinct()
            result = await session.execute(statement)
            return result.scalars().all()

    async def count_total_baselines(self) -> int:
        """전체 베이스라인 개수 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(BaseLine)
            result = await session.execute(statement)
            baselines = result.scalars().all()
            return len(baselines)

    async def get_baseline_summary(self) -> Dict[str, Any]:
        """베이스라인 전체 요약 정보"""
        async with self.postgres_db.get_session() as session:
            # 전체 베이스라인 조회
            statement = select(BaseLine)
            result = await session.execute(statement)
            all_baselines = result.scalars().all()
            
            # 통계 계산
            total_count = len(all_baselines)
            unique_stocks = set(baseline.stock_code for baseline in all_baselines)
            stock_count = len(unique_stocks)
            
            # 종목별 step 개수
            stock_steps = {}
            for baseline in all_baselines:
                if baseline.stock_code not in stock_steps:
                    stock_steps[baseline.stock_code] = []
                stock_steps[baseline.stock_code].append(baseline.step)
            
            return {
                "total_baselines": total_count,
                "unique_stocks": stock_count,
                "stock_codes": list(unique_stocks),
                "stock_step_counts": {code: len(steps) for code, steps in stock_steps.items()},
                "max_steps_per_stock": max([len(steps) for steps in stock_steps.values()]) if stock_steps else 0,
                "min_steps_per_stock": min([len(steps) for steps in stock_steps.values()]) if stock_steps else 0
            }