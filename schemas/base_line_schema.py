# schemas/base_line_schema.py에 추가할 스키마들 (SQLModel 버전) - Updated with low_price and high_price

from sqlmodel import SQLModel
from pydantic import Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# 기존 스키마들 - Updated
class BaselineCreate(SQLModel):
    """베이스라인 생성 시 사용되는 스키마"""
    stock_code: str = Field(..., description="종목 코드", example="005930")
    decision_price: int = Field(..., gt=0, description="결정 가격 (원)", example=75000)
    quantity: int = Field(..., gt=0, description="수량", example=10)
    low_price: Optional[int] = Field(None, gt=0, description="예상 최저 가격 (원)", example=72000)
    high_price: Optional[int] = Field(None, gt=0, description="예상 최고 가격 (원)", example=78000)

class BaselineUpdate(SQLModel):
    """베이스라인 업데이트 시 사용되는 스키마"""
    stock_code: str = Field(..., description="종목 코드", example="005930")
    step: int = Field(..., ge=0, description="단계 (0부터 시작)", example=0)
    decision_price: int = Field(..., gt=0, description="결정 가격 (원)", example=73000)
    quantity: int = Field(..., gt=0, description="수량", example=15)
    low_price: Optional[int] = Field(None, gt=0, description="예상 최저 가격 (원)", example=70000)
    high_price: Optional[int] = Field(None, gt=0, description="예상 최고 가격 (원)", example=76000)

class BaselineRead(SQLModel):
    """베이스라인 조회 시 반환되는 스키마"""
    id: Optional[int] = Field(default=None, primary_key=True, description="베이스라인 고유 ID")
    stock_code: str = Field(..., description="종목 코드", example="005930")
    step: int = Field(..., ge=0, description="단계 (0부터 시작)", example=0)
    decision_price: int = Field(..., gt=0, description="결정 가격 (원)", example=75000)
    quantity: int = Field(..., gt=0, description="수량", example=10)
    low_price: Optional[int] = Field(None, description="예상 최저 가격 (원)", example=72000)
    high_price: Optional[int] = Field(None, description="예상 최고 가격 (원)", example=78000)
    created_at: Optional[datetime] = Field(default=None, description="생성 시간")
    updated_at: Optional[datetime] = Field(default=None, description="수정 시간")

class LastStepResponse(SQLModel):
    """마지막 step 조회 응답 스키마"""
    stock_code: str = Field(..., description="종목 코드", example="005930")
    last_step: Optional[int] = Field(None, description="마지막 step (없으면 null)", example=3)

class DeleteResponse(SQLModel):
    """삭제 응답 스키마"""
    message: str = Field(..., description="삭제 결과 메시지")
    deleted_count: Optional[int] = Field(None, description="삭제된 항목 수")

class SingleDeleteResponse(SQLModel):
    """단일 항목 삭제 응답 스키마"""
    message: str = Field(..., description="삭제 결과 메시지")

class ErrorResponse(SQLModel):
    """에러 응답 스키마"""
    detail: str = Field(..., description="에러 상세 메시지")

# ==================== 새로 추가되는 스키마들 ====================

# ✅ 베이스라인 요약 응답 스키마
class BaselineSummaryResponse(SQLModel):
    """베이스라인 전체 요약 정보 응답"""
    total_baselines: int = Field(..., description="전체 베이스라인 개수", example=150)
    unique_stocks: int = Field(..., description="고유 종목 개수", example=25)
    stock_codes: List[str] = Field(..., description="등록된 종목 코드 목록", example=["005930", "035420", "000660"])
    stock_step_counts: Dict[str, int] = Field(..., description="종목별 step 개수", example={"005930": 5, "035420": 3, "000660": 7})
    max_steps_per_stock: int = Field(..., description="종목당 최대 step 수", example=7)
    min_steps_per_stock: int = Field(..., description="종목당 최소 step 수", example=1)

# ✅ 벌크 생성 요청 스키마
class BulkCreateRequest(SQLModel):
    """여러 베이스라인 생성 요청"""
    baselines: List[BaselineCreate] = Field(..., description="생성할 베이스라인 목록")

# ✅ 벌크 생성 응답 스키마
class BulkCreateResponse(SQLModel):
    """벌크 생성 작업 결과 응답"""
    total_requested: int = Field(..., description="요청된 총 개수", example=10)
    created: int = Field(..., description="성공적으로 생성된 개수", example=7)
    skipped: int = Field(..., description="이미 존재해서 건너뛴 개수", example=2)
    errors: int = Field(..., description="오류 발생한 개수", example=1)
    error_details: Optional[List[str]] = Field(None, description="오류 상세 내용", example=["종목 999999: 잘못된 종목코드"])
    success_rate: float = Field(..., description="성공률 (%)", example=90.0)
    message: str = Field(..., description="작업 완료 메시지", example="벌크 생성 완료: 생성 7개, 건너뜀 2개, 오류 1개")

# ✅ 동기화 응답 스키마
class SyncResponse(SQLModel):
    """실시간 그룹 동기화 작업 결과 응답"""
    total_groups: Optional[int] = Field(None, description="처리된 그룹 수", example=5)
    total_stock_codes: int = Field(..., description="추출된 총 종목 코드 수", example=150)
    created: int = Field(..., description="새로 생성된 베이스라인 수", example=120)
    skipped: int = Field(..., description="이미 존재해서 건너뛴 수", example=25)
    errors: int = Field(..., description="오류 발생한 수", example=5)
    success_rate: float = Field(..., description="성공률 (%)", example=96.7)
    message: str = Field(..., description="작업 완료 메시지", example="베이스라인 동기화 완료: 생성 120개, 건너뜀 25개, 오류 5개")

# ✅ 특정 그룹 동기화 응답 스키마
class GroupSyncResponse(SQLModel):
    """특정 그룹 동기화 작업 결과 응답"""
    group: int = Field(..., description="처리된 그룹 번호", example=1)
    stock_codes: int = Field(..., description="그룹 내 종목 코드 수", example=30)
    created: int = Field(..., description="새로 생성된 베이스라인 수", example=25)
    skipped: int = Field(..., description="이미 존재해서 건너뛴 수", example=3)
    errors: int = Field(..., description="오류 발생한 수", example=2)
    success_rate: float = Field(..., description="성공률 (%)", example=93.3)
    message: str = Field(..., description="작업 완료 메시지", example="그룹 1 베이스라인 동기화 완료: 생성 25개, 건너뜀 3개, 오류 2개")

# ✅ Step 상세 정보 스키마 - Updated
class StepDetail(SQLModel):
    """Step별 상세 정보"""
    step: int = Field(..., description="단계 번호", example=0)
    price: int = Field(..., description="결정 가격", example=50000)
    quantity: int = Field(..., description="수량", example=10)
    low_price: Optional[int] = Field(None, description="예상 최저 가격", example=48000)
    high_price: Optional[int] = Field(None, description="예상 최고 가격", example=52000)

# ✅ 종목별 통계 응답 스키마 - Updated
class StockStatsResponse(SQLModel):
    """특정 종목의 베이스라인 통계 응답"""
    stock_code: str = Field(..., description="종목 코드", example="005930")
    total_steps: int = Field(..., description="총 step 수", example=5)
    total_quantity: int = Field(..., description="총 수량", example=50)
    total_value: int = Field(..., description="총 가치 (가격 × 수량)", example=2500000)
    average_price: float = Field(..., description="평균 결정 가격", example=50000.0)
    min_price: int = Field(..., description="최소 결정 가격", example=45000)
    max_price: int = Field(..., description="최대 결정 가격", example=55000)
    average_low_price: Optional[float] = Field(None, description="평균 예상 최저 가격", example=47500.0)
    average_high_price: Optional[float] = Field(None, description="평균 예상 최고 가격", example=52500.0)
    steps: List[StepDetail] = Field(..., description="각 step별 상세 정보")

# ✅ 전체 삭제 응답 스키마
class DeleteAllResponse(SQLModel):
    """전체 베이스라인 삭제 결과 응답"""
    deleted_stocks: int = Field(..., description="삭제된 종목 수", example=25)
    total_deleted_baselines: int = Field(..., description="삭제된 총 베이스라인 수", example=150)
    message: str = Field(..., description="삭제 완료 메시지", example="모든 베이스라인이 삭제되었습니다")

# ✅ 카운트 응답 스키마
class CountResponse(SQLModel):
    """개수 조회 응답"""
    total_count: int = Field(..., description="총 개수", example=150)

# ✅ 종목 코드 목록 응답 스키마
class StockCodesResponse(SQLModel):
    """종목 코드 목록 응답"""
    stock_codes: List[str] = Field(..., description="등록된 종목 코드 목록", example=["005930", "035420", "000660"])
    total_count: int = Field(..., description="총 종목 수", example=3)

# ✅ 일반적인 성공 응답 스키마
class SuccessResponse(SQLModel):
    """일반적인 성공 응답"""
    success: bool = Field(True, description="작업 성공 여부")
    message: str = Field(..., description="결과 메시지", example="작업이 성공적으로 완료되었습니다")
    data: Optional[Dict[str, Any]] = Field(None, description="추가 데이터")

# ✅ 페이지네이션 메타데이터 스키마
class PaginationMeta(SQLModel):
    """페이지네이션 메타데이터"""
    page: int = Field(..., description="현재 페이지", example=1)
    size: int = Field(..., description="페이지 크기", example=10)
    total: int = Field(..., description="전체 항목 수", example=150)
    pages: int = Field(..., description="전체 페이지 수", example=15)

# ✅ 페이지네이션된 베이스라인 목록 응답 스키마
class PaginatedBaselineResponse(SQLModel):
    """페이지네이션된 베이스라인 목록 응답"""
    items: List[BaselineRead] = Field(..., description="베이스라인 목록")
    meta: PaginationMeta = Field(..., description="페이지네이션 메타데이터")

# ✅ 베이스라인 검색 요청 스키마 - Updated
class BaselineSearchRequest(SQLModel):
    """베이스라인 검색 요청"""
    stock_codes: Optional[List[str]] = Field(None, description="검색할 종목 코드 목록", example=["005930", "035420"])
    min_price: Optional[int] = Field(None, description="최소 가격", example=40000)
    max_price: Optional[int] = Field(None, description="최대 가격", example=80000)
    min_quantity: Optional[int] = Field(None, description="최소 수량", example=5)
    max_quantity: Optional[int] = Field(None, description="최대 수량", example=100)
    min_low_price: Optional[int] = Field(None, description="최소 예상 최저 가격", example=38000)
    max_low_price: Optional[int] = Field(None, description="최대 예상 최저 가격", example=42000)
    min_high_price: Optional[int] = Field(None, description="최소 예상 최고 가격", example=78000)
    max_high_price: Optional[int] = Field(None, description="최대 예상 최고 가격", example=82000)
    step: Optional[int] = Field(None, description="특정 step", example=0)

# ✅ 베이스라인 일괄 업데이트 요청 스키마
class BulkUpdateRequest(SQLModel):
    """베이스라인 일괄 업데이트 요청"""
    updates: List[BaselineUpdate] = Field(..., description="업데이트할 베이스라인 목록")

# ✅ 베이스라인 일괄 업데이트 응답 스키마
class BulkUpdateResponse(SQLModel):
    """베이스라인 일괄 업데이트 응답"""
    total_requested: int = Field(..., description="요청된 총 개수", example=10)
    updated: int = Field(..., description="성공적으로 업데이트된 개수", example=8)
    not_found: int = Field(..., description="찾을 수 없는 항목 수", example=1)
    errors: int = Field(..., description="오류 발생한 개수", example=1)
    error_details: Optional[List[str]] = Field(None, description="오류 상세 내용")
    success_rate: float = Field(..., description="성공률 (%)", example=90.0)
    message: str = Field(..., description="작업 완료 메시지", example="일괄 업데이트 완료: 업데이트 8개, 미발견 1개, 오류 1개")

# ✅ 가격 범위 분석 응답 스키마 (새로 추가)
class PriceRangeAnalysisResponse(SQLModel):
    """가격 범위 분석 응답 스키마"""
    stock_code: str = Field(..., description="종목 코드", example="005930")
    total_baselines: int = Field(..., description="총 베이스라인 수", example=5)
    price_range_spread: Optional[float] = Field(None, description="평균 가격 범위 폭 (high - low)", example=5000.0)
    price_accuracy_ratio: Optional[float] = Field(None, description="가격 정확도 비율 (decision / (high+low)/2)", example=0.98)
    risk_assessment: str = Field(..., description="리스크 평가", example="LOW_RISK")  # LOW_RISK, MEDIUM_RISK, HIGH_RISK
    recommendation: str = Field(..., description="투자 권장 사항", example="적정 가격대에서 분할 매수 권장")

# ✅ 베이스라인 생성 시 가격 검증 요청 스키마 (새로 추가)
class BaselineCreateWithValidation(BaselineCreate):
    """가격 검증이 포함된 베이스라인 생성 요청"""
    validate_price_range: bool = Field(True, description="가격 범위 검증 수행 여부", example=True)
    max_price_deviation: Optional[float] = Field(0.1, description="허용 가격 편차 비율 (10% = 0.1)", example=0.1)
    