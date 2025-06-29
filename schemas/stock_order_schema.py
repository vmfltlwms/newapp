# stock_order_schema.py
from sqlmodel import SQLModel
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

# ✅ 주식 주문 기본 스키마
class StockOrderBase(BaseModel):
    """주식 주문 기본 스키마"""
    user_id: str = Field(..., description="사용자 ID", example="user123")
    stock_code: str = Field(..., description="종목코드", example="005930")
    stock_name: Optional[str] = Field(None, description="종목명", example="삼성전자")
    exchange_type: str = Field("KRX", description="거래소구분 - KRX:한국거래소, NXT:넥스트트레이드, SOR:최선주문집행")
    order_quantity: int = Field(..., gt=0, description="주문수량", example=10)
    order_price: Optional[Decimal] = Field(None, description="주문단가 (시장가 주문 시 생략)", example=75000.0)
    trade_type: str = Field("0", description="매매구분 - 0:보통, 3:시장가, 5:조건부지정가, 6:최유리지정가, 7:최우선지정가")
    condition_price: Optional[Decimal] = Field(None, description="조건단가")

# ✅ 주식 매수 주문 스키마
class StockBuyRequest(StockOrderBase):
    """주식 매수 주문 요청 스키마"""
    order_type: str = Field("buy", description="주문구분")
    
    class Config:
        schema_extra = {
            "example": {
                "user_id": "user123",
                "stock_code": "005930",
                "stock_name": "삼성전자",
                "exchange_type": "KRX",
                "order_quantity": 10,
                "order_price": 75000.0,
                "trade_type": "0"
            }
        }

# ✅ 주식 매도 주문 스키마
class StockSellRequest(StockOrderBase):
    """주식 매도 주문 요청 스키마"""
    order_type: str = Field("sell", description="주문구분")
    
    class Config:
        schema_extra = {
            "example": {
                "user_id": "user123",
                "stock_code": "005930",
                "stock_name": "삼성전자",
                "exchange_type": "KRX",
                "order_quantity": 5,
                "order_price": 76000.0,
                "trade_type": "0"
            }
        }

# ✅ 주식 정정 주문 스키마
class StockModifyRequest(BaseModel):
    """주식 정정 주문 요청 스키마"""
    user_id: str = Field(..., description="사용자 ID", example="user123")
    original_order_no: str = Field(..., description="원주문번호", example="20240528001")
    stock_code: str = Field(..., description="종목코드", example="005930")
    exchange_type: str = Field("KRX", description="거래소구분")
    modify_quantity: int = Field(..., gt=0, description="정정수량", example=8)
    modify_price: Decimal = Field(..., description="정정단가", example=74000.0)
    modify_condition_price: Optional[Decimal] = Field(None, description="정정조건단가")
    order_type: str = Field("modify", description="주문구분")
    
    class Config:
        schema_extra = {
            "example": {
                "user_id": "user123",
                "original_order_no": "20240528001",
                "stock_code": "005930",
                "exchange_type": "KRX",
                "modify_quantity": 8,
                "modify_price": 74000.0
            }
        }

# ✅ 주식 취소 주문 스키마
class StockCancelRequest(BaseModel):
    """주식 취소 주문 요청 스키마"""
    user_id: str = Field(..., description="사용자 ID", example="user123")
    original_order_no: str = Field(..., description="원주문번호", example="20240528001")
    stock_code: str = Field(..., description="종목코드", example="005930")
    exchange_type: str = Field("KRX", description="거래소구분")
    cancel_quantity: int = Field(0, description="취소수량 (0: 전량취소)", example=0)
    order_type: str = Field("cancel", description="주문구분")
    
    class Config:
        schema_extra = {
            "example": {
                "user_id": "user123",
                "original_order_no": "20240528001",
                "stock_code": "005930",
                "exchange_type": "KRX",
                "cancel_quantity": 0
            }
        }

# ✅ 주식 주문 응답 스키마
class StockOrderResponse(BaseModel):
    """주식 주문 응답 스키마"""
    id: Optional[int] = Field(None, description="주문 ID")
    order_no: Optional[str] = Field(None, description="주문번호")
    user_id: str = Field(..., description="사용자 ID")
    stock_code: str = Field(..., description="종목코드")
    stock_name: Optional[str] = Field(None, description="종목명")
    order_type: str = Field(..., description="주문구분")
    exchange_type: str = Field(..., description="거래소구분")
    order_quantity: int = Field(..., description="주문수량")
    order_price: Optional[Decimal] = Field(None, description="주문단가")
    trade_type: str = Field(..., description="매매구분")
    order_status: str = Field(..., description="주문상태")
    created_at: datetime = Field(..., description="생성시간")
    
    class Config:
        from_attributes = True

# ✅ 주문 목록 응답 스키마
class StockOrderListResponse(BaseModel):
    """주문 목록 응답 스키마"""
    orders: List[StockOrderResponse] = Field(..., description="주문 목록")
    total_count: int = Field(..., description="전체 주문 수")
    page: int = Field(..., description="현재 페이지")
    page_size: int = Field(..., description="페이지 크기")

# ✅ 주문 통계 응답 스키마
class OrderStatisticsResponse(BaseModel):
    """주문 통계 응답 스키마"""
    user_id: str = Field(..., description="사용자 ID")
    total_orders: int = Field(..., description="총 주문 수")
    buy_orders: int = Field(..., description="매수 주문 수")
    sell_orders: int = Field(..., description="매도 주문 수")
    pending_orders: int = Field(..., description="대기 중인 주문 수")
    completed_orders: int = Field(..., description="완료된 주문 수")
    cancelled_orders: int = Field(..., description="취소된 주문 수")

# ✅ 키움 API 응답 스키마
class KiwoomOrderResponse(BaseModel):
    """키움 API 주문 응답 스키마"""
    ord_no: Optional[str] = Field(None, description="주문번호")
    result_code: Optional[str] = Field(None, description="결과코드")
    result_msg: Optional[str] = Field(None, description="결과메시지")
    
# ✅ 에러 응답 스키마
class ErrorResponse(BaseModel):
    """에러 응답 스키마"""
    detail: str = Field(..., description="에러 상세 메시지")
    error_code: Optional[str] = Field(None, description="에러 코드")
    timestamp: datetime = Field(default_factory=datetime.now, description="에러 발생 시간")

# ✅ 성공 응답 스키마
class SuccessResponse(BaseModel):
    """성공 응답 스키마"""
    message: str = Field(..., description="성공 메시지")
    data: Optional[dict] = Field(None, description="응답 데이터")

# ✅ 주문 검색 필터 스키마
class OrderSearchFilter(BaseModel):
    """주문 검색 필터 스키마"""
    user_id: Optional[str] = Field(None, description="사용자 ID")
    stock_code: Optional[str] = Field(None, description="종목코드")
    order_type: Optional[str] = Field(None, description="주문구분 (buy/sell/modify/cancel)")
    order_status: Optional[str] = Field(None, description="주문상태")
    exchange_type: Optional[str] = Field(None, description="거래소구분")
    start_date: Optional[datetime] = Field(None, description="시작일시")
    end_date: Optional[datetime] = Field(None, description="종료일시")
    min_price: Optional[Decimal] = Field(None, description="최소 주문단가")
    max_price: Optional[Decimal] = Field(None, description="최대 주문단가")
    min_quantity: Optional[int] = Field(None, description="최소 주문수량")
    max_quantity: Optional[int] = Field(None, description="최대 주문수량")

# ✅ 페이지네이션 스키마
class PaginationParams(BaseModel):
    """페이지네이션 파라미터 스키마"""
    page: int = Field(1, ge=1, description="페이지 번호 (1부터 시작)")
    page_size: int = Field(20, ge=1, le=100, description="페이지 크기 (최대 100)")
    
    @property
    def offset(self) -> int:
        """오프셋 계산"""
        return (self.page - 1) * self.page_size

# ✅ 주문 상태 변경 스키마
class OrderStatusUpdate(BaseModel):
    """주문 상태 변경 스키마"""
    order_no: str = Field(..., description="주문번호")
    new_status: str = Field(..., description="새로운 상태")
    reason: Optional[str] = Field(None, description="변경 사유")

# ✅ 벌크 주문 스키마
class BulkOrderRequest(BaseModel):
    """벌크 주문 요청 스키마"""
    user_id: str = Field(..., description="사용자 ID")
    orders: List[StockOrderBase] = Field(..., description="주문 목록", max_items=100)

# ✅ 벌크 주문 응답 스키마
class BulkOrderResponse(BaseModel):
    """벌크 주문 응답 스키마"""
    total_requested: int = Field(..., description="요청된 총 주문 수")
    successful: int = Field(..., description="성공한 주문 수")
    failed: int = Field(..., description="실패한 주문 수")
    results: List[dict] = Field(..., description="각 주문의 결과")