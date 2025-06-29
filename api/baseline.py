from fastapi import APIRouter, HTTPException, Request, status
from typing import List, Optional
import logging

from schemas.base_line_schema import (
    BaselineCreate, 
    BaselineRead, 
    BaselineUpdate,
    LastStepResponse,
    DeleteResponse,
    SingleDeleteResponse,
    BaselineSummaryResponse,
    BulkCreateRequest,
    BulkCreateResponse
)

router = APIRouter()
logger = logging.getLogger(__name__)

# ✅ 새 베이스라인 생성 (step=0) - Updated with low_price, high_price
@router.post("/", response_model=BaselineRead, status_code=status.HTTP_201_CREATED)
async def create_new(
    request: Request,
    baseline_data: BaselineCreate
):
    """해당 코드에 베이스라인이 없다면 step 0으로 새로운 베이스라인 생성"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        return await baseline_module.create_new(
            stock_code=baseline_data.stock_code,
            decision_price=baseline_data.decision_price,
            quantity=baseline_data.quantity,
            low_price=baseline_data.low_price,
            high_price=baseline_data.high_price
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"생성 실패: {str(e)}")

# ✅ 특정 종목에 새로운 step 추가 - Updated with low_price, high_price
@router.post("/add-step", response_model=BaselineRead, status_code=status.HTTP_201_CREATED)
async def add_step(
    request: Request,
    baseline_data: BaselineCreate
):
    """특정 종목에 새로운 step의 베이스라인 추가 (자동으로 다음 step 번호 부여)"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        return await baseline_module.add_step(
            stock_code=baseline_data.stock_code,
            decision_price=baseline_data.decision_price,
            quantity=baseline_data.quantity,
            low_price=baseline_data.low_price,
            high_price=baseline_data.high_price
        )
    except Exception as e:
        logger.error(f"step 추가 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"step 추가 실패: {str(e)}")

# ✅ 특정 종목의 특정 step 베이스라인 업데이트 - Updated with low_price, high_price
@router.put("/update_by_step", response_model=BaselineRead)
async def update_by_step(
    request: Request,
    baseline_data: BaselineUpdate
):
    """특정 종목과 단계의 수량 업데이트"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        updated_baseline = await baseline_module.update_by_step(
            stock_code=baseline_data.stock_code,
            step=baseline_data.step,
            new_price=baseline_data.decision_price,
            new_quantity=baseline_data.quantity,
            low_price=baseline_data.low_price,
            high_price=baseline_data.high_price
        )
        if not updated_baseline:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {baseline_data.stock_code}의 step {baseline_data.step} 베이스라인을 찾을 수 없습니다"
            )
        return updated_baseline
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"베이스라인 업데이트 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"업데이트 실패: {str(e)}")

# ✅ 특정 종목의 모든 베이스라인 조회
@router.get("/get_all_by_code/{stock_code}", response_model=List[BaselineRead])
async def get_all_by_code(
    request: Request,
    stock_code: str
):
    """특정 종목 코드로 모든 베이스라인 조회"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        baselines = await baseline_module.get_all_by_code(stock_code)
        return baselines
    except Exception as e:
        logger.error(f"베이스라인 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 특정 종목의 마지막 step 번호 조회
@router.get("/last_step/{stock_code}", response_model=LastStepResponse)
async def get_last_step(
    request: Request,
    stock_code: str
):
    """특정 종목 코드의 마지막(최대) step 반환"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        last_step = await baseline_module.get_last_step(stock_code)
        return LastStepResponse(stock_code=stock_code, last_step=last_step)
    except Exception as e:
        logger.error(f"마지막 step 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 특정 종목의 마지막 베이스라인 조회
@router.get("/last_data/{stock_code}", response_model=BaselineRead)
async def get_last_baseline(
    request: Request,
    stock_code: str
):
    """특정 종목 코드의 마지막 step에 해당하는 베이스라인 객체 반환"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        baseline = await baseline_module.get_last_baseline(stock_code)
        if not baseline:
            raise HTTPException(status_code=404, detail=f"종목 {stock_code}의 베이스라인을 찾을 수 없습니다")
        return baseline
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"마지막 베이스라인 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 특정 종목의 특정 step 베이스라인 조회
@router.get("/{stock_code}/step/{step}", response_model=Optional[BaselineRead])
async def get_by_step(
    request: Request,
    stock_code: str,
    step: int
):
    """종목 코드와 단계로 특정 베이스라인 조회"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        baseline = await baseline_module.get_by_step(stock_code, step)
        if not baseline:
            raise HTTPException(
                status_code=404, 
                detail=f"종목 {stock_code}의 step {step} 베이스라인을 찾을 수 없습니다"
            )
        return baseline
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"베이스라인 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")


# ✅ 특정 종목의 특정 step 베이스라인 삭제
@router.delete("/{stock_code}/step/{step}")
async def delete_by_step(
    request: Request,
    stock_code: str,
    step: int
):
    """특정 종목의 특정 step 베이스라인 삭제"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        deleted = await baseline_module.delete_by_step(stock_code, step)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {stock_code}의 step {step} 베이스라인을 찾을 수 없습니다"
            )
        return {
            "message": f"종목 {stock_code}의 step {step} 베이스라인이 삭제되었습니다"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"베이스라인 삭제 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"삭제 실패: {str(e)}")
      
# ✅ 특정 종목의 마지막 step 베이스라인 삭제
@router.delete("/delete_last/{stock_code}", response_model=SingleDeleteResponse)
async def delete_last_step(
    request: Request,
    stock_code: str
):
    """특정 종목의 마지막 step 베이스라인 삭제"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        deleted = await baseline_module.delete_last_step(stock_code)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {stock_code}의 베이스라인을 찾을 수 없습니다"
            )
        return SingleDeleteResponse(
            message=f"종목 {stock_code}의 마지막 step 베이스라인이 삭제되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"마지막 step 베이스라인 삭제 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"삭제 실패: {str(e)}") 
      
# ✅ 특정 종목의 모든 베이스라인 삭제
@router.delete("/delete_all/{stock_code}")
async def delete_by_code(
    request: Request,
    stock_code: str
):
    """특정 종목의 모든 베이스라인 삭제"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        deleted_count = await baseline_module.delete_by_code(stock_code)
        if deleted_count == 0:
            raise HTTPException(
                status_code=404,
                detail=f"종목 {stock_code}의 베이스라인을 찾을 수 없습니다"
            )
        return {
            "message": f"종목 {stock_code}의 베이스라인 {deleted_count}개가 삭제되었습니다",
            "deleted_count": deleted_count
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"베이스라인 삭제 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"삭제 실패: {str(e)}")

# 새로 추가

# ✅ 모든 베이스라인 조회
@router.get("/all", response_model=List[BaselineRead])
async def get_all_baseline(request: Request):
    """모든 베이스라인 조회"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        baselines = await baseline_module.get_all_baseline()
        return baselines
    except Exception as e:
        logger.error(f"전체 베이스라인 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 모든 베이스라인 정렬 조회 (종목코드, step 순)
@router.get("/all/ordered", response_model=List[BaselineRead])
async def get_all_baseline_ordered(request: Request):
    """모든 베이스라인을 종목 코드와 step 순으로 정렬하여 조회"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        baselines = await baseline_module.get_all_baseline_ordered_by_code()
        return baselines
    except Exception as e:
        logger.error(f"정렬된 베이스라인 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 등록된 모든 종목 코드 조회
@router.get("/stock-codes", response_model=List[str])
async def get_all_stock_codes(request: Request):
    """베이스라인에 등록된 모든 종목 코드 조회 (중복 제거)"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        stock_codes = await baseline_module.get_all_stock_codes()
        return stock_codes
    except Exception as e:
        logger.error(f"종목 코드 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 전체 베이스라인 개수 조회
@router.get("/count", response_model=dict)
async def count_total_baselines(request: Request):
    """전체 베이스라인 개수 조회"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        count = await baseline_module.count_total_baselines()
        return {"total_count": count}
    except Exception as e:
        logger.error(f"베이스라인 개수 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 베이스라인 요약 정보 조회
@router.get("/summary", response_model=dict)
async def get_baseline_summary(request: Request):
    """베이스라인 전체 요약 정보 조회"""
    baseline_module = request.app.baseline.baseline_module()
    try:
        summary = await baseline_module.get_baseline_summary()
        return summary
    except Exception as e:
        logger.error(f"베이스라인 요약 정보 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")

# ✅ 실시간 그룹에서 베이스라인 동기화 - Updated with low_price, high_price
@router.post("/sync-from-groups", response_model=dict)
async def sync_baseline_from_realtime_groups(request: Request):
    """실시간 그룹의 모든 주식 코드로 베이스라인 생성 (decision_price=0, quantity=0)"""
    baseline_module = request.app.baseline.baseline_module()
    realtime_group_module = request.app.realtime_group.realtime_group_module()
    
    try:
        # 모든 실시간 그룹 조회
        all_groups = await realtime_group_module.get_all_groups()
        logger.info(f"📊 총 {len(all_groups)}개의 실시간 그룹을 조회했습니다")
        
        # 모든 그룹에서 주식 코드 추출 (중복 제거)
        all_stock_codes = set()
        for group in all_groups:
            if group.stock_code:
                all_stock_codes.update(group.stock_code)
        
        logger.info(f"🎯 총 {len(all_stock_codes)}개의 고유 주식 코드를 추출했습니다")
        
        # 각 주식 코드에 대해 베이스라인 생성 시도
        created_count = 0
        skipped_count = 0
        error_count = 0
        
        for stock_code in all_stock_codes:
            try:
                existing_baselines = await baseline_module.get_all_by_code(stock_code)
                
                if existing_baselines:
                    skipped_count += 1
                    continue
                
                new_baseline = await baseline_module.create_new(
                    stock_code=stock_code,
                    decision_price=0,
                    quantity=0,
                    low_price=None,
                    high_price=None
                )
                
                if new_baseline:
                    created_count += 1
                else:
                    error_count += 1
                    
            except ValueError:
                skipped_count += 1
            except Exception as e:
                logger.error(f"종목 {stock_code} 처리 중 오류: {str(e)}")
                error_count += 1
        
        result = {
            "total_groups": len(all_groups),
            "total_stock_codes": len(all_stock_codes),
            "created": created_count,
            "skipped": skipped_count,
            "errors": error_count,
            "success_rate": (created_count / len(all_stock_codes) * 100) if all_stock_codes else 0,
            "message": f"베이스라인 동기화 완료: 생성 {created_count}개, 건너뜀 {skipped_count}개, 오류 {error_count}개"
        }
        
        return result
        
    except Exception as e:
        logger.error(f"베이스라인 동기화 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"동기화 실패: {str(e)}")

# ✅ 특정 그룹에서 베이스라인 동기화 - Updated with low_price, high_price
@router.post("/sync-from-group/{group}", response_model=dict)
async def sync_baseline_from_specific_group(request: Request, group: int):
    """특정 실시간 그룹의 주식 코드로 베이스라인 생성"""
    baseline_module = request.app.baseline.baseline_module()
    realtime_group_module = request.app.realtime_group.realtime_group_module()
    
    try:
        # 특정 그룹 조회
        target_group = await realtime_group_module.get_by_group(group)
        
        if not target_group:
            raise HTTPException(status_code=404, detail=f"그룹 {group}을 찾을 수 없습니다")
        
        if not target_group.stock_code:
            return {
                "group": group,
                "stock_codes": 0,
                "created": 0,
                "skipped": 0,
                "errors": 0,
                "success_rate": 0,
                "message": f"그룹 {group}에 주식 코드가 없습니다"
            }
        
        created_count = 0
        skipped_count = 0
        error_count = 0
        
        for stock_code in target_group.stock_code:
            try:
                new_baseline = await baseline_module.create_new(
                    stock_code=stock_code,
                    decision_price=0,
                    quantity=0,
                    low_price=None,
                    high_price=None
                )
                
                if new_baseline:
                    created_count += 1
                    
            except ValueError:
                skipped_count += 1
            except Exception as e:
                logger.error(f"종목 {stock_code} 처리 중 오류: {str(e)}")
                error_count += 1
        
        total_codes = len(target_group.stock_code)
        success_rate = (created_count / total_codes * 100) if total_codes > 0 else 0
        
        result = {
            "group": group,
            "stock_codes": total_codes,
            "created": created_count,
            "skipped": skipped_count,
            "errors": error_count,
            "success_rate": round(success_rate, 2),
            "message": f"그룹 {group} 베이스라인 동기화 완료: 생성 {created_count}개, 건너뜀 {skipped_count}개, 오류 {error_count}개"
        }
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"그룹 {group} 베이스라인 동기화 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"동기화 실패: {str(e)}")

# ✅ 벌크 베이스라인 생성 - Updated with low_price, high_price
@router.post("/bulk-create", response_model=dict)
async def bulk_create_baselines(request: Request, bulk_data: List[BaselineCreate]):
    """여러 베이스라인을 한번에 생성"""
    baseline_module = request.app.baseline.baseline_module()
    
    try:
        created_count = 0
        skipped_count = 0
        error_count = 0
        errors = []
        
        for baseline_data in bulk_data:
            try:
                new_baseline = await baseline_module.create_new(
                    stock_code=baseline_data.stock_code,
                    decision_price=baseline_data.decision_price,
                    quantity=baseline_data.quantity,
                    low_price=baseline_data.low_price,
                    high_price=baseline_data.high_price
                )
                
                if new_baseline:
                    created_count += 1
                else:
                    error_count += 1
                    errors.append(f"종목 {baseline_data.stock_code}: 생성 실패")
                    
            except ValueError as e:
                skipped_count += 1
                logger.debug(f"종목 {baseline_data.stock_code}: {str(e)}")
            except Exception as e:
                error_count += 1
                error_msg = f"종목 {baseline_data.stock_code}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        total_requested = len(bulk_data)
        success_rate = (created_count / total_requested * 100) if total_requested > 0 else 0
        
        result = {
            "total_requested": total_requested,
            "created": created_count,
            "skipped": skipped_count,
            "errors": error_count,
            "success_rate": round(success_rate, 2),
            "error_details": errors if errors else None,
            "message": f"벌크 생성 완료: 생성 {created_count}개, 건너뜀 {skipped_count}개, 오류 {error_count}개"
        }
        
        return result
        
    except Exception as e:
        logger.error(f"벌크 베이스라인 생성 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"벌크 생성 실패: {str(e)}")

# ✅ 종목별 베이스라인 통계 - Updated with low_price, high_price stats
@router.get("/stats/{stock_code}", response_model=dict)
async def get_stock_baseline_stats(request: Request, stock_code: str):
    """특정 종목의 베이스라인 통계 정보"""
    baseline_module = request.app.baseline.baseline_module()
    
    try:
        baselines = await baseline_module.get_all_by_code(stock_code)
        
        if not baselines:
            raise HTTPException(status_code=404, detail=f"종목 {stock_code}의 베이스라인을 찾을 수 없습니다")
        
        total_quantity = sum(b.quantity for b in baselines)
        total_value = sum(b.decision_price * b.quantity for b in baselines)
        avg_price = sum(b.decision_price for b in baselines) / len(baselines)
        
        # 가격 범위 통계 계산
        baselines_with_price_range = [b for b in baselines if b.low_price is not None and b.high_price is not None]
        avg_low_price = None
        avg_high_price = None
        
        if baselines_with_price_range:
            avg_low_price = sum(b.low_price for b in baselines_with_price_range) / len(baselines_with_price_range)
            avg_high_price = sum(b.high_price for b in baselines_with_price_range) / len(baselines_with_price_range)
        
        stats = {
            "stock_code": stock_code,
            "total_steps": len(baselines),
            "total_quantity": total_quantity,
            "total_value": total_value,
            "average_price": round(avg_price, 2),
            "min_price": min(b.decision_price for b in baselines),
            "max_price": max(b.decision_price for b in baselines),
            "average_low_price": round(avg_low_price, 2) if avg_low_price is not None else None,
            "average_high_price": round(avg_high_price, 2) if avg_high_price is not None else None,
            "price_range_data_count": len(baselines_with_price_range),
            "steps": [
                {
                    "step": b.step, 
                    "price": b.decision_price, 
                    "quantity": b.quantity,
                    "low_price": b.low_price,
                    "high_price": b.high_price
                } for b in baselines
            ]
        }
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"종목 {stock_code} 통계 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"통계 조회 실패: {str(e)}")

# ✅ 전체 베이스라인 삭제 (주의: 위험한 작업)
@router.delete("/delete-all", response_model=dict)
async def delete_all_baselines(request: Request, confirm: bool = False):
    """모든 베이스라인 삭제 (confirm=true 필요)"""
    if not confirm:
        raise HTTPException(
            status_code=400, 
            detail="모든 베이스라인을 삭제하려면 confirm=true 파라미터가 필요합니다"
        )
    
    baseline_module = request.app.baseline.baseline_module()
    
    try:
        # 모든 종목 코드 조회
        stock_codes = await baseline_module.get_all_stock_codes()
        total_deleted = 0
        
        for stock_code in stock_codes:
            deleted_count = await baseline_module.delete_by_code(stock_code)
            total_deleted += deleted_count
        
        return {
            "message": f"모든 베이스라인이 삭제되었습니다",
            "deleted_stocks": len(stock_codes),
            "total_deleted_baselines": total_deleted
        }
        
    except Exception as e:
        logger.error(f"전체 베이스라인 삭제 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"삭제 실패: {str(e)}")

# ✅ 새로 추가된 엔드포인트들

# 가격 범위 분석 엔드포인트
@router.get("/price-range-analysis/{stock_code}", response_model=dict)
async def get_price_range_analysis(request: Request, stock_code: str):
    """특정 종목의 가격 범위 분석"""
    baseline_module = request.app.baseline.baseline_module()
    
    try:
        baselines = await baseline_module.get_all_by_code(stock_code)
        
        if not baselines:
            raise HTTPException(status_code=404, detail=f"종목 {stock_code}의 베이스라인을 찾을 수 없습니다")
        
        # 가격 범위가 있는 베이스라인만 필터링
        price_range_baselines = [
            b for b in baselines 
            if b.low_price is not None and b.high_price is not None
        ]
        
        if not price_range_baselines:
            return {
                "stock_code": stock_code,
                "total_baselines": len(baselines),
                "price_range_spread": None,
                "price_accuracy_ratio": None,
                "risk_assessment": "NO_DATA",
                "recommendation": "가격 범위 데이터가 없어 분석할 수 없습니다."
            }
        
        # 가격 범위 분석
        spreads = [b.high_price - b.low_price for b in price_range_baselines]
        avg_spread = sum(spreads) / len(spreads)
        
        # 가격 정확도 비율 계산
        accuracy_ratios = []
        for b in price_range_baselines:
            mid_price = (b.high_price + b.low_price) / 2
            accuracy_ratio = b.decision_price / mid_price
            accuracy_ratios.append(accuracy_ratio)
        
        avg_accuracy = sum(accuracy_ratios) / len(accuracy_ratios)
        
        # 리스크 평가
        if avg_spread < 5000:  # 5천원 미만
            risk_assessment = "LOW_RISK"
            recommendation = "가격 변동성이 낮아 안정적인 투자가 가능합니다."
        elif avg_spread < 15000:  # 1만5천원 미만
            risk_assessment = "MEDIUM_RISK"
            recommendation = "적정한 가격 변동성으로 분할 매수를 권장합니다."
        else:
            risk_assessment = "HIGH_RISK"
            recommendation = "높은 가격 변동성으로 신중한 접근이 필요합니다."
        
        return {
            "stock_code": stock_code,
            "total_baselines": len(baselines),
            "price_range_data_count": len(price_range_baselines),
            "price_range_spread": round(avg_spread, 2),
            "price_accuracy_ratio": round(avg_accuracy, 4),
            "risk_assessment": risk_assessment,
            "recommendation": recommendation,
            "analysis_details": {
                "min_spread": min(spreads),
                "max_spread": max(spreads),
                "avg_spread": round(avg_spread, 2),
                "spread_std": round((sum((s - avg_spread) ** 2 for s in spreads) / len(spreads)) ** 0.5, 2) if len(spreads) > 1 else 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"가격 범위 분석 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"분석 실패: {str(e)}")

# 가격 범위 검증 베이스라인 생성
@router.post("/create-with-validation", response_model=BaselineRead, status_code=status.HTTP_201_CREATED)
async def create_baseline_with_validation(
    request: Request,
    baseline_data: BaselineCreate,
    validate_price_range: bool = True,
    max_deviation: float = 0.1  # 10% 허용 편차
):
    """가격 범위 검증과 함께 베이스라인 생성"""
    baseline_module = request.app.baseline.baseline_module()
    
    try:
        # 가격 범위 검증
        if validate_price_range and baseline_data.low_price and baseline_data.high_price:
            price_range = baseline_data.high_price - baseline_data.low_price
            mid_price = (baseline_data.high_price + baseline_data.low_price) / 2
            
            # 결정 가격이 범위 내에 있는지 확인
            if not (baseline_data.low_price <= baseline_data.decision_price <= baseline_data.high_price):
                raise HTTPException(
                    status_code=400,
                    detail=f"결정 가격 {baseline_data.decision_price}이 예상 범위 [{baseline_data.low_price}, {baseline_data.high_price}] 밖에 있습니다."
                )
            
            # 가격 편차 검증
            deviation = abs(baseline_data.decision_price - mid_price) / mid_price
            if deviation > max_deviation:
                raise HTTPException(
                    status_code=400,
                    detail=f"결정 가격의 편차({deviation:.2%})가 허용 범위({max_deviation:.2%})를 초과합니다."
                )
        
        # 베이스라인 생성
        return await baseline_module.create_new(
            stock_code=baseline_data.stock_code,
            decision_price=baseline_data.decision_price,
            quantity=baseline_data.quantity,
            low_price=baseline_data.low_price,
            high_price=baseline_data.high_price
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"검증된 베이스라인 생성 실패: {str(e)}")
        raise HTTPException(status_code=400, detail=f"생성 실패: {str(e)}")

# 가격 범위별 베이스라인 검색
@router.post("/search-by-price-range", response_model=List[BaselineRead])
async def search_baselines_by_price_range(
    request: Request,
    min_low_price: Optional[int] = None,
    max_low_price: Optional[int] = None,
    min_high_price: Optional[int] = None,
    max_high_price: Optional[int] = None,
    min_decision_price: Optional[int] = None,
    max_decision_price: Optional[int] = None
):
    """가격 범위를 기준으로 베이스라인 검색"""
    baseline_module = request.app.baseline.baseline_module()
    
    try:
        # 모든 베이스라인 조회 후 필터링
        all_baselines = await baseline_module.get_all_baseline()
        
        filtered_baselines = []
        for baseline in all_baselines:
            # 조건 확인
            if min_low_price and (baseline.low_price is None or baseline.low_price < min_low_price):
                continue
            if max_low_price and (baseline.low_price is None or baseline.low_price > max_low_price):
                continue
            if min_high_price and (baseline.high_price is None or baseline.high_price < min_high_price):
                continue
            if max_high_price and (baseline.high_price is None or baseline.high_price > max_high_price):
                continue
            if min_decision_price and baseline.decision_price < min_decision_price:
                continue
            if max_decision_price and baseline.decision_price > max_decision_price:
                continue
            
            filtered_baselines.append(baseline)
        
        return filtered_baselines
        
    except Exception as e:
        logger.error(f"가격 범위 검색 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"검색 실패: {str(e)}")

# 전체 가격 범위 통계
@router.get("/price-range-stats", response_model=dict)
async def get_overall_price_range_stats(request: Request):
    """전체 베이스라인의 가격 범위 통계"""
    baseline_module = request.app.baseline.baseline_module()
    
    try:
        all_baselines = await baseline_module.get_all_baseline()
        
        if not all_baselines:
            return {
                "total_baselines": 0,
                "price_range_data_count": 0,
                "message": "베이스라인 데이터가 없습니다."
            }
        
        # 가격 범위가 있는 데이터만 필터링
        price_range_baselines = [
            b for b in all_baselines 
            if b.low_price is not None and b.high_price is not None
        ]
        
        if not price_range_baselines:
            return {
                "total_baselines": len(all_baselines),
                "price_range_data_count": 0,
                "message": "가격 범위 데이터가 없습니다."
            }
        
        # 통계 계산
        spreads = [b.high_price - b.low_price for b in price_range_baselines]
        decision_prices = [b.decision_price for b in price_range_baselines]
        low_prices = [b.low_price for b in price_range_baselines]
        high_prices = [b.high_price for b in price_range_baselines]
        
        # 종목별 가격 범위 통계
        stock_stats = {}
        for baseline in price_range_baselines:
            stock_code = baseline.stock_code
            if stock_code not in stock_stats:
                stock_stats[stock_code] = {
                    "count": 0,
                    "spreads": [],
                    "avg_spread": 0
                }
            
            spread = baseline.high_price - baseline.low_price
            stock_stats[stock_code]["count"] += 1
            stock_stats[stock_code]["spreads"].append(spread)
        
        # 종목별 평균 계산
        for stock_code, stats in stock_stats.items():
            stats["avg_spread"] = sum(stats["spreads"]) / len(stats["spreads"])
        
        return {
            "total_baselines": len(all_baselines),
            "price_range_data_count": len(price_range_baselines),
            "coverage_percentage": round((len(price_range_baselines) / len(all_baselines)) * 100, 2),
            "overall_stats": {
                "avg_spread": round(sum(spreads) / len(spreads), 2),
                "min_spread": min(spreads),
                "max_spread": max(spreads),
                "avg_decision_price": round(sum(decision_prices) / len(decision_prices), 2),
                "min_decision_price": min(decision_prices),
                "max_decision_price": max(decision_prices),
                "avg_low_price": round(sum(low_prices) / len(low_prices), 2),
                "avg_high_price": round(sum(high_prices) / len(high_prices), 2)
            },
            "stock_count_with_price_range": len(stock_stats),
            "top_volatile_stocks": sorted(
                [(stock, stats["avg_spread"]) for stock, stats in stock_stats.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]  # 상위 10개 변동성 높은 종목
        }
        
    except Exception as e:
        logger.error(f"전체 가격 범위 통계 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"통계 조회 실패: {str(e)}")

# 베이스라인 일괄 업데이트
@router.put("/bulk-update", response_model=dict)
async def bulk_update_baselines(request: Request, updates: List[BaselineUpdate]):
    """여러 베이스라인을 한번에 업데이트"""
    baseline_module = request.app.baseline.baseline_module()
    
    try:
        updated_count = 0
        not_found_count = 0
        error_count = 0
        errors = []
        
        for update_data in updates:
            try:
                updated_baseline = await baseline_module.update_by_step(
                    stock_code=update_data.stock_code,
                    step=update_data.step,
                    new_price=update_data.decision_price,
                    new_quantity=update_data.quantity,
                    low_price=update_data.low_price,
                    high_price=update_data.high_price
                )
                
                if updated_baseline:
                    updated_count += 1
                else:
                    not_found_count += 1
                    
            except Exception as e:
                error_count += 1
                error_msg = f"종목 {update_data.stock_code} step {update_data.step}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        total_requested = len(updates)
        success_rate = (updated_count / total_requested * 100) if total_requested > 0 else 0
        
        result = {
            "total_requested": total_requested,
            "updated": updated_count,
            "not_found": not_found_count,
            "errors": error_count,
            "success_rate": round(success_rate, 2),
            "error_details": errors if errors else None,
            "message": f"일괄 업데이트 완료: 업데이트 {updated_count}개, 미발견 {not_found_count}개, 오류 {error_count}개"
        }
        
        return result
        
    except Exception as e:
        logger.error(f"일괄 업데이트 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"일괄 업데이트 실패: {str(e)}")