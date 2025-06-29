import logging
from fastapi import APIRouter, Request , HTTPException, Query

router = APIRouter()
logger = logging.getLogger(__name__)

"""주식 틱차트 조회 (ka10079)"""
@router.get("/chart/tick/{code}")
async def get_tick_chart(
    request: Request,
    code: str, 
    tick_scope: str = Query("1", description="틱범위 - 1:1틱, 3:3틱, 5:5틱, 10:10틱, 30:30틱"),
    price_type: str = Query("1", description="종가시세구분 - 1:최근가, 2:매수가, 3:매도가"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키"),
):
    kiwoom_client= request.app.kiwoom.kiwoom_module()
    try:
        # if not kiwoom_client.connected:
        #     raise HTTPException(status_code=503, detail="키움 API에 연결되어 있지 않습니다.")
        
        response = await kiwoom_client.get_tick_chart(
            code=code,
            tick_scope=tick_scope,
            price_type=price_type,
            cont_yn=cont_yn,
            next_key=next_key
        )

        return response
    
    except Exception as e:
        logger.error(f"틱차트 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
      

"""주식 분봉차트 조회 (ka10080)"""
@router.get("/chart/minute/{code}")
async def get_minute_chart(
    request: Request,
    code: str,
    tic_scope: str = Query("1", description="분단위 - 1:1분, 3:3분, 5:5분, 10:10분, 15:15분, 30:30분, 60:60분"),
    price_type: str = Query("1", description="종가시세구분 - 1:최근가, 2:매수가, 3:매도가"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키"),
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    try:
        response = await kiwoom_client.get_minute_chart(
            code=code,
            tic_scope=tic_scope,
            price_type=price_type,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    except Exception as e:
        logger.error(f"분봉차트 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


"""주식 일봉차트 조회 (ka10081)"""
@router.get("/chart/daily/{code}")
async def get_daily_chart(
    request: Request,
    code: str,
    base_dt: str = Query("", description="기준일자 (YYYYMMDD 형식, 빈값시 오늘날짜)"),
    price_type: str = Query("1", description="종가시세구분 - 1:최근가, 2:매수가, 3:매도가"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키"),
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    try:
        response = await kiwoom_client.get_daily_chart(
            code=code,
            base_dt=base_dt,
            price_type=price_type,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    except Exception as e:
        logger.error(f"일봉차트 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


"""주식 주봉차트 조회 (ka10082)"""
@router.get("/chart/weekly/{code}")
async def get_weekly_chart(
    request: Request,
    code: str,
    base_dt: str = Query("", description="기준일자 (YYYYMMDD 형식, 빈값시 오늘날짜)"),
    price_type: str = Query("1", description="종가시세구분 - 1:최근가, 2:매수가, 3:매도가"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키"),
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    try:
        response = await kiwoom_client.get_weekly_chart(
            code=code,
            base_dt=base_dt,
            price_type=price_type,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    except Exception as e:
        logger.error(f"주봉차트 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


"""주식 월봉차트 조회 (ka10083)"""
@router.get("/chart/monthly/{code}")
async def get_monthly_chart(
    request: Request,
    code: str,
    base_dt: str = Query("", description="기준일자 (YYYYMMDD 형식, 빈값시 오늘날짜)"),
    price_type: str = Query("1", description="종가시세구분 - 1:최근가, 2:매수가, 3:매도가"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키"),
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    try:
        response = await kiwoom_client.get_monthly_chart(
            code=code,
            base_dt=base_dt,
            price_type=price_type,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    except Exception as e:
        logger.error(f"월봉차트 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


"""주식 년봉차트 조회 (ka10094)"""
@router.get("/chart/yearly/{code}")
async def get_yearly_chart(
    request: Request,
    code: str,
    base_dt: str = Query("", description="기준일자 (YYYYMMDD 형식, 빈값시 오늘날짜)"),
    price_type: str = Query("1", description="종가시세구분 - 1:최근가, 2:매수가, 3:매도가"),
    cont_yn: str = Query("N", description="연속조회여부 - Y:연속조회, N:일반조회"),
    next_key: str = Query("", description="연속조회키"),
):
    kiwoom_client = request.app.kiwoom.kiwoom_module()
    try:
        response = await kiwoom_client.get_yearly_chart(
            code=code,
            base_dt=base_dt,
            price_type=price_type,
            cont_yn=cont_yn,
            next_key=next_key
        )
        return response
    except Exception as e:
        logger.error(f"년봉차트 조회 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))