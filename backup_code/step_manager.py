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

# ✅ 특정 인덱스 거래 가격 제거
@router.delete("/delete-price/{code}/index/{index}", response_model=StepManagerRead)
async def delete_trade_price_by_index(
    request: Request,
    code: str,
    index: int
):
    """특정 인덱스의 거래 가격을 제거 (단계 동기화)"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        updated_manager = await step_manager_module.delete_trade_price_by_index(
            code=code,
            index=index
        )
        if not updated_manager:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {code}의 스텝매니저를 찾을 수 없거나 유효하지 않은 인덱스입니다"
            )
        return updated_manager
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"인덱스별 거래 가격 제거 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"가격 제거 실패: {str(e)}")

# ✅ 특정 인덱스 거래 가격 수정
@router.put("/update-price/{code}/index/{index}", response_model=StepManagerRead)
async def update_trade_price_by_index(
    request: Request,
    code: str,
    index: int,
    price_data: StepManagerPriceUpdate
):
    """특정 인덱스의 거래 가격을 수정"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        updated_manager = await step_manager_module.update_trade_price_by_index(
            code=code,
            index=index,
            new_price=price_data.trade_price
        )
        if not updated_manager:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {code}의 스텝매니저를 찾을 수 없거나 유효하지 않은 인덱스입니다"
            )
        return updated_manager
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"인덱스별 거래 가격 수정 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"가격 수정 실패: {str(e)}")

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

# ✅ 완전 거래된 포지션 조회
@router.get("/fully-traded", response_model=List[StepManagerRead])
async def get_fully_traded_positions(request: Request):
    """완전히 거래된 포지션 조회"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.get_fully_traded_positions()
    except Exception as e:
        logger.error(f"완전 거래 포지션 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 시장별 개수 조회
@router.get("/count-by-market", response_model=dict)
async def count_by_market(request: Request):
    """시장별 개수 조회"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.count_by_market()
    except Exception as e:
        logger.error(f"시장별 개수 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 타입별 개수 조회
@router.get("/count-by-type", response_model=dict)
async def count_by_type(request: Request):
    """타입별 개수 조회"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.count_by_type()
    except Exception as e:
        logger.error(f"타입별 개수 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 전체 통계 요약
@router.get("/summary", response_model=StepManagerSummaryResponse)
async def get_summary_statistics(request: Request):
    """전체 통계 요약"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.get_summary_statistics()
    except Exception as e:
        logger.error(f"통계 요약 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 최근 거래 조회
@router.get("/recent-trades", response_model=List[StepManagerRead])
async def get_recent_trades(
    request: Request,
    limit: int = 10
):
    """최근 거래 조회 (마지막 거래 시간 기준)"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.get_recent_trades(limit)
    except Exception as e:
        logger.error(f"최근 거래 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 거래 히스토리 요약 통계
@router.get("/trade-history-summary", response_model=StepManagerTradeHistoryResponse)
async def get_trade_history_summary(request: Request):
    """거래 히스토리 요약 통계"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        return await step_manager_module.get_trade_history_summary()
    except Exception as e:
        logger.error(f"거래 히스토리 요약 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 종목별 거래 상세 정보
@router.get("/trade-details/{code}", response_model=dict)
async def get_trade_details(
    request: Request,
    code: str
):
    """특정 종목의 거래 상세 정보"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        step_manager = await step_manager_module.get_by_code(code)
        if not step_manager:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {code}의 스텝매니저를 찾을 수 없습니다"
            )
        
        trade_prices = step_manager.last_trade_prices
        avg_price = step_manager.get_average_trade_price()
        
        details = {
            "stock_code": code,
            "current_step": step_manager.trade_step,
            "total_trades": len(trade_prices),
            "trade_prices": trade_prices,
            "average_trade_price": avg_price,
            "total_value": step_manager.total_value,
            "hold_value": step_manager.hold_value,
            "trade_value": step_manager.trade_value,
            "profit_loss": step_manager.profit_loss,
            "completion_rate": (step_manager.trade_qty / step_manager.total_qty * 100) if step_manager.total_qty > 0 else 0,
            "is_fully_traded": step_manager.is_fully_traded,
            "last_trade_time": step_manager.last_trade_time
        }
        
        # 각 단계별 가격 정보
        step_details = []
        for i, price in enumerate(trade_prices):
            step_details.append({
                "step": i,
                "price": price,
                "step_value": price * (step_manager.trade_qty // len(trade_prices)) if trade_prices else 0
            })
        
        details["step_details"] = step_details
        
        return details
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"거래 상세 정보 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 종목별 성과 분석
@router.get("/performance/{code}", response_model=dict)
async def get_performance_analysis(
    request: Request,
    code: str
):
    """특정 종목의 성과 분석"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        step_manager = await step_manager_module.get_by_code(code)
        if not step_manager:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {code}의 스텝매니저를 찾을 수 없습니다"
            )
        
        trade_prices = step_manager.last_trade_prices
        
        # 성과 분석
        performance = {
            "stock_code": code,
            "current_price": step_manager.final_price,
            "average_buy_price": step_manager.get_average_trade_price(),
            "total_investment": sum(trade_prices) if trade_prices else 0,
            "current_value": step_manager.hold_value,
            "unrealized_pnl": step_manager.profit_loss,
            "total_quantity": step_manager.total_qty,
            "traded_quantity": step_manager.trade_qty,
            "holding_quantity": step_manager.hold_qty,
            "completion_rate": (step_manager.trade_qty / step_manager.total_qty * 100) if step_manager.total_qty > 0 else 0
        }
        
        # 수익률 계산
        if trade_prices and step_manager.get_average_trade_price():
            avg_buy_price = step_manager.get_average_trade_price()
            return_rate = ((step_manager.final_price - avg_buy_price) / avg_buy_price) * 100
            performance["return_rate"] = round(return_rate, 2)
        else:
            performance["return_rate"] = 0
        
        # 위험도 평가
        if len(trade_prices) > 1:
            price_volatility = max(trade_prices) - min(trade_prices)
            volatility_rate = (price_volatility / step_manager.get_average_trade_price()) * 100 if step_manager.get_average_trade_price() else 0
            performance["price_volatility"] = price_volatility
            performance["volatility_rate"] = round(volatility_rate, 2)
            
            if volatility_rate < 5:
                performance["risk_level"] = "LOW"
            elif volatility_rate < 15:
                performance["risk_level"] = "MEDIUM"
            else:
                performance["risk_level"] = "HIGH"
        else:
            performance["price_volatility"] = 0
            performance["volatility_rate"] = 0
            performance["risk_level"] = "UNKNOWN"
        
        return performance
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"성과 분석 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"분석 실패: {str(e)}")

# ✅ 벌크 작업 - 여러 종목 거래 가격 추가
@router.post("/bulk-add-prices", response_model=dict)
async def bulk_add_trade_prices(
    request: Request,
    bulk_data: List[dict]  # [{"code": "005930", "trade_price": 190000}, ...]
):
    """여러 종목에 거래 가격을 한번에 추가"""
    step_manager_module = request.app.step_manager.step_manager_module()
    
    try:
        success_count = 0
        error_count = 0
        errors = []
        
        for data in bulk_data:
            try:
                code = data.get("code")
                trade_price = data.get("trade_price")
                
                if not code or not trade_price:
                    error_count += 1
                    errors.append(f"잘못된 데이터 형식: {data}")
                    continue
                
                updated_manager = await step_manager_module.add_trade_price(
                    code=code,
                    trade_price=trade_price
                )
                
                if updated_manager:
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f"종목 {code}: 스텝매니저를 찾을 수 없음")
                    
            except Exception as e:
                error_count += 1
                error_msg = f"종목 {data.get('code', 'UNKNOWN')}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        total_requested = len(bulk_data)
        success_rate = (success_count / total_requested * 100) if total_requested > 0 else 0
        
        result = {
            "total_requested": total_requested,
            "success": success_count,
            "errors": error_count,
            "success_rate": round(success_rate, 2),
            "error_details": errors if errors else None,
            "message": f"일괄 가격 추가 완료: 성공 {success_count}개, 오류 {error_count}개"
        }
        
        return result
        
    except Exception as e:
        logger.error(f"일괄 가격 추가 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"일괄 작업 실패: {str(e)}")

# ✅ 전체 포트폴리오 요약
@router.get("/portfolio-summary", response_model=dict)
async def get_portfolio_summary(request: Request):
    """전체 포트폴리오 요약 정보"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        all_managers = await step_manager_module.get_all()
        
        if not all_managers:
            return {
                "total_stocks": 0,
                "total_investment": 0,
                "total_current_value": 0,
                "total_hold_value": 0,
                "total_unrealized_pnl": 0,
                "overall_return_rate": 0,
                "active_positions": 0,
                "completed_positions": 0,
                "market_distribution": {},
                "type_distribution": {},
                "message": "포트폴리오가 비어있습니다"
            }
        
        # 포트폴리오 통계 계산
        total_stocks = len(all_managers)
        total_investment = 0
        total_current_value = 0
        total_hold_value = 0
        total_unrealized_pnl = 0
        active_positions = 0
        completed_positions = 0
        market_counts = {}
        type_counts = {True: 0, False: 0}
        
        for manager in all_managers:
            # 투자금액 계산 (평균 매수가 * 거래 수량)
            avg_price = manager.get_average_trade_price()
            if avg_price:
                total_investment += avg_price * manager.trade_qty
            
            # 현재 가치
            total_current_value += manager.final_price * manager.trade_qty
            total_hold_value += manager.hold_value
            
            # 손익
            if manager.profit_loss:
                total_unrealized_pnl += manager.profit_loss
            
            # 포지션 상태
            if manager.hold_qty > 0:
                active_positions += 1
            if manager.is_fully_traded:
                completed_positions += 1
            
            # 시장별 분포
            market = manager.market
            market_counts[market] = market_counts.get(market, 0) + 1
            
            # 타입별 분포
            type_counts[manager.type] += 1
        
        # 전체 수익률 계산
        overall_return_rate = 0
        if total_investment > 0:
            overall_return_rate = ((total_current_value - total_investment) / total_investment) * 100
        
        portfolio_summary = {
            "total_stocks": total_stocks,
            "total_investment": round(total_investment, 2),
            "total_current_value": total_current_value,
            "total_hold_value": total_hold_value,
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "overall_return_rate": round(overall_return_rate, 2),
            "active_positions": active_positions,
            "completed_positions": completed_positions,
            "completion_rate": round((completed_positions / total_stocks * 100), 2) if total_stocks > 0 else 0,
            "market_distribution": market_counts,
            "type_distribution": type_counts,
            "average_position_size": round(total_current_value / total_stocks, 2) if total_stocks > 0 else 0
        }
        
        return portfolio_summary
        
    except Exception as e:
        logger.error(f"포트폴리오 요약 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 가격 범위별 검색
@router.get("/search-by-price-range", response_model=List[StepManagerRead])
async def search_by_price_range(
    request: Request,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_avg_price: Optional[float] = None,
    max_avg_price: Optional[float] = None
):
    """가격 범위로 스텝 매니저 검색"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        all_managers = await step_manager_module.get_all()
        filtered_managers = []
        
        for manager in all_managers:
            # 현재가 범위 확인
            if min_price and manager.final_price < min_price:
                continue
            if max_price and manager.final_price > max_price:
                continue
            
            # 평균 거래가 범위 확인
            avg_price = manager.get_average_trade_price()
            if min_avg_price and (not avg_price or avg_price < min_avg_price):
                continue
            if max_avg_price and (not avg_price or avg_price > max_avg_price):
                continue
            
            filtered_managers.append(manager)
        
        return filtered_managers
        
    except Exception as e:
        logger.error(f"가격 범위 검색 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"검색 실패: {str(e)}")

# ✅ 거래 단계별 통계
@router.get("/step-statistics", response_model=dict)
async def get_step_statistics(request: Request):
    """거래 단계별 통계 정보"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        all_managers = await step_manager_module.get_all()
        
        step_stats = {}
        step_values = {}
        
        for manager in all_managers:
            step = manager.trade_step
            
            # 단계별 개수
            if step not in step_stats:
                step_stats[step] = {
                    "count": 0,
                    "total_value": 0,
                    "stocks": []
                }
            
            step_stats[step]["count"] += 1
            step_stats[step]["total_value"] += manager.trade_value
            step_stats[step]["stocks"].append(manager.code)
        
        # 단계별 평균 계산
        for step, stats in step_stats.items():
            stats["average_value"] = round(stats["total_value"] / stats["count"], 2) if stats["count"] > 0 else 0
        
        return {
            "step_distribution": step_stats,
            "total_steps": len(step_stats),
            "most_common_step": max(step_stats.items(), key=lambda x: x[1]["count"])[0] if step_stats else None,
            "step_progression": {
                "step_0": step_stats.get(0, {}).get("count", 0),
                "step_1": step_stats.get(1, {}).get("count", 0),
                "step_2": step_stats.get(2, {}).get("count", 0),
                "step_3_plus": sum(stats["count"] for step, stats in step_stats.items() if step >= 3)
            }
        }
        
    except Exception as e:
        logger.error(f"단계별 통계 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 리밸런싱 추천
@router.get("/rebalancing-recommendations", response_model=dict)
async def get_rebalancing_recommendations(request: Request):
    """포트폴리오 리밸런싱 추천"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        all_managers = await step_manager_module.get_all()
        
        if not all_managers:
            return {
                "total_stocks": 0,
                "recommendations": [],
                "message": "분석할 포트폴리오가 없습니다"
            }
        
        recommendations = []
        
        for manager in all_managers:
            recommendation = {
                "stock_code": manager.code,
                "current_step": manager.trade_step,
                "completion_rate": round((manager.trade_qty / manager.total_qty * 100), 2) if manager.total_qty > 0 else 0,
                "action": "HOLD",
                "reason": "",
                "priority": "LOW"
            }
            
            # 분석 및 추천
            completion_rate = (manager.trade_qty / manager.total_qty * 100) if manager.total_qty > 0 else 0
            avg_price = manager.get_average_trade_price()
            current_price = manager.final_price
            
            if completion_rate == 0:
                recommendation["action"] = "START_BUYING"
                recommendation["reason"] = "아직 매수를 시작하지 않았습니다"
                recommendation["priority"] = "HIGH"
            elif completion_rate < 50:
                if avg_price and current_price < avg_price * 0.95:  # 5% 이상 하락
                    recommendation["action"] = "INCREASE_POSITION"
                    recommendation["reason"] = "평균 매수가 대비 5% 이상 하락으로 추가 매수 기회"
                    recommendation["priority"] = "HIGH"
                else:
                    recommendation["action"] = "CONTINUE_BUYING"
                    recommendation["reason"] = "계획된 단계적 매수를 계속 진행"
                    recommendation["priority"] = "MEDIUM"
            elif completion_rate < 80:
                recommendation["action"] = "MONITOR"
                recommendation["reason"] = "대부분 매수 완료, 시장 상황 모니터링"
                recommendation["priority"] = "LOW"
            elif completion_rate >= 100:
                if avg_price and current_price > avg_price * 1.1:  # 10% 이상 상승
                    recommendation["action"] = "CONSIDER_SELLING"
                    recommendation["reason"] = "평균 매수가 대비 10% 이상 상승으로 수익 실현 고려"
                    recommendation["priority"] = "MEDIUM"
                else:
                    recommendation["action"] = "HOLD"
                    recommendation["reason"] = "매수 완료, 장기 보유"
                    recommendation["priority"] = "LOW"
            
            recommendations.append(recommendation)
        
        # 우선순위별 정렬
        priority_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 0), reverse=True)
        
        # 요약 통계
        action_counts = {}
        priority_counts = {}
        
        for rec in recommendations:
            action = rec["action"]
            priority = rec["priority"]
            
            action_counts[action] = action_counts.get(action, 0) + 1
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
        
        return {
            "total_stocks": len(all_managers),
            "recommendations": recommendations,
            "summary": {
                "action_distribution": action_counts,
                "priority_distribution": priority_counts,
                "high_priority_count": priority_counts.get("HIGH", 0)
            },
            "message": f"총 {len(recommendations)}개 종목에 대한 리밸런싱 추천이 생성되었습니다"
        }
        
    except Exception as e:
        logger.error(f"리밸런싱 추천 생성 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"추천 생성 실패: {str(e)}")

# ✅ 종목 비교 분석
@router.post("/compare-stocks", response_model=dict)
async def compare_stocks(
    request: Request,
    stock_codes: List[str]
):
    """여러 종목의 비교 분석"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        if len(stock_codes) < 2:
            raise HTTPException(
                status_code=400,
                detail="비교를 위해서는 최소 2개 이상의 종목이 필요합니다"
            )
        
        comparisons = []
        not_found = []
        
        for code in stock_codes:
            manager = await step_manager_module.get_by_code(code)
            if not manager:
                not_found.append(code)
                continue
            
            avg_price = manager.get_average_trade_price()
            return_rate = 0
            if avg_price:
                return_rate = ((manager.final_price - avg_price) / avg_price) * 100
            
            comparison = {
                "stock_code": code,
                "current_price": manager.final_price,
                "average_buy_price": avg_price,
                "trade_step": manager.trade_step,
                "completion_rate": round((manager.trade_qty / manager.total_qty * 100), 2) if manager.total_qty > 0 else 0,
                "return_rate": round(return_rate, 2),
                "trade_value": manager.trade_value,
                "hold_value": manager.hold_value,
                "unrealized_pnl": manager.profit_loss,
                "market": manager.market,
                "type": manager.type
            }
            
            comparisons.append(comparison)
        
        if not comparisons:
            return {
                "compared_stocks": 0,
                "not_found": not_found,
                "comparisons": [],
                "message": "비교할 수 있는 종목이 없습니다"
            }
        
        # 비교 통계
        best_performer = max(comparisons, key=lambda x: x["return_rate"])
        worst_performer = min(comparisons, key=lambda x: x["return_rate"])
        highest_completion = max(comparisons, key=lambda x: x["completion_rate"])
        most_valuable = max(comparisons, key=lambda x: x["hold_value"])
        
        return {
            "compared_stocks": len(comparisons),
            "not_found": not_found,
            "comparisons": comparisons,
            "analysis": {
                "best_performer": {
                    "stock_code": best_performer["stock_code"],
                    "return_rate": best_performer["return_rate"]
                },
                "worst_performer": {
                    "stock_code": worst_performer["stock_code"],
                    "return_rate": worst_performer["return_rate"]
                },
                "highest_completion": {
                    "stock_code": highest_completion["stock_code"],
                    "completion_rate": highest_completion["completion_rate"]
                },
                "most_valuable": {
                    "stock_code": most_valuable["stock_code"],
                    "hold_value": most_valuable["hold_value"]
                },
                "average_return_rate": round(sum(c["return_rate"] for c in comparisons) / len(comparisons), 2),
                "average_completion_rate": round(sum(c["completion_rate"] for c in comparisons) / len(comparisons), 2)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"종목 비교 분석 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"비교 분석 실패: {str(e)}")

# ✅ 위험도 분석
@router.get("/risk-analysis", response_model=dict)
async def get_risk_analysis(request: Request):
    """전체 포트폴리오의 위험도 분석"""
    step_manager_module = request.app.step_manager.step_manager_module()
    try:
        all_managers = await step_manager_module.get_all()
        
        if not all_managers:
            return {
                "total_stocks": 0,
                "overall_risk_level": "UNKNOWN",
                "message": "분석할 포트폴리오가 없습니다"
            }
        
        risk_analysis = {
            "total_stocks": len(all_managers),
            "risk_distribution": {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "UNKNOWN": 0},
            "concentration_risk": {},
            "market_exposure": {},
            "step_concentration": {},
            "recommendations": []
        }
        
        total_value = sum(manager.hold_value for manager in all_managers)
        
        for manager in all_managers:
            trade_prices = manager.last_trade_prices
            
            # 개별 종목 위험도 계산
            if len(trade_prices) > 1:
                price_volatility = max(trade_prices) - min(trade_prices)
                avg_price = manager.get_average_trade_price()
                volatility_rate = (price_volatility / avg_price) * 100 if avg_price else 0
                
                if volatility_rate < 5:
                    risk_level = "LOW"
                elif volatility_rate < 15:
                    risk_level = "MEDIUM"
                else:
                    risk_level = "HIGH"
            else:
                risk_level = "UNKNOWN"
            
            risk_analysis["risk_distribution"][risk_level] += 1
            
            # 집중도 위험 (개별 종목이 전체 포트폴리오에서 차지하는 비중)
            concentration = (manager.hold_value / total_value * 100) if total_value > 0 else 0
            if concentration > 20:  # 20% 이상이면 높은 집중도
                risk_analysis["recommendations"].append(
                    f"종목 {manager.code}의 비중이 {concentration:.1f}%로 높습니다. 분산투자를 고려하세요."
                )
            
            # 시장 노출도
            market = manager.market
            risk_analysis["market_exposure"][market] = risk_analysis["market_exposure"].get(market, 0) + 1
            
            # 단계 집중도
            step = manager.trade_step
            risk_analysis["step_concentration"][step] = risk_analysis["step_concentration"].get(step, 0) + 1
        
        # 전체 위험도 평가
        high_risk_count = risk_analysis["risk_distribution"]["HIGH"]
        total_stocks = len(all_managers)
        high_risk_ratio = (high_risk_count / total_stocks) * 100 if total_stocks > 0 else 0
        
        if high_risk_ratio > 30:
            risk_analysis["overall_risk_level"] = "HIGH"
            risk_analysis["recommendations"].append("고위험 종목의 비중이 높습니다. 리스크 관리가 필요합니다.")
        elif high_risk_ratio > 15:
            risk_analysis["overall_risk_level"] = "MEDIUM"
            risk_analysis["recommendations"].append("적정 수준의 위험도를 유지하고 있습니다.")
        else:
            risk_analysis["overall_risk_level"] = "LOW"
            risk_analysis["recommendations"].append("전반적으로 안정적인 포트폴리오입니다.")
        
        # 시장 집중도 확인
        if len(risk_analysis["market_exposure"]) == 1:
            risk_analysis["recommendations"].append("단일 시장에만 투자되어 있습니다. 시장 분산을 고려하세요.")
        
        return risk_analysis
        
    except Exception as e:
        logger.error(f"위험도 분석 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"분석 실패: {str(e)}")