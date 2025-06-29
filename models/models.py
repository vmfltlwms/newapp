from datetime import datetime
import json
import time
from sqlmodel import ARRAY, Column, SQLModel, Field, String
from typing import List, Optional

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    age: int
    email: str

class Realtime_Group(SQLModel, table=True):
    group: int = Field(primary_key=True)
    strategy: int = Field(default=1)
    data_type: List[str] = Field(sa_column=Column(ARRAY(String)))
    stock_code : List[int] = Field(sa_column=Column(ARRAY(String)))

class BaseLine(SQLModel, table=True):
    """베이스라인 모델 - 예상 가격 범위 필드 추가"""
    __tablename__ = "baseline"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(..., description="종목 코드", max_length=10, index=True)
    step: int = Field(..., description="단계 (0부터 시작)", ge=0, index=True)
    decision_price: int = Field(..., description="결정 가격 (원)", ge=0)
    quantity: int = Field(..., description="수량", ge=0)
    low_price: Optional[int] = Field(None, description="예상 최저 가격 (원)", ge=0)
    high_price: Optional[int] = Field(None, description="예상 최고 가격 (원)", ge=0)
    created_at: Optional[datetime] = Field(default_factory=datetime.now, description="생성 시간")
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, description="수정 시간")
    
    
    class Config:
        """SQLModel 설정"""
        # 종목코드와 step의 조합이 유니크해야 함
        schema_extra = {
            "example": {
                "stock_code": "005930",
                "step": 0,
                "decision_price": 75000,
                "quantity": 10,
                "low_price": 72000,
                "high_price": 78000
            }
        }
    
    def __repr__(self) -> str:
        return f"<BaseLine(stock_code={self.stock_code}, step={self.step}, decision_price={self.decision_price}, low_price={self.low_price}, high_price={self.high_price})>"
    
    @property
    def price_range(self) -> Optional[int]:
        """가격 범위 계산 (high_price - low_price)"""
        if self.high_price is not None and self.low_price is not None:
            return self.high_price - self.low_price
        return None
    
    @property
    def price_range_percentage(self) -> Optional[float]:
        """가격 범위 비율 계산 ((high_price - low_price) / decision_price * 100)"""
        if self.high_price is not None and self.low_price is not None and self.decision_price > 0:
            return ((self.high_price - self.low_price) / self.decision_price) * 100
        return None
    
    @property
    def is_price_in_range(self) -> Optional[bool]:
        """결정 가격이 예상 범위 내에 있는지 확인"""
        if self.high_price is not None and self.low_price is not None:
            return self.low_price <= self.decision_price <= self.high_price
        return None
    
    @property
    def total_value(self) -> int:
        """총 가치 계산 (결정 가격 × 수량)"""
        return self.decision_price * self.quantity
    
    @property
    def estimated_low_value(self) -> Optional[int]:
        """예상 최저 가치 계산 (low_price × quantity)"""
        if self.low_price is not None:
            return self.low_price * self.quantity
        return None
    
    @property
    def estimated_high_value(self) -> Optional[int]:
        """예상 최고 가치 계산 (high_price × quantity)"""
        if self.high_price is not None:
            return self.high_price * self.quantity
        return None
      

class StepManager(SQLModel, table=True):
    """스텝 매니저 모델"""
    __tablename__ = "step_manager"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(..., description="종목 코드", max_length=10, index=True)
    type: bool = Field(..., description="타입", index=True)
    market: str = Field(..., description="시장 구분 (kospi, kosdaq, all)", max_length=10, index=True)
    final_price: int = Field(..., description="최종 가격 (원)", ge=0)
    total_qty: int = Field(..., description="총 수량", ge=0)
    trade_qty: int = Field(..., description="거래 수량", ge=0)
    trade_step: int = Field(..., description="거래 단계", ge=0, index=True)
    hold_qty: int = Field(..., description="보유 수량", ge=0)
    last_trade_time: Optional[datetime] = Field(default=None, description="마지막 거래 시간")
    
    # 방법 1: JSON 문자열로 저장 (가장 호환성 좋음)
    last_trade_prices_json: Optional[str] = Field(
        default=None, 
        description="마지막 거래 가격들 (JSON 문자열)", 
        alias="last_trade_prices"
    )
    
    created_at: Optional[datetime] = Field(default_factory=datetime.now, description="생성 시간")
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, description="수정 시간")
    
    class Config:
        """SQLModel 설정"""
        schema_extra = {
            "example": {
                "code": "005930",
                "type": True,
                "market": "kospi",
                "final_price": 75000,
                "total_qty": 100,
                "trade_qty": 50,
                "trade_step": 2,
                "hold_qty": 50,
                "last_trade_time": "2025-06-21T10:30:00",
                "last_trade_prices": [190930, 190960]
            }
        }
    
    def __repr__(self) -> str:
        return f"<StepManager(code={self.code}, type={self.type}, market={self.market}, trade_step={self.trade_step})>"
    
    # 프로퍼티로 리스트 접근 제공
    @property
    def last_trade_prices(self) -> List[int]:
        """마지막 거래 가격 리스트"""
        if self.last_trade_prices_json is None:
            return []
        try:
            return json.loads(self.last_trade_prices_json)
        except (json.JSONDecodeError, TypeError):
            return []
    
    @last_trade_prices.setter
    def last_trade_prices(self, value: List[int]):
        """마지막 거래 가격 리스트 설정"""
        if value is None or len(value) == 0:
            self.last_trade_prices_json = None
        else:
            self.last_trade_prices_json = json.dumps(value)
    
    @property
    def last_trade_price(self) -> Optional[int]:
        """가장 최근 거래 가격 (기존 호환성 유지)"""
        prices = self.last_trade_prices
        return prices[-1] if prices else None
    
    @property
    def total_value(self) -> int:
        """총 가치 계산 (최종 가격 × 총 수량)"""
        return self.final_price * self.total_qty
    
    @property
    def hold_value(self) -> int:
        """보유 가치 계산 (최종 가격 × 보유 수량)"""
        return self.final_price * self.hold_qty
    
    @property
    def trade_value(self) -> int:
        """거래 가치 계산 (최종 가격 × 거래 수량)"""
        return self.final_price * self.trade_qty
    
    @property
    def last_trade_value(self) -> Optional[int]:
        """마지막 거래 가치 계산 (마지막 거래 가격 × 거래 수량)"""
        if self.last_trade_price is not None:
            return self.last_trade_price * self.trade_qty
        return None
    
    @property
    def profit_loss(self) -> Optional[int]:
        """손익 계산 (현재 가치 - 마지막 거래 가치)"""
        if self.last_trade_price is not None:
            current_value = self.final_price * self.trade_qty
            last_value = self.last_trade_price * self.trade_qty
            return current_value - last_value
        return None
    
    @property
    def remaining_qty(self) -> int:
        """남은 수량 계산 (총 수량 - 거래 수량)"""
        return self.total_qty - self.trade_qty
    
    @property
    def is_fully_traded(self) -> bool:
        """완전 거래 여부 확인"""
        return self.trade_qty >= self.total_qty
    
    # 새로운 헬퍼 메서드들
    def add_trade_price(self, price: int):
        """새로운 거래 가격 추가"""
        prices = self.last_trade_prices
        prices.append(price)
        self.last_trade_prices = prices
    
    def get_average_trade_price(self) -> Optional[float]:
        """평균 거래 가격 계산"""
        prices = self.last_trade_prices
        return sum(prices) / len(prices) if prices else None
    
    def get_price_by_step(self, step: int) -> Optional[int]:
        """특정 단계의 거래 가격 조회"""
        prices = self.last_trade_prices
        return prices[step] if 0 <= step < len(prices) else None