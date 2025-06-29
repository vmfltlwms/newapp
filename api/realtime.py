from schemas.realtime_request_model  import RealtimePriceRequest, RealtimePriceUnsubscribeRequest
import logging
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Query, Request, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)

@inject
@router.post("/price/subscribe",
            summary="실시간 구독 등록",
            description="실시간 구독 등록",
            responses={
                200: {"description": "구독 성공"},
                400: {"description": "잘못된 요청"},
                503: {"description": "서비스 이용 불가"}
            })
async def subscribe_realtime_price(
    request: Request,
    model : RealtimePriceRequest):
    realtime_module= request.app.realtime.realtime_module()

    try:
        # 연결 상태 확인
        if not realtime_module.connected:
            raise HTTPException(status_code=503, detail="키움 API에 연결되어 있지 않습니다.")
        
        # 입력값 검증
        if not model.items:
            raise HTTPException(status_code=400, detail="종목 코드가 비어있습니다.")
        
        if not model.data_types:
            raise HTTPException(status_code=400, detail="종목 타입이 비어있습니다.")
        
        # 구독 요청
        result = await realtime_module.subscribe_realtime_price(
            group_no=model.group_no,
            items=model.items,
            data_types=model.data_types,
            refresh=model.refresh
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        
        logger.info(f"구독 성공: 그룹={model.group_no}, 종목={model.items}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Subscribe error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/price/unsubscribe",
            summary="실시간 구독 등록해제",
            description="실시간 구독 등록해제")
async def unsubscribe_realtime_price(
    request: Request,
    model: RealtimePriceUnsubscribeRequest
    ):
    realtime_module= request.app.realtime.realtime_module()
    """
    실시간 시세 정보 구독 해제 API
    
    - **group_no**: 그룹 번호
    - **items**: 종목 코드 리스트 (예: ["005930", "000660"]). None이면 그룹 전체 해제
    - **data_types**: 데이터 타입 리스트 (예: ["0D"]). None이면 지정된 종목의 모든 타입 해제
    """
    try:
        if not realtime_module.connected:
            raise HTTPException(status_code=503, detail="키움 API에 연결되어 있지 않습니다.")
        
        result = await realtime_module.unsubscribe_realtime_price(
            group_no = model.group_no
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        

        logger.info(f"구독 해제 성공: 그룹={model.group_no}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unsubscribe error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/condition/list")
async def get_condition_list(
    request: Request
):
    """조건검색 목록 조회 (ka10171)"""
    realtime_module = request.app.realtime.realtime_module()
    
    try:
        response = await realtime_module.get_condition_list()
        return response
    
    except Exception as e:
        logger.error(f"조건검색 목록 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/condition/search")
async def request_condition_search(
    request: Request,
    seq: str = Query(..., description="조건검색식 일련번호", example="1"),
    search_type: str = Query("0", description="조회구분 - 0:조건검색, 1:신규편입, 2:신규이탈"),
    stex_tp	: str = Query("K", description="거래소구분 - 0:전체, 1:코스피, 2:코스닥"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키")
):
    """조건검색 요청 일반 (ka10172)"""
    realtime_module = request.app.realtime.realtime_module()
    
    try:
        response = await realtime_module.request_condition_search(
            seq=seq,
            search_type=search_type,
            stex_tp	=stex_tp	,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    
    except Exception as e:
        logger.error(f"조건검색 요청 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/condition/realtime")
async def request_realtime_condition(
    request: Request,
    seq: str = Query(..., description="조건검색식 일련번호", example="1"),
    search_type: str = Query("0", description="조회구분 - 0:조건검색, 1:신규편입, 2:신규이탈"),
    stex_tp: str = Query("0", description="시장구분 - 0:전체, 1:코스피, 2:코스닥")
):
    """조건검색 요청 실시간 (ka10173)"""
    realtime_module = request.app.realtime.realtime_module()
    
    try:
        response = await realtime_module.request_realtime_condition(
            seq=seq,
            search_type=search_type,
            stex_tp=stex_tp
        )
        return response
    
    except Exception as e:
        logger.error(f"실시간 조건검색 요청 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/condition/cancel")
async def cancel_realtime_condition(
    request: Request,
    seq: str = Query(..., description="조건검색식 일련번호", example="1")
):
    """조건검색 실시간 해제 (ka10174)"""
    realtime_module = request.app.realtime.realtime_module()
    
    try:
        response = await realtime_module.cancel_realtime_condition(seq=seq)
        return response
    
    except Exception as e:
        logger.error(f"실시간 조건검색 해제 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))