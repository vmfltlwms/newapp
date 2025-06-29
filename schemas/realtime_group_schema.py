# schemas/realtime_group_schema.py
from typing import List, Optional
from sqlmodel import ARRAY, Column, SQLModel, Field, String
from typing import List, Optional
from models.models import Realtime_Group


class RealtimeGroupCreate(SQLModel):
    """실시간 그룹 생성용 스키마"""
    group: int = Field(..., description="그룹 ID", ge=0)
    strategy: int = Field(default=1, description="전략 번호", ge=1)
    data_type: List[str] = Field(..., description="데이터 타입 목록", min_length=0)
    stock_code: List[str] = Field(..., description="종목 코드 목록", min_length=0)
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "group": 1,
                "strategy": 1,
                "data_type": [],
                "stock_code": []
            }
        }
    }

class RealtimeGroupRead(SQLModel):
    """실시간 그룹 조회용 스키마"""
    group: int = Field(..., description="그룹 ID")
    strategy: int = Field(..., description="전략 번호")
    data_type: List[str] = Field(..., description="데이터 타입 목록")
    stock_code: List[str] = Field(..., description="종목 코드 목록")
    
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "group": 1,
                "strategy": 1,
                "data_type": ["0B"],
                "stock_code": ["005930", "000660"]
            }
        }
    }

class RealtimeGroupUpdate(SQLModel):
    """실시간 그룹 업데이트용 스키마"""
    strategy: Optional[int] = Field(None, description="전략 번호", ge=1)
    data_type: Optional[List[str]] = Field(None, description="데이터 타입 목록")
    stock_code: Optional[List[str]] = Field(None, description="종목 코드 목록")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "strategy": 2,
                "data_type": [],
                "stock_code": []
            }
        }
    }

class RealtimeGroupStrategyUpdate(SQLModel):
    """실시간 그룹 전략 업데이트용 스키마"""
    strategy: int = Field(..., description="새로운 전략 번호", ge=1)
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "strategy": 1
            }
        }
    }

class StockCodeManage(SQLModel):
    """종목 코드 관리용 스키마 (추가/제거)"""
    stock_code: str = Field(..., description="종목 코드", min_length=1)
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "stock_code": "005930"
            }
        }
    }

class DataTypeManage(SQLModel):
    """데이터 타입 관리용 스키마 (추가/제거)"""
    data_type: str = Field(..., description="데이터 타입", min_length=1)
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "data_type": "0B"
            }
        }
    }

class GroupDeleteResponse(SQLModel):
    """그룹 삭제 응답용 스키마"""
    message: str = Field(..., description="삭제 결과 메시지")
    group_id: int = Field(..., description="삭제된 그룹 ID")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "그룹 1가 삭제되었습니다",
                "group_id": 1
            }
        }
    }

class StockManageResponse(SQLModel):
    """종목 코드 관리 응답용 스키마"""
    message: str = Field(..., description="작업 결과 메시지")
    group_id: int = Field(..., description="대상 그룹 ID")
    stock_code: str = Field(..., description="추가/제거된 종목 코드")
    action: str = Field(..., description="수행된 작업 (add/remove)")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "종목 코드가 성공적으로 추가되었습니다",
                "group_id": 1,
                "stock_code": "005930",
                "action": "add"
            }
        }
    }

class DataTypeManageResponse(SQLModel):
    """데이터 타입 관리 응답용 스키마"""
    message: str = Field(..., description="작업 결과 메시지")
    group_id: int = Field(..., description="대상 그룹 ID")
    data_type: str = Field(..., description="추가/제거된 데이터 타입")
    action: str = Field(..., description="수행된 작업 (add/remove)")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "데이터 타입이 성공적으로 추가되었습니다",
                "group_id": 1,
                "data_type": "0B",
                "action": "add"
            }
        }
    }