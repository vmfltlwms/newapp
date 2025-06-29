# schemas/kiwoom_schemas.py - 개선 버전
from sqlmodel import SQLModel, Field
from typing import List, Optional
from enum import Enum


# Enum 정의
class MarketType(str, Enum):
    KOSPI = "K"
    KOSDAQ = "Q"
    ALL = "A"


class SearchType(str, Enum):
    NORMAL = "0"
    REALTIME = "1"


class DataType(str, Enum):
    CURRENT_PRICE = "현재가"
    CHANGE_RATE = "등락률"
    VOLUME = "거래량"
    HIGH_PRICE = "고가"
    LOW_PRICE = "저가"


# 개선된 스키마들
class RealtimePriceRequest(SQLModel):
    group_no: str = Field(default="1", description="그룹 번호")
    items: List[str] = Field(..., description="종목 코드 리스트", min_items=1)
    data_types: List[str] = Field(..., description="데이터 타입 리스트", min_items=1)
    refresh: bool = Field(default=True, description="기존 등록 유지 여부")
    
    class Config:
        schema_extra = {
            "example": {
                "group_no": "1",
                "items": ["005930", "000660"],
                "data_types": ["현재가", "등락률"],
                "refresh": True
            }
        }


class RealtimePriceUnsubscribeRequest(SQLModel):
    group_no: str = Field(default="1", description="그룹 번호")
    items: Optional[List[str]] = Field(default=None, description="취소할 종목 코드 리스트")
    data_types: Optional[List[str]] = Field(default=None, description="취소할 데이터 타입 리스트")
    
    class Config:
        schema_extra = {
            "example": {
                "group_no": "1",
                "items": ["005930"],
                "data_types": ["현재가"]
            }
        }


class ConditionalSearchRequest(SQLModel):
    seq: str = Field(..., description="조건식 시퀀스")
    search_type: SearchType = Field(default=SearchType.NORMAL, description="검색 타입")
    market_type: MarketType = Field(default=MarketType.KOSPI, description="시장 구분")
    cont_yn: str = Field(default="N", description="연속 조회 여부 (Y/N)")
    next_key: str = Field(default="", description="다음 조회 키")
    
    class Config:
        schema_extra = {
            "example": {
                "seq": "4",
                "search_type": "0",
                "market_type": "K",
                "cont_yn": "N",
                "next_key": ""
            }
        }


class StockInfo(SQLModel):
    code: str = Field(..., description="종목 코드", min_length=6, max_length=6)
    name: str = Field(..., description="종목명")
    market: str = Field(..., description="시장 구분")
    price: float = Field(..., description="현재가", ge=0)
    change: float = Field(..., description="등락액")
    change_ratio: float = Field(..., description="등락률")
    volume: int = Field(..., description="거래량", ge=0)


class StockRegistration(SQLModel):
    items: List[str] = Field(..., description="종목 코드 리스트", min_items=1)
    types: List[str] = Field(..., description="데이터 타입 리스트", min_items=1)
    refresh: bool = Field(default=False, description="새로고침 여부")


class GroupRegistration(SQLModel):
    group_no: str = Field(..., description="그룹 번호")
    registration: StockRegistration = Field(..., description="주식 등록 정보")


# 응답 스키마들
class RealtimePriceResponse(SQLModel):
    group_no: str
    item_code: str
    item_name: str
    current_price: int
    change_rate: float
    volume: int
    timestamp: str


class ConditionalSearchResponse(SQLModel):
    items: List[StockInfo]
    total_count: int
    next_key: Optional[str] = None
    has_more: bool = False