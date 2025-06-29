from fastapi import APIRouter, HTTPException, Request, status
from typing import List, Optional
import logging
from datetime import datetime

from schemas.step_manager_schema import (
    StepManagerCreate, 
    StepManagerRead, 
    StepManagerUpdate,
    StepManagerTradeUpdate,
    StepManagerPriceUpdate,
    StepManagerSummaryResponse,
    StepManagerTradeHistoryResponse,
    DeleteResponse,
    SingleDeleteResponse
)

router = APIRouter()
logger = logging.getLogger(__name__)

# ✅ 새 스텝 매니저 생성
@router.post("/", response_model=StepManagerRead, status_code=status.HTTP_201_CREATED)
async def create_new(
    request: Request,
    step_manager_data: StepManagerCreate
):
    """새로운 스텝 매니저 생성"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.create_new(
            code=step_manager_data.code,
            type=step_manager_data.type,
            market=step_manager_data.market,
            final_price=step_manager_data.final_price,
            total_qty=step_manager_data.total_qty,
            trade_qty=step_manager_data.trade_qty,
            trade_step=step_manager_data.trade_step,
            hold_qty=step_manager_data.hold_qty,
            last_trade_time=step_manager_data.last_trade_time,
            last_trade_prices=step_manager_data.last_trade_prices
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"스텝매니저 생성 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"생성 실패: {str(e)}")

# ✅ 종목 코드로 스텝 매니저 조회
@router.get("/code/{code}", response_model=StepManagerRead)
async def get_by_code(
    request: Request,
    code: str
):
    """종목 코드로 스텝 매니저 조회"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        step_manager = await step_manager_module.get_by_code(code)
        if not step_manager:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {code}의 스텝매니저를 찾을 수 없습니다"
            )
        return step_manager
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스텝매니저 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 모든 스텝 매니저 조회
@router.get("/all", response_model=List[StepManagerRead])
async def get_all(request: Request):
    """모든 스텝 매니저 조회"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.get_all()
    except Exception as e:
        logger.error(f"전체 스텝매니저 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 모든 스텝 매니저 삭제
@router.delete("/delete-all", response_model=DeleteResponse)
async def delete_all(
    request: Request
):
    """모든 스텝 매니저 삭제"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        deleted_count = 0
        codes = await step_manager_module.get_all_codes()
        
        for code in codes:
            deleted = await step_manager_module.delete_by_code(code)
            if deleted:
                deleted_count += 1
        
        logger.info(f"{deleted_count}개 스텝매니저 삭제완료")
        
        return DeleteResponse(
            message=f"총 {deleted_count}개의 스텝매니저가 삭제되었습니다",
            deleted_count=deleted_count
        )
    except Exception as e:
        logger.error(f"전체 스텝매니저 삭제 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"삭제 실패: {str(e)}")

# ✅ 시장별 스텝 매니저 조회
@router.get("/market/{market}", response_model=List[StepManagerRead])
async def get_by_market(
    request: Request,
    market: str
):
    """시장별 스텝 매니저 조회 (kospi, kosdaq, all)"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.get_by_market(market)
    except Exception as e:
        logger.error(f"시장별 스텝매니저 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 타입별 스텝 매니저 조회
@router.get("/type/{type_value}", response_model=List[StepManagerRead])
async def get_by_type(
    request: Request,
    type_value: bool
):
    """타입별 스텝 매니저 조회"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.get_by_type(type_value)
    except Exception as e:
        logger.error(f"타입별 스텝매니저 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 거래 단계별 스텝 매니저 조회
@router.get("/trade-step/{trade_step}", response_model=List[StepManagerRead])
async def get_by_trade_step(
    request: Request,
    trade_step: int
):
    """거래 단계별 스텝 매니저 조회"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.get_by_trade_step(trade_step)
    except Exception as e:
        logger.error(f"거래 단계별 스텝매니저 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 스텝 매니저 업데이트
@router.put("/update/{code}", response_model=StepManagerRead)
async def update_by_code(
    request: Request,
    code: str,
    update_data: StepManagerUpdate
):
    """종목 코드로 스텝 매니저 업데이트"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        updated_manager = await step_manager_module.update_by_code(
            code=code,
            final_price=update_data.final_price,
            total_qty=update_data.total_qty,
            trade_qty=update_data.trade_qty,
            trade_step=update_data.trade_step,
            hold_qty=update_data.hold_qty,
            last_trade_time=update_data.last_trade_time,
            last_trade_prices=update_data.last_trade_prices
        )
        if not updated_manager:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {code}의 스텝매니저를 찾을 수 없습니다"
            )
        return updated_manager
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스텝매니저 업데이트 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"업데이트 실패: {str(e)}")

# ✅ 거래 정보 업데이트
@router.put("/update-trade/{code}", response_model=StepManagerRead)
async def update_trade_info(
    request: Request,
    code: str,
    trade_data: StepManagerTradeUpdate
):
    """거래 정보 업데이트 (거래 수량, 단계, 가격)"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        updated_manager = await step_manager_module.update_trade_info(
            code=code,
            trade_qty=trade_data.trade_qty,
            trade_step=trade_data.trade_step,
            trade_price=trade_data.trade_price
        )
        if not updated_manager:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {code}의 스텝매니저를 찾을 수 없습니다"
            )
        return updated_manager
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"거래 정보 업데이트 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"업데이트 실패: {str(e)}")

# ✅ 거래 가격 추가
@router.post("/add-price/{code}", response_model=StepManagerRead)
async def add_trade_price(
    request: Request,
    code: str,
    price_data: StepManagerPriceUpdate
):
    """특정 종목의 거래 가격을 리스트에 추가하고 단계 +1"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        updated_manager = await step_manager_module.add_trade_price(
            code=code,
            trade_price=price_data.trade_price
        )
        if not updated_manager:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {code}의 스텝매니저를 찾을 수 없습니다"
            )
        return updated_manager
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"거래 가격 추가 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"가격 추가 실패: {str(e)}")

# ✅ 거래 가격 제거
@router.delete("/delete-price/{code}", response_model=StepManagerRead)
async def delete_trade_price(
    request: Request,
    code: str
):
    """특정 종목의 마지막 거래 가격을 제거하고 단계 -1"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        updated_manager = await step_manager_module.delete_trade_price(code)
        if not updated_manager:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {code}의 스텝매니저를 찾을 수 없거나 거래 가격이 없습니다"
            )
        return updated_manager
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"거래 가격 제거 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"가격 제거 실패: {str(e)}")

# ✅ 거래 단계와 가격 리스트 동기화
@router.put("/sync-step/{code}", response_model=StepManagerRead)
async def sync_trade_step_with_prices(
    request: Request,
    code: str
):
    """거래 단계를 거래 가격 리스트 길이와 동기화"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        updated_manager = await step_manager_module.sync_trade_step_with_prices(code)
        if not updated_manager:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {code}의 스텝매니저를 찾을 수 없습니다"
            )
        return updated_manager
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"단계 동기화 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"동기화 실패: {str(e)}")

# ✅ 거래 가격 리스트 초기화
@router.delete("/reset-prices/{code}", response_model=StepManagerRead)
async def reset_trade_prices(
    request: Request,
    code: str
):
    """특정 종목의 거래 가격 리스트 초기화"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        updated_manager = await step_manager_module.reset_trade_prices(code)
        if not updated_manager:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {code}의 스텝매니저를 찾을 수 없습니다"
            )
        return updated_manager
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"거래 가격 초기화 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"초기화 실패: {str(e)}")

# ✅ 스텝 매니저 삭제
@router.delete("/delete/{code}", response_model=SingleDeleteResponse)
async def delete_by_code(
    request: Request,
    code: str
):
    """종목 코드로 스텝 매니저 삭제"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        deleted = await step_manager_module.delete_by_code(code)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {code}의 스텝매니저를 찾을 수 없습니다"
            )
        return SingleDeleteResponse(
            message=f"종목 {code}의 스텝매니저가 삭제되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스텝매니저 삭제 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"삭제 실패: {str(e)}")

# ✅ 등록된 모든 종목 코드 조회
@router.get("/codes", response_model=List[str])
async def get_all_codes(request: Request):
    """등록된 모든 종목 코드 조회"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.get_all_codes()
    except Exception as e:
        logger.error(f"종목 코드 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 활성 포지션 조회
@router.get("/active-positions", response_model=List[StepManagerRead])
async def get_active_positions(request: Request):
    """보유 수량이 있는 포지션 조회"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.get_active_positions()
    except Exception as e:
        logger.error(f"활성 포지션 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

