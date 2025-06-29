# api/realtime_group_api.py
from fastapi import APIRouter, HTTPException, Request, status
from typing import List
import logging

from schemas.realtime_group_schema import (
    RealtimeGroupCreate, 
    RealtimeGroupRead, 
    RealtimeGroupUpdate,
    RealtimeGroupStrategyUpdate,
    GroupDeleteResponse,
    StockCodeManage
)

router = APIRouter()
logger = logging.getLogger(__name__)

# ✅ 새 실시간 그룹 생성
@router.post("/", response_model=RealtimeGroupRead, status_code=status.HTTP_201_CREATED)
async def create_new(
    request: Request,
    group_data: RealtimeGroupCreate
):
    """새로운 실시간 그룹 생성"""
    realtime_group_module = request.app.realtime_group.realtime_group_module()
    try:
        return await realtime_group_module.create_new(
            group_data.group,
            group_data.data_type,
            group_data.stock_code,
            group_data.strategy
        )
    except Exception as e:
        logger.error(f"실시간 그룹 생성 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"생성 실패: {str(e)}")

# ✅ 특정 그룹 조회
@router.get("/{group_id}", response_model=RealtimeGroupRead)
async def get_by_group(
    request: Request,
    group_id: int
):
    """특정 그룹 조회"""
    realtime_group_module = request.app.realtime_group.realtime_group_module()
    try:
        group = await realtime_group_module.get_by_group(group_id)
        if not group:
            raise HTTPException(
                status_code=404, 
                detail=f"그룹 {group_id}를 찾을 수 없습니다"
            )
        return group
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"실시간 그룹 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 모든 그룹 조회
@router.get("/", response_model=List[RealtimeGroupRead])
async def get_all_groups(
    request: Request
):
    """모든 실시간 그룹 조회"""
    realtime_group_module = request.app.realtime_group.realtime_group_module()
    try:
        groups = await realtime_group_module.get_all_groups()
        return groups
    except Exception as e:
        logger.error(f"실시간 그룹 목록 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 특정 그룹의 전략만 업데이트
@router.patch("/{group_id}/strategy", response_model=RealtimeGroupRead)
async def update_strategy(
    request: Request,
    group_id: int,
    strategy_data: RealtimeGroupStrategyUpdate
):
    """특정 그룹의 전략만 업데이트"""
    realtime_group_module = request.app.realtime_group.realtime_group_module()
    try:
        updated_group = await realtime_group_module.update_strategy(
            group_id,
            strategy_data.strategy
        )
        if not updated_group:
            raise HTTPException(
                status_code=404,
                detail=f"그룹 {group_id}를 찾을 수 없습니다"
            )
        return updated_group
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"전략 업데이트 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"전략 업데이트 실패: {str(e)}")

# ✅ 특정 그룹 업데이트
@router.put("/{group_id}", response_model=RealtimeGroupRead)
async def update_by_group(
    request: Request,
    group_id: int,
    group_data: RealtimeGroupUpdate
):
    """특정 그룹의 전략, 데이터 타입 및 종목 코드 업데이트"""
    realtime_group_module = request.app.realtime_group.realtime_group_module()
    try:
        updated_group = await realtime_group_module.update_by_group(
            group_id,
            group_data.strategy,
            group_data.data_type,
            group_data.stock_code
        )
        if not updated_group:
            raise HTTPException(
                status_code=404,
                detail=f"그룹 {group_id}를 찾을 수 없습니다"
            )
        return updated_group
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"실시간 그룹 업데이트 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"업데이트 실패: {str(e)}")

# ✅ 특정 그룹에 종목 코드 추가
@router.post("/{group_id}/add-stock", response_model=RealtimeGroupRead)
async def add_stock_to_group(
    request: Request,
    group_id: int,
    stock_data: str
):
    """특정 그룹에 종목 코드 추가"""
    realtime_group_module = request.app.realtime_group.realtime_group_module()
    try:
        updated_group = await realtime_group_module.add_stock_to_group(
            group_id,
            stock_data
        )
        if not updated_group:
            raise HTTPException(
                status_code=404,
                detail=f"그룹 {group_id}를 찾을 수 없습니다"
            )
        return updated_group
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"종목 코드 추가 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"종목 코드 추가 실패: {str(e)}")

# ✅ 특정 그룹에 데이터 타입 추가
@router.post("/{group_id}/add-datatype")
async def add_data_type_to_group(
    request: Request,
    group_id: int,
    data_type: str
):
    """특정 그룹에 데이터 타입 추가"""
    realtime_group_module = request.app.realtime_group.realtime_group_module()
    try:
        updated_group = await realtime_group_module.add_data_type_to_group(
            group_id,
            data_type
        )
        if not updated_group:
            raise HTTPException(
                status_code=404,
                detail=f"그룹 {group_id}를 찾을 수 없습니다"
            )
        return updated_group
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"데이터 타입 추가 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"데이터 타입 추가 실패: {str(e)}")

# ✅ 특정 그룹에서 종목 코드 제거
@router.delete("/{group_id}/remove-stock", response_model=RealtimeGroupRead)
async def remove_stock_from_group(
    request: Request,
    group_id: int,
    stock_data: StockCodeManage
):
    """특정 그룹에서 종목 코드 제거"""
    realtime_group_module = request.app.realtime_group.realtime_group_module()
    try:
        updated_group = await realtime_group_module.remove_stock_from_group(
            group_id,
            stock_data.stock_code
        )
        if not updated_group:
            raise HTTPException(
                status_code=404,
                detail=f"그룹 {group_id}를 찾을 수 없습니다"
            )
        return updated_group
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"종목 코드 제거 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"종목 코드 제거 실패: {str(e)}")

# ✅ 특정 그룹에서 데이터 타입 제거
@router.delete("/{group_id}/remove-datatype")
async def remove_data_type_from_group(
    request: Request,
    group_id: int,
    data_type: str
):
    """특정 그룹에서 데이터 타입 제거"""
    realtime_group_module = request.app.realtime_group.realtime_group_module()
    try:
        updated_group = await realtime_group_module.remove_data_type_from_group(
            group_id,
            data_type
        )
        if not updated_group:
            raise HTTPException(
                status_code=404,
                detail=f"그룹 {group_id}를 찾을 수 없습니다"
            )
        return updated_group
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"데이터 타입 제거 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"데이터 타입 제거 실패: {str(e)}")

# ✅ 특정 그룹 삭제
@router.delete("/{group_id}", response_model=GroupDeleteResponse)
async def delete_by_group(
    request: Request,
    group_id: int
):
    """특정 그룹 삭제"""
    realtime_group_module = request.app.realtime_group.realtime_group_module()
    try:
        deleted = await realtime_group_module.delete_by_group(group_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"그룹 {group_id}를 찾을 수 없습니다"
            )
        return GroupDeleteResponse(
            message=f"그룹 {group_id}가 삭제되었습니다",
            group_id=group_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"실시간 그룹 삭제 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"삭제 실패: {str(e)}")