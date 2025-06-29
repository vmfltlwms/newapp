# schemas/step_manager_schema.py
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime

class StepManagerBase(BaseModel):
    """스텝 매니저 기본 스키마"""
    code: str = Field(..., description="종목 코드", max_length=10)
    type: bool = Field(..., description="타입")
    market: str = Field(..., description="시장 구분 (kospi, kosdaq, all)", max_length=10)
    final_price: int = Field(..., description="최종 가격 (원)", gt=0)
    total_qty: int = Field(..., description="총 수량", gt=0)
    trade_qty: int = Field(default=0, description="거래 수량", ge=0)
    trade_step: int = Field(default=0, description="거래 단계", ge=0)
    hold_qty: Optional[int] = Field(default=None, description="보유 수량", ge=0)
    last_trade_time: Optional[datetime] = Field(default=None, description="마지막 거래 시간")
    last_trade_prices: Optional[List[int]] = Field(default_factory=list, description="거래 가격 리스트")

    # ✅ timezone 제거 validator 추가
    @validator('last_trade_time', pre=True)
    def normalize_datetime(cls, v):
        """datetime의 timezone 정보를 제거하여 naive datetime으로 변환"""
        if v is None:
            return v
        
        if isinstance(v, datetime):
            # timezone이 있는 경우 제거
            if v.tzinfo is not None:
                # UTC로 변환 후 timezone 제거
                return v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            return v
        
        return v

    class Config:
        # ✅ JSON 직렬화 시 timezone 처리
        json_encoders = {
            datetime: lambda v: v.replace(tzinfo=None) if v and v.tzinfo else v
        }
        
        
class StepManagerCreate(StepManagerBase):
    """스텝 매니저 생성 스키마"""
    pass

class StepManagerUpdate(BaseModel):
    """스텝 매니저 업데이트 스키마"""
    final_price: Optional[int] = Field(default=None, description="최종 가격 (원)", gt=0)
    total_qty: Optional[int] = Field(default=None, description="총 수량", gt=0)
    trade_qty: Optional[int] = Field(default=None, description="거래 수량", ge=0)
    trade_step: Optional[int] = Field(default=None, description="거래 단계", ge=0)
    hold_qty: Optional[int] = Field(default=None, description="보유 수량", ge=0)
    last_trade_time: Optional[datetime] = Field(default=None, description="마지막 거래 시간")
    last_trade_prices: Optional[List[int]] = Field(default=None, description="거래 가격 리스트")

class StepManagerTradeUpdate(BaseModel):
    """거래 정보 업데이트 스키마"""
    trade_qty: int = Field(..., description="거래 수량", ge=0)
    trade_step: int = Field(..., description="거래 단계", ge=0)
    trade_price: int = Field(..., description="거래 가격", gt=0)

class StepManagerPriceUpdate(BaseModel):
    """거래 가격 업데이트 스키마"""
    trade_price: int = Field(..., description="거래 가격", gt=0)

class StepManagerRead(StepManagerBase):
    """스텝 매니저 조회 스키마"""
    id: int = Field(..., description="ID")
    created_at: datetime = Field(..., description="생성 시간")
    updated_at: datetime = Field(..., description="수정 시간")
    
    # 계산된 필드들
    total_value: int = Field(..., description="총 가치")
    hold_value: int = Field(..., description="보유 가치")
    trade_value: int = Field(..., description="거래 가치")
    last_trade_value: Optional[int] = Field(default=None, description="마지막 거래 가치")
    profit_loss: Optional[int] = Field(default=None, description="손익")
    remaining_qty: int = Field(..., description="남은 수량")
    is_fully_traded: bool = Field(..., description="완전 거래 여부")
    
    class Config:
        from_attributes = True

class StepManagerSummaryResponse(BaseModel):
    """스텝 매니저 요약 응답 스키마"""
    total_count: int = Field(..., description="전체 개수")
    market_distribution: dict = Field(..., description="시장별 분포")
    type_distribution: dict = Field(..., description="타입별 분포")
    average_final_price: int = Field(..., description="평균 최종 가격")
    total_value: int = Field(..., description="총 가치")
    total_hold_value: int = Field(..., description="총 보유 가치")
    active_positions: int = Field(..., description="활성 포지션 수")
    fully_traded_positions: int = Field(..., description="완전 거래 포지션 수")
    completion_rate: float = Field(..., description="완료율")
    average_trade_prices_summary: dict = Field(..., description="평균 거래 가격 요약")

class StepManagerTradeHistoryResponse(BaseModel):
    """거래 히스토리 요약 응답 스키마"""
    total_trades: int = Field(..., description="총 거래 횟수")
    step_distribution: dict = Field(..., description="단계별 분포")
    price_ranges: dict = Field(..., description="가격대별 분포")
    managers_with_trades: int = Field(..., description="거래 기록이 있는 매니저 수")

class DeleteResponse(BaseModel):
    """삭제 응답 스키마"""
    message: str = Field(..., description="삭제 메시지")
    deleted_count: int = Field(..., description="삭제된 개수")

class SingleDeleteResponse(BaseModel):
    """단일 삭제 응답 스키마"""
    message: str = Field(..., description="삭제 메시지")

# 추가 스키마들
class BulkPriceUpdate(BaseModel):
    """일괄 가격 업데이트 스키마"""
    code: str = Field(..., description="종목 코드")
    trade_price: int = Field(..., description="거래 가격", gt=0)

class StockComparisonRequest(BaseModel):
    """종목 비교 요청 스키마"""
    stock_codes: List[str] = Field(..., description="비교할 종목 코드 리스트", min_items=2)

class PriceRangeSearchRequest(BaseModel):
    """가격 범위 검색 요청 스키마"""
    min_price: Optional[int] = Field(default=None, description="최소 가격", ge=0)
    max_price: Optional[int] = Field(default=None, description="최대 가격", ge=0)
    min_avg_price: Optional[float] = Field(default=None, description="최소 평균 가격", ge=0)
    max_avg_price: Optional[float] = Field(default=None, description="최대 평균 가격", ge=0)

class RebalancingRecommendation(BaseModel):
    """리밸런싱 추천 스키마"""
    stock_code: str = Field(..., description="종목 코드")
    current_step: int = Field(..., description="현재 단계")
    completion_rate: float = Field(..., description="완료율")
    action: str = Field(..., description="추천 액션")
    reason: str = Field(..., description="추천 이유")
    priority: str = Field(..., description="우선순위")

class PortfolioSummary(BaseModel):
    """포트폴리오 요약 스키마"""
    total_stocks: int = Field(..., description="총 종목 수")
    total_investment: float = Field(..., description="총 투자금")
    total_current_value: int = Field(..., description="총 현재 가치")
    total_hold_value: int = Field(..., description="총 보유 가치")
    total_unrealized_pnl: float = Field(..., description="총 미실현 손익")
    overall_return_rate: float = Field(..., description="전체 수익률")
    active_positions: int = Field(..., description="활성 포지션 수")
    completed_positions: int = Field(..., description="완료 포지션 수")
    completion_rate: float = Field(..., description="완료율")
    market_distribution: dict = Field(..., description="시장별 분포")
    type_distribution: dict = Field(..., description="타입별 분포")
    average_position_size: float = Field(..., description="평균 포지션 크기")

class StepStatistics(BaseModel):
    """단계별 통계 스키마"""
    step_distribution: dict = Field(..., description="단계별 분포")
    total_steps: int = Field(..., description="총 단계 수")
    most_common_step: Optional[int] = Field(default=None, description="가장 흔한 단계")
    step_progression: dict = Field(..., description="단계별 진행 현황")

class RiskAnalysis(BaseModel):
    """위험도 분석 스키마"""
    total_stocks: int = Field(..., description="총 종목 수")
    overall_risk_level: str = Field(..., description="전체 위험도")
    risk_distribution: dict = Field(..., description="위험도별 분포")
    concentration_risk: dict = Field(..., description="집중도 위험")
    market_exposure: dict = Field(..., description="시장 노출도")
    step_concentration: dict = Field(..., description="단계 집중도")
    recommendations: List[str] = Field(..., description="리스크 관리 추천사항")

class PerformanceAnalysis(BaseModel):
    """성과 분석 스키마"""
    stock_code: str = Field(..., description="종목 코드")
    current_price: int = Field(..., description="현재가")
    average_buy_price: Optional[float] = Field(default=None, description="평균 매수가")
    total_investment: int = Field(..., description="총 투자금")
    current_value: int = Field(..., description="현재 가치")
    unrealized_pnl: Optional[int] = Field(default=None, description="미실현 손익")
    total_quantity: int = Field(..., description="총 수량")
    traded_quantity: int = Field(..., description="거래 수량")
    holding_quantity: int = Field(..., description="보유 수량")
    completion_rate: float = Field(..., description="완료율")
    return_rate: float = Field(..., description="수익률")
    price_volatility: int = Field(..., description="가격 변동성")
    volatility_rate: float = Field(..., description="변동성 비율")
    risk_level: str = Field(..., description="리스크 레벨")

class TradeDetails(BaseModel):
    """거래 상세 정보 스키마"""
    stock_code: str = Field(..., description="종목 코드")
    current_step: int = Field(..., description="현재 단계")
    total_trades: int = Field(..., description="총 거래 횟수")
    trade_prices: List[int] = Field(..., description="거래 가격 리스트")
    average_trade_price: Optional[float] = Field(default=None, description="평균 거래가")
    total_value: int = Field(..., description="총 가치")
    hold_value: int = Field(..., description="보유 가치")
    trade_value: int = Field(..., description="거래 가치")
    profit_loss: Optional[int] = Field(default=None, description="손익")
    completion_rate: float = Field(..., description="완료율")
    is_fully_traded: bool = Field(..., description="완전 거래 여부")
    last_trade_time: Optional[datetime] = Field(default=None, description="마지막 거래 시간")
    step_details: List[dict] = Field(..., description="단계별 상세 정보")

class StockComparison(BaseModel):
    """종목 비교 스키마"""
    stock_code: str = Field(..., description="종목 코드")
    current_price: int = Field(..., description="현재가")
    average_buy_price: Optional[float] = Field(default=None, description="평균 매수가")
    trade_step: int = Field(..., description="거래 단계")
    completion_rate: float = Field(..., description="완료율")
    return_rate: float = Field(..., description="수익률")
    trade_value: int = Field(..., description="거래 가치")
    hold_value: int = Field(..., description="보유 가치")
    unrealized_pnl: Optional[int] = Field(default=None, description="미실현 손익")
    market: str = Field(..., description="시장")
    type: bool = Field(..., description="타입")

class ComparisonAnalysis(BaseModel):
    """비교 분석 결과 스키마"""
    best_performer: dict = Field(..., description="최고 성과 종목")
    worst_performer: dict = Field(..., description="최저 성과 종목")
    highest_completion: dict = Field(..., description="최고 완료율 종목")
    most_valuable: dict = Field(..., description="최고 가치 종목")
    average_return_rate: float = Field(..., description="평균 수익률")
    average_completion_rate: float = Field(..., description="평균 완료율")

class BulkOperationResult(BaseModel):
    """일괄 작업 결과 스키마"""
    total_requested: int = Field(..., description="총 요청 수")
    success: int = Field(..., description="성공 수")
    errors: int = Field(..., description="오류 수")
    success_rate: float = Field(..., description="성공률")
    error_details: Optional[List[str]] = Field(default=None, description="오류 상세")
    message: str = Field(..., description="결과 메시지")

# 요청/응답 래퍼 스키마들
class StepManagerListResponse(BaseModel):
    """스텝 매니저 리스트 응답"""
    items: List[StepManagerRead] = Field(..., description="스텝 매니저 리스트")
    total: int = Field(..., description="총 개수")

class StockCodesResponse(BaseModel):
    """종목 코드 리스트 응답"""
    stock_codes: List[str] = Field(..., description="종목 코드 리스트")
    total: int = Field(..., description="총 개수")

class ComparisonResponse(BaseModel):
    """종목 비교 응답"""
    compared_stocks: int = Field(..., description="비교된 종목 수")
    not_found: List[str] = Field(..., description="찾을 수 없는 종목")
    comparisons: List[StockComparison] = Field(..., description="비교 결과")
    analysis: ComparisonAnalysis = Field(..., description="분석 결과")

class RebalancingResponse(BaseModel):
    """리밸런싱 추천 응답"""
    total_stocks: int = Field(..., description="총 종목 수")
    recommendations: List[RebalancingRecommendation] = Field(..., description="추천 리스트")
    summary: dict = Field(..., description="요약 정보")
    message: str = Field(..., description="메시지")

class SearchResponse(BaseModel):
    """검색 결과 응답"""
    results: List[StepManagerRead] = Field(..., description="검색 결과")
    total_found: int = Field(..., description="찾은 개수")
    search_criteria: dict = Field(..., description="검색 조건")

# 에러 응답 스키마
class ErrorResponse(BaseModel):
    """에러 응답 스키마"""
    detail: str = Field(..., description="에러 상세")
    error_code: Optional[str] = Field(default=None, description="에러 코드")
    timestamp: datetime = Field(default_factory=datetime.now, description="발생 시간")

# Enum 클래스들
from enum import Enum

class MarketType(str, Enum):
    """시장 타입"""
    KOSPI = "kospi"
    KOSDAQ = "kosdaq"
    ALL = "all"

class ActionType(str, Enum):
    """액션 타입"""
    START_BUYING = "START_BUYING"
    CONTINUE_BUYING = "CONTINUE_BUYING"
    INCREASE_POSITION = "INCREASE_POSITION"
    MONITOR = "MONITOR"
    HOLD = "HOLD"
    CONSIDER_SELLING = "CONSIDER_SELLING"

class PriorityType(str, Enum):
    """우선순위 타입"""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class RiskLevel(str, Enum):
    """위험도 레벨"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"

# 헬스체크 스키마
class HealthCheckResponse(BaseModel):
    """헬스체크 응답"""
    status: str = Field(..., description="상태")
    timestamp: datetime = Field(default_factory=datetime.now, description="확인 시간")
    service: str = Field(default="StepManager API", description="서비스명")
    version: str = Field(default="1.0.0", description="버전")

# 메트릭스 스키마
class MetricsResponse(BaseModel):
    """메트릭스 응답"""
    total_requests: int = Field(..., description="총 요청 수")
    successful_requests: int = Field(..., description="성공 요청 수")
    failed_requests: int = Field(..., description="실패 요청 수")
    average_response_time: float = Field(..., description="평균 응답 시간")
    uptime: str = Field(..., description="가동 시간")
    memory_usage: dict = Field(..., description="메모리 사용량")
    
# 설정 스키마들
class StepManagerConfig(BaseModel):
    """스텝 매니저 설정"""
    max_trade_step: int = Field(default=10, description="최대 거래 단계")
    default_market: MarketType = Field(default=MarketType.ALL, description="기본 시장")
    price_precision: int = Field(default=0, description="가격 정밀도")
    quantity_precision: int = Field(default=0, description="수량 정밀도")
    enable_auto_sync: bool = Field(default=True, description="자동 동기화 활성화")
    
class ApiConfig(BaseModel):
    """API 설정"""
    page_size: int = Field(default=50, description="페이지 크기")
    max_page_size: int = Field(default=1000, description="최대 페이지 크기")
    enable_cache: bool = Field(default=True, description="캐시 활성화")
    cache_ttl: int = Field(default=300, description="캐시 TTL(초)")
    rate_limit: int = Field(default=100, description="속도 제한(분당)")

# 페이지네이션 스키마
class PaginationParams(BaseModel):
    """페이지네이션 파라미터"""
    page: int = Field(default=1, description="페이지 번호", ge=1)
    size: int = Field(default=50, description="페이지 크기", ge=1, le=1000)
    sort_by: Optional[str] = Field(default=None, description="정렬 기준")
    sort_order: Optional[str] = Field(default="asc", description="정렬 순서", pattern="^(asc|desc)$")

class PaginatedResponse(BaseModel):
    """페이지네이션 응답"""
    items: List[StepManagerRead] = Field(..., description="아이템 리스트")
    total: int = Field(..., description="총 개수")
    page: int = Field(..., description="현재 페이지")
    size: int = Field(..., description="페이지 크기")
    pages: int = Field(..., description="총 페이지 수")
    has_next: bool = Field(..., description="다음 페이지 존재 여부")
    has_prev: bool = Field(..., description="이전 페이지 존재 여부")

# 필터링 스키마
class StepManagerFilter(BaseModel):
    """스텝 매니저 필터"""
    markets: Optional[List[MarketType]] = Field(default=None, description="시장 필터")
    types: Optional[List[bool]] = Field(default=None, description="타입 필터")
    min_step: Optional[int] = Field(default=None, description="최소 단계", ge=0)
    max_step: Optional[int] = Field(default=None, description="최대 단계", ge=0)
    min_price: Optional[int] = Field(default=None, description="최소 가격", ge=0)
    max_price: Optional[int] = Field(default=None, description="최대 가격", ge=0)
    has_trades: Optional[bool] = Field(default=None, description="거래 기록 보유 여부")
    is_active: Optional[bool] = Field(default=None, description="활성 상태 여부")
    date_from: Optional[datetime] = Field(default=None, description="시작 날짜")
    date_to: Optional[datetime] = Field(default=None, description="종료 날짜")