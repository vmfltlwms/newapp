#step_manager_module.py

from asyncio.log import logger  
from typing import List, Optional, Dict, Any
from dependency_injector.wiring import inject, Provide
from sqlmodel import select, and_, or_
from db.postgres_db import PostgresDB
from container.postgres_container import Postgres_Container
from models.models import StepManager
from datetime import datetime

@inject
class StepManagerModule():
    def __init__(self, 
                postgres_db: PostgresDB = Provide[Postgres_Container.postgres_db]):
        self.postgres_db = postgres_db

    async def initialize(self):
        pass
    
    async def shutdown(self):
        pass

    # 기본 CRUD 메서드들
    async def create_new(self, 
                        code: str,
                        type: bool,
                        market: str,
                        final_price: int,
                        total_qty: int,
                        trade_qty: int = 0,
                        trade_step: int = 0,
                        hold_qty: Optional[int] = None,
                        last_trade_time: Optional[datetime] = None,
                        last_trade_prices: Optional[List[int]] = None) -> Optional[StepManager]:
        """새로운 스텝 매니저 생성"""
        # hold_qty가 None이면 total_qty - trade_qty로 설정
        if hold_qty is None:
            hold_qty = total_qty - trade_qty
        
        # last_trade_prices가 None이면 빈 리스트로 설정
        if last_trade_prices is None:
            last_trade_prices = []
            
        async with self.postgres_db.get_session() as session:
            # 해당 코드에 이미 스텝매니저가 존재하는지 확인
            existing = await self.get_by_code(code)
            if existing:
                raise ValueError(f"종목 {code}에 이미 스텝매니저가 존재합니다")
            
            new_step_manager = StepManager(
                code=code,
                type=type,
                market=market,
                final_price=final_price,
                total_qty=total_qty,
                trade_qty=trade_qty,
                trade_step=trade_step,
                hold_qty=hold_qty,
                last_trade_time=last_trade_time
            )
            
            # last_trade_prices 설정
            new_step_manager.last_trade_prices = last_trade_prices
            
            session.add(new_step_manager)
            await session.commit()
            await session.refresh(new_step_manager)
            return new_step_manager

    async def get_by_code(self, code: str) -> Optional[StepManager]:
        """종목 코드로 스텝 매니저 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(StepManager).where(StepManager.code == code)
            result = await session.execute(statement)
            return result.scalar_one_or_none()

    async def get_all(self) -> List[StepManager]:
        """모든 스텝 매니저 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(StepManager)
            result = await session.execute(statement)
            return result.scalars().all()

    async def get_by_market(self, market: str) -> List[StepManager]:
        """시장별 스텝 매니저 조회"""
        async with self.postgres_db.get_session() as session:
            if market.lower() == "all":
                statement = select(StepManager)
            else:
                statement = select(StepManager).where(StepManager.market == market)
            result = await session.execute(statement)
            return result.scalars().all()

    async def get_by_type(self, type_value: bool) -> List[StepManager]:
        """타입별 스텝 매니저 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(StepManager).where(StepManager.type == type_value)
            result = await session.execute(statement)
            return result.scalars().all()

    async def get_by_trade_step(self, trade_step: int) -> List[StepManager]:
        """거래 단계별 스텝 매니저 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(StepManager).where(StepManager.trade_step == trade_step)
            result = await session.execute(statement)
            return result.scalars().all()

    async def update_by_code(self, 
                            code: str,
                            final_price: Optional[int] = None,
                            total_qty: Optional[int] = None,
                            trade_qty: Optional[int] = None,
                            trade_step: Optional[int] = None,
                            hold_qty: Optional[int] = None,
                            last_trade_time: Optional[datetime] = None,
                            last_trade_prices: Optional[List[int]] = None) -> Optional[StepManager]:
        """종목 코드로 스텝 매니저 업데이트"""
        step_manager = await self.get_by_code(code)
        if not step_manager:
            return None
        
        async with self.postgres_db.get_session() as session:
            if final_price is not None:
                step_manager.final_price = final_price
            if total_qty is not None:
                step_manager.total_qty = total_qty
            if trade_qty is not None:
                step_manager.trade_qty = trade_qty
            if trade_step is not None:
                step_manager.trade_step = trade_step
            if hold_qty is not None:
                step_manager.hold_qty = hold_qty
            if last_trade_time is not None:
                step_manager.last_trade_time = last_trade_time
            if last_trade_prices is not None:
                step_manager.last_trade_prices = last_trade_prices
            
            step_manager.updated_at = datetime.now()
            session.add(step_manager)
            await session.commit()
            await session.refresh(step_manager)
            return step_manager

    async def update_trade_info(self, 
                               code: str,
                               trade_qty: int,
                               trade_step: int,
                               trade_price: int) -> Optional[StepManager]:
        """거래 정보 업데이트 (거래 수량, 단계, 가격)"""
        step_manager = await self.get_by_code(code)
        if not step_manager:
            return None
        
        async with self.postgres_db.get_session() as session:
            step_manager.trade_qty = trade_qty
            step_manager.trade_step = trade_step
            step_manager.last_trade_time = datetime.now()
            step_manager.hold_qty = step_manager.total_qty - trade_qty
            
            # 새로운 거래 가격을 리스트에 추가
            step_manager.add_trade_price(trade_price)
            
            step_manager.updated_at = datetime.now()
            
            session.add(step_manager)
            await session.commit()
            await session.refresh(step_manager)
            return step_manager

    async def add_trade_price(self, 
                             code: str, 
                             trade_price: int) -> Optional[StepManager]:
        """특정 종목의 거래 가격을 리스트에 추가하고 단계 +1"""
        step_manager = await self.get_by_code(code)
        if not step_manager:
            return None
        
        async with self.postgres_db.get_session() as session:
            # 거래 가격 추가
            step_manager.add_trade_price(trade_price)
            # 단계 +1
            step_manager.trade_step += 1
            step_manager.updated_at = datetime.now()
            
            session.add(step_manager)
            await session.commit()
            await session.refresh(step_manager)
            return step_manager

    async def delete_trade_price(self, code: str) -> Optional[StepManager]:
        """특정 종목의 마지막 거래 가격을 제거하고 단계 -1"""
        step_manager = await self.get_by_code(code)
        if not step_manager:
            return None
        
        async with self.postgres_db.get_session() as session:
            # 현재 거래 가격 리스트 가져오기
            trade_prices = step_manager.last_trade_prices
            
            # 리스트가 비어있으면 None 반환
            if not trade_prices:
                return None
            
            # 마지막 가격 제거
            trade_prices.pop()
            step_manager.last_trade_prices = trade_prices
            
            # 단계 -1 (0 이하로는 내려가지 않음)
            if step_manager.trade_step > 0:
                step_manager.trade_step -= 1
            
            step_manager.updated_at = datetime.now()
            
            session.add(step_manager)
            await session.commit()
            await session.refresh(step_manager)
            return step_manager

    async def delete_trade_price_by_index(self, 
                                      code: str, 
                                      index: int) -> Optional[StepManager]:
        """특정 인덱스의 거래 가격을 제거 (단계는 유지)"""
        step_manager = await self.get_by_code(code)
        if not step_manager:
            return None
        
        async with self.postgres_db.get_session() as session:
            trade_prices = step_manager.last_trade_prices
            
            # 인덱스가 유효한지 확인
            if not trade_prices or index < 0 or index >= len(trade_prices):
                return None
            
            # 특정 인덱스의 가격 제거
            trade_prices.pop(index)
            step_manager.last_trade_prices = trade_prices
            
            # trade_step을 리스트 길이와 동기화
            step_manager.trade_step = len(trade_prices)
            step_manager.updated_at = datetime.now()
            
            session.add(step_manager)
            await session.commit()
            await session.refresh(step_manager)
            return step_manager

    async def update_trade_price_by_index(self, 
                                         code: str, 
                                         index: int, 
                                         new_price: int) -> Optional[StepManager]:
        """특정 인덱스의 거래 가격을 수정"""
        step_manager = await self.get_by_code(code)
        if not step_manager:
            return None
        
        async with self.postgres_db.get_session() as session:
            trade_prices = step_manager.last_trade_prices
            
            # 인덱스가 유효한지 확인
            if not trade_prices or index < 0 or index >= len(trade_prices):
                return None
            
            # 특정 인덱스의 가격 수정
            trade_prices[index] = new_price
            step_manager.last_trade_prices = trade_prices
            step_manager.updated_at = datetime.now()
            
            session.add(step_manager)
            await session.commit()
            await session.refresh(step_manager)
            return step_manager

    async def sync_trade_step_with_prices(self, code: str) -> Optional[StepManager]:
        """거래 단계를 거래 가격 리스트 길이와 동기화"""
        step_manager = await self.get_by_code(code)
        if not step_manager:
            return None
        
        async with self.postgres_db.get_session() as session:
            # trade_step을 리스트 길이와 동기화
            step_manager.trade_step = len(step_manager.last_trade_prices)
            step_manager.updated_at = datetime.now()
            
            session.add(step_manager)
            await session.commit()
            await session.refresh(step_manager)
            return step_manager

    async def reset_trade_prices(self, code: str) -> Optional[StepManager]:
        """특정 종목의 거래 가격 리스트 초기화"""
        step_manager = await self.get_by_code(code)
        if not step_manager:
            return None
        
        async with self.postgres_db.get_session() as session:
            step_manager.last_trade_prices = []
            step_manager.trade_step = 0
            step_manager.updated_at = datetime.now()
            
            session.add(step_manager)
            await session.commit()
            await session.refresh(step_manager)
            return step_manager

    async def delete_all(self) -> bool:
        count = 0
        codes = await self.get_all_codes()
        for code in codes :
            await self.delete_by_code(code)
            count += 1
        logger.info(f"{count}개 스텝매니저 삭제완료")

    async def delete_by_code(self, code: str) -> bool:
        """종목 코드로 스텝 매니저 삭제"""
        async with self.postgres_db.get_session() as session:
            statement = select(StepManager).where(StepManager.code == code)
            result = await session.execute(statement)
            step_manager = result.scalar_one_or_none()
            
            if not step_manager:
                return False
            
            await session.delete(step_manager)
            await session.commit()
            logger.info(f"{code} 스텝매니저 삭제완료")
            return True


    # 유틸리티 메서드들
    async def get_all_codes(self) -> List[str]:
        """등록된 모든 종목 코드 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(StepManager.code).distinct()
            result = await session.execute(statement)
            return result.scalars().all()

    async def get_active_positions(self) -> List[StepManager]:
        """보유 수량이 있는 포지션 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(StepManager).where(StepManager.hold_qty > 0)
            result = await session.execute(statement)
            return result.scalars().all()

    async def get_fully_traded_positions(self) -> List[StepManager]:
        """완전히 거래된 포지션 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(StepManager).where(StepManager.hold_qty >= StepManager.total_qty)
            result = await session.execute(statement)
            return result.scalars().all()


    async def count_by_market(self) -> Dict[str, int]:
        """시장별 개수 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(StepManager)
            result = await session.execute(statement)
            all_managers = result.scalars().all()
            
            market_counts = {}
            for manager in all_managers:
                market = manager.market
                market_counts[market] = market_counts.get(market, 0) + 1
            
            return market_counts

    async def count_by_type(self) -> Dict[bool, int]:
        """타입별 개수 조회"""
        async with self.postgres_db.get_session() as session:
            statement = select(StepManager)
            result = await session.execute(statement)
            all_managers = result.scalars().all()
            
            type_counts = {True: 0, False: 0}
            for manager in all_managers:
                type_counts[manager.type] += 1
            
            return type_counts

    async def get_summary_statistics(self) -> Dict[str, Any]:
        """전체 통계 요약"""
        async with self.postgres_db.get_session() as session:
            statement = select(StepManager)
            result = await session.execute(statement)
            all_managers = result.scalars().all()
            
            if not all_managers:
                return {
                    "total_count": 0,
                    "market_distribution": {},
                    "type_distribution": {},
                    "average_final_price": 0,
                    "total_value": 0,
                    "total_hold_value": 0,
                    "active_positions": 0,
                    "fully_traded_positions": 0,
                    "average_trade_prices_summary": {}
                }
            
            # 통계 계산
            total_count = len(all_managers)
            market_counts = {}
            type_counts = {True: 0, False: 0}
            total_value = 0
            total_hold_value = 0
            active_positions = 0
            fully_traded_positions = 0
            price_sum = 0
            avg_prices = []
            
            for manager in all_managers:
                # 시장별 분포
                market = manager.market
                market_counts[market] = market_counts.get(market, 0) + 1
                
                # 타입별 분포
                type_counts[manager.type] += 1
                
                # 가치 계산
                total_value += manager.total_value
                total_hold_value += manager.hold_value
                price_sum += manager.final_price
                
                # 포지션 상태
                if manager.hold_qty > 0:
                    active_positions += 1
                if manager.trade_qty >= manager.total_qty:
                    fully_traded_positions += 1
                
                # 평균 거래 가격 수집
                avg_price = manager.get_average_trade_price()
                if avg_price is not None:
                    avg_prices.append(avg_price)
            
            # 평균 거래 가격 통계
            avg_prices_summary = {}
            if avg_prices:
                avg_prices_summary = {
                    "count": len(avg_prices),
                    "min": min(avg_prices),
                    "max": max(avg_prices),
                    "average": sum(avg_prices) / len(avg_prices)
                }
            
            return {
                "total_count": total_count,
                "market_distribution": market_counts,
                "type_distribution": type_counts,
                "average_final_price": price_sum // total_count if total_count > 0 else 0,
                "total_value": total_value,
                "total_hold_value": total_hold_value,
                "active_positions": active_positions,
                "fully_traded_positions": fully_traded_positions,
                "completion_rate": (fully_traded_positions / total_count * 100) if total_count > 0 else 0,
                "average_trade_prices_summary": avg_prices_summary
            }

    async def get_recent_trades(self, limit: int = 10) -> List[StepManager]:
        """최근 거래 조회 (마지막 거래 시간 기준)"""
        async with self.postgres_db.get_session() as session:
            statement = select(StepManager).where(
                StepManager.last_trade_time.is_not(None)
            ).order_by(StepManager.last_trade_time.desc()).limit(limit)
            result = await session.execute(statement)
            return result.scalars().all()

    async def get_trade_history_summary(self) -> Dict[str, Any]:
        """거래 히스토리 요약 통계"""
        all_managers = await self.get_all()
        
        total_trades = 0
        step_distribution = {}
        price_ranges = {"under_100k": 0, "100k_500k": 0, "500k_1m": 0, "over_1m": 0}
        
        for manager in all_managers:
            trade_prices = manager.last_trade_prices
            total_trades += len(trade_prices)
            
            # 단계별 분포
            step = manager.trade_step
            step_distribution[step] = step_distribution.get(step, 0) + 1
            
            # 가격대별 분포
            for price in trade_prices:
                if price < 100000:
                    price_ranges["under_100k"] += 1
                elif price < 500000:
                    price_ranges["100k_500k"] += 1
                elif price < 1000000:
                    price_ranges["500k_1m"] += 1
                else:
                    price_ranges["over_1m"] += 1
        
        return {
            "total_trades": total_trades,
            "step_distribution": step_distribution,
            "price_ranges": price_ranges,
            "managers_with_trades": len([m for m in all_managers if m.last_trade_prices])
        }