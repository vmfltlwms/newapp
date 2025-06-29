import logging
from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/order/buy")
async def order_stock_buy(
    request: Request,
    dmst_stex_tp: str = Query("KRX", description="국내거래소구분 - KRX:한국거래소, NXT:넥스트트레이드, SOR:최선주문집행"),
    stk_cd: str = Query(..., description="종목코드", example="005930"),
    ord_qty: str = Query(..., description="주문수량", example="10"),
    ord_uv: str = Query("", description="주문단가 (시장가 주문 시 비워둠)", example="75000"),
    trde_tp: str = Query("3", description="매매구분 - 0:보통, 3:시장가, 5:조건부지정가, 6:최유리지정가, 7:최우선지정가"),
    cond_uv: str = Query("", description="조건단가 (조건부 주문 시 사용)"),
    cont_yn: str = Query("N", description="연속조회여부"),
    next_key: str = Query("", description="연속조회키")
):
    """주식 매수주문 (kt10000)"""
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        # if not kiwoom_client.connected:
        #     raise HTTPException(status_code=503, detail="키움 API에 연결되어 있지 않습니다.")
        
        response = await kiwoom_client.order_stock_buy(
            dmst_stex_tp=dmst_stex_tp,
            stk_cd=stk_cd,
            ord_qty=ord_qty,
            ord_uv=ord_uv,
            trde_tp=trde_tp,
            cond_uv=cond_uv,
            cont_yn=cont_yn,
            next_key=next_key
        )

        return response
    
    except Exception as e:
        logger.error(f"주식 매수주문 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order/sell")
async def order_stock_sell(
    request: Request,
    dmst_stex_tp: str = Query("KRX", description="국내거래소구분 - KRX:한국거래소, NXT:넥스트트레이드, SOR:최선주문집행"),
    stk_cd: str = Query(..., description="종목코드", example="005930"),
    ord_qty: str = Query(..., description="주문수량", example="5"),
    ord_uv: str = Query("", description="주문단가 (시장가 주문 시 비워둠)", example="76000"),
    trde_tp: str = Query("3", description="매매구분 - 0:보통, 3:시장가, 5:조건부지정가, 6:최유리지정가, 7:최우선지정가"),
    cond_uv: str = Query("", description="조건단가 (조건부 주문 시 사용)"),
    cont_yn: str = Query("N", description="연속조회여부"),
    next_key: str = Query("", description="연속조회키")
):
    """주식 매도주문 (kt10001)"""
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        # if not kiwoom_client.connected:
        #     raise HTTPException(status_code=503, detail="키움 API에 연결되어 있지 않습니다.")
        
        response = await kiwoom_client.order_stock_sell(
            dmst_stex_tp=dmst_stex_tp,
            stk_cd=stk_cd,
            ord_qty=ord_qty,
            ord_uv=ord_uv,
            trde_tp=trde_tp,
            cond_uv=cond_uv,
            cont_yn=cont_yn,
            next_key=next_key
        )

        return response
    
    except Exception as e:
        logger.error(f"주식 매도주문 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order/modify")
async def order_stock_modify(
    request: Request,
    dmst_stex_tp: str = Query("KRX", description="국내거래소구분 - KRX:한국거래소, NXT:넥스트트레이드, SOR:최선주문집행"),
    orig_ord_no: str = Query(..., description="원주문번호", example="20240528001"),
    stk_cd: str = Query(..., description="종목코드", example="005930"),
    mdfy_qty: str = Query(..., description="정정수량", example="8"),
    mdfy_uv: str = Query(..., description="정정단가", example="74000"),
    mdfy_cond_uv: str = Query("", description="정정조건단가"),
    cont_yn: str = Query("N", description="연속조회여부"),
    next_key: str = Query("", description="연속조회키")
):
    """주식 정정주문 (kt10002)"""
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        # if not kiwoom_client.connected:
        #     raise HTTPException(status_code=503, detail="키움 API에 연결되어 있지 않습니다.")
        
        response = await kiwoom_client.order_stock_modify(
            dmst_stex_tp=dmst_stex_tp,
            orig_ord_no=orig_ord_no,
            stk_cd=stk_cd,
            mdfy_qty=mdfy_qty,
            mdfy_uv=mdfy_uv,
            mdfy_cond_uv=mdfy_cond_uv,
            cont_yn=cont_yn,
            next_key=next_key
        )

        return response
    
    except Exception as e:
        logger.error(f"주식 정정주문 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order/cancel")
async def order_stock_cancel(
    request: Request,
    dmst_stex_tp: str = Query("KRX", description="국내거래소구분 - KRX:한국거래소, NXT:넥스트트레이드, SOR:최선주문집행"),
    orig_ord_no: str = Query(..., description="원주문번호", example="20240528001"),
    stk_cd: str = Query(..., description="종목코드", example="005930"),
    cncl_qty: str = Query("0", description="취소수량 ('0' 입력시 잔량 전부 취소)", example="0"),
    cont_yn: str = Query("N", description="연속조회여부"),
    next_key: str = Query("", description="연속조회키")
):
    """주식 취소주문 (kt10003)"""
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        # if not kiwoom_client.connected:
        #     raise HTTPException(status_code=503, detail="키움 API에 연결되어 있지 않습니다.")
        
        response = await kiwoom_client.order_stock_cancel(
            dmst_stex_tp=dmst_stex_tp,
            orig_ord_no=orig_ord_no,
            stk_cd=stk_cd,
            cncl_qty=cncl_qty,
            cont_yn=cont_yn,
            next_key=next_key
        )

        return response
    
    except Exception as e:
        logger.error(f"주식 취소주문 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))