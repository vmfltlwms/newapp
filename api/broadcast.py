# api/broadcast.py
from fastapi import APIRouter, WebSocket, Request
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/")
async def websocket_endpoint(websocket: WebSocket, request: Request):
    """WebSocket 엔드포인트 - 통합된 브로드캐스트 매니저 사용"""
    # main.py에서 주입된 브로드캐스트 매니저 사용
    broadcast_module = request.app.broadcast.broadcast_module()
    # 통합된 핸들러로 연결 처리
    await broadcast_module.handle_websocket_connection(websocket)


@router.get("/status")
async def websocket_status(request: Request):
    """WebSocket 연결 상태 확인"""
    broadcast_module = request.app.broadcast.broadcast_module()
    return {
        "active_connections": broadcast_module.get_connection_count(),
        "status": "running"
    }