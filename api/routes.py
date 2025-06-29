from fastapi import APIRouter
from api import chart, realtime,realtime_group,socket_broadcast,order,account,step_manager

# API 라우터 생성
api_router = APIRouter()

# 각 엔드포인트 라우터 등록
api_router.include_router(socket_broadcast.router, prefix="/ws", tags=["ws"])
api_router.include_router(chart.router, prefix="/chart", tags=["chart"])
api_router.include_router(realtime.router, prefix="/realtime", tags=["realtime"])
# api_router.include_router(baseline.router, prefix="/baseline", tags=["baseline"])
api_router.include_router(order.router, prefix="/order", tags=["order"])
api_router.include_router(account.router, prefix="/account", tags=["account"])
api_router.include_router(realtime_group.router, prefix="/realtime_group", tags=["realtime_group"])
api_router.include_router(step_manager.router, prefix="/step_manager", tags=["step_manager"])

