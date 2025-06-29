import logging
from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)



"""주식 기본정보 조회요청 (ka10001)"""
@router.get("/stock/info")
async def get_stock_info(
    request: Request,
    stk_cd: str = Query(..., description="종목코드")
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        response = await kiwoom_client.get_stock_info(
            code=stk_cd

        )
        return response
    except Exception as e:
        logger.error(f"주식 기본정보 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

"""예수금상세현황요청 (kt00001)"""
@router.get("/account/deposit")
async def get_deposit_detail(
    request: Request,
    qry_tp: str = Query("2", description="조회구분 (3:추정조회, 2:일반조회)"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키")
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        response = await kiwoom_client.get_deposit_detail(
            query_type=qry_tp,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    except Exception as e:
        logger.error(f"예수금상세현황 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

"""계좌별주문체결내역상세요청 (kt00007)"""
@router.get("/account/order-detail")
async def get_order_detail(
    request: Request,
    ord_dt: str = Query(..., description="주문일자 (YYYYMMDD)", example="20240528"),
    qry_tp: str = Query("1", description="조회구분 - 1:주문순, 2:역순, 3:미체결, 4:체결내역만"),
    stk_bond_tp: str = Query("1", description="주식채권구분 - 0:전체, 1:주식, 2:채권"),
    sell_tp: str = Query("0", description="매도수구분 - 0:전체, 1:매도, 2:매수"),
    stk_cd: str = Query("", description="종목코드 (공백허용, 공백일때 전체종목)"),
    fr_ord_no: str = Query("", description="시작주문번호 (공백허용, 공백일때 전체주문)"),
    dmst_stex_tp: str = Query("KRX", description="국내거래소구분 - %:(전체), KRX:한국거래소, NXT:넥스트트레이드, SOR:최선주문집행"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키")
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        response = await kiwoom_client.get_order_detail(
            order_date=ord_dt,
            query_type=qry_tp,
            stock_bond_type=stk_bond_tp,
            sell_buy_type=sell_tp,
            stock_code=stk_cd,
            from_order_no=fr_ord_no,
            market_type=dmst_stex_tp,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    
    except Exception as e:
        logger.error(f"주문체결내역 상세 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

"""당일매매일지요청 (ka10170)"""
@router.get("/account/daily-trading-log")
async def get_daily_trading_log(
    request: Request,
    base_dt: str = Query("", description="기준일자 (YYYYMMDD) - 공백일 경우 당일"),
    ottks_tp: str = Query("1", description="단주구분 - 1:당일매수에 대한 당일매도, 2:당일매도 전체"),
    ch_crd_tp: str = Query("0", description="0:전체, 1:현금매매만, 2:신용매매만"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키")
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        response = await kiwoom_client.get_daily_trading_log(
            base_date=base_dt,
            ottks_tp=ottks_tp,
            ch_crd_tp=ch_crd_tp,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    
    except Exception as e:
        logger.error(f"당일매매일지 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

"""미체결요청 (ka10075)"""
@router.get("/account/outstanding-orders")
async def get_outstanding_orders(
    request: Request,
    all_stk_tp: str = Query("0", description="전체종목구분 - 0:전체, 1:종목"),
    trde_tp: str = Query("0", description="매매구분 - 0:전체, 1:매도, 2:매수"),
    stk_cd: str = Query("", description="종목코드 (all_stk_tp가 1일 경우 필수)"),
    stex_tp: str = Query("0", description="거래소구분 - 0:통합, 1:KRX, 2:NXT"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키")
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        response = await kiwoom_client.get_outstanding_orders(
            all_stk_tp=all_stk_tp,
            trde_tp=trde_tp,
            stk_cd=stk_cd,
            stex_tp=stex_tp,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    
    except Exception as e:
        logger.error(f"미체결 주문 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

"""체결요청 (ka10076)"""
@router.get("/account/executed-orders")
async def get_executed_orders(
    request: Request,
    stk_cd: str = Query("", description="종목코드"),
    qry_tp: str = Query("0", description="조회구분 - 0:전체, 1:종목"),
    sell_tp: str = Query("0", description="매도수구분 - 0:전체, 1:매도, 2:매수"),
    ord_no: str = Query("", description="주문번호 (입력한 주문번호보다 과거에 체결된 내역 조회)"),
    stex_tp: str = Query("0", description="거래소구분 - 0:통합, 1:KRX, 2:NXT"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키")
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        response = await kiwoom_client.get_executed_orders(
            stk_cd=stk_cd,
            qry_tp=qry_tp,
            sell_tp=sell_tp,
            ord_no=ord_no,
            stex_tp=stex_tp,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    
    except Exception as e:
        logger.error(f"체결 주문 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

"""일자별종목별실현손익요청_일자 (ka10072)"""
@router.get("/account/daily-item-profit")
async def get_daily_item_realized_profit(
    request: Request,
    stk_cd: str = Query(..., description="종목코드", example="005930"),
    strt_dt: str = Query(..., description="시작일자 (YYYYMMDD)", example="20240501"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키")
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        response = await kiwoom_client.get_daily_item_realized_profit(
            stk_cd=stk_cd,
            strt_dt=strt_dt,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    
    except Exception as e:
        logger.error(f"일자별종목별실현손익 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

"""일자별실현손익요청 (ka10074)"""
@router.get("/account/daily-profit")
async def get_daily_realized_profit(
    request: Request,
    strt_dt: str = Query(..., description="시작일자 (YYYYMMDD)", example="20240501"),
    end_dt: str = Query(..., description="종료일자 (YYYYMMDD)", example="20240531"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키")
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        response = await kiwoom_client.get_daily_realized_profit(
            strt_dt=strt_dt,
            end_dt=end_dt,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    
    except Exception as e:
        logger.error(f"일자별 실현손익 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

"""계좌수익률요청 (ka10085)"""
@router.get("/account/return")
async def get_account_return(
    request: Request,
    stex_tp: str = Query("0", description="거래소구분 - 0:통합, 1:KRX, 2:NXT"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키")
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        response = await kiwoom_client.get_account_return(
            stex_tp=stex_tp,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    
    except Exception as e:
        logger.error(f"계좌수익률 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
      
"""계좌 정보 조회요청"""
@router.get("/account/info")
async def get_account_info(
    request: Request,
    qry_tp: str = Query("1", description="조회구분 - 1:합산, 2:개별"),
    dmst_stex_tp: str = Query("K", description="국내거래소구분 - KRX:한국거래소, NXT:넥스트"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키")
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    
    try:
        response = await kiwoom_client.get_account_info(
            query_type=qry_tp,
            exchange_type=dmst_stex_tp,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    except Exception as e:
        logger.error(f"계좌 정보 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))