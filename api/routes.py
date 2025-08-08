from fastapi import APIRouter
from api import chart, realtime,socket_broadcast,order,account

# API 라우터 생성
api_router = APIRouter()

# 각 엔드포인트 라우터 등록
api_router.include_router(socket_broadcast.router, prefix="/ws", tags=["ws"])
api_router.include_router(chart.router, prefix="/chart", tags=["chart"])
api_router.include_router(realtime.router, prefix="/realtime", tags=["realtime"])
api_router.include_router(order.router, prefix="/order", tags=["order"])
api_router.include_router(account.router, prefix="/account", tags=["account"])

