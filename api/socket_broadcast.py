# api/websocket.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any
import json
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_count = 0

    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_count += 1
        connection_id = f"conn_{self.connection_count}"
        logger.info(f"WebSocket 클라이언트 연결: {connection_id} (총 {len(self.active_connections)}개)")
        return connection_id

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket 클라이언트 연결 해제 (총 {len(self.active_connections)}개)")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """특정 클라이언트에게 메시지 전송"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"개별 메시지 전송 실패: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: Dict[Any, Any]):
        """모든 연결된 클라이언트에게 브로드캐스트"""
        if not self.active_connections:
            return
            
        message_str = json.dumps(message)
        disconnected_connections = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.error(f"브로드캐스트 전송 실패: {e}")
                disconnected_connections.append(connection)
        
        # 실패한 연결들 제거
        for connection in disconnected_connections:
            self.disconnect(connection)

    def get_connection_count(self) -> int:
        return len(self.active_connections)

# 전역 연결 매니저 인스턴스
manager = ConnectionManager()

@router.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 엔드포인트"""
    connection_id = await manager.connect(websocket)
    
    try:
        # 연결 확인 메시지 전송
        await manager.send_personal_message(
            json.dumps({
                "type": "connection_established",
                "message": "WebSocket 연결이 성공했습니다",
                "connection_id": connection_id,
                "timestamp": asyncio.get_event_loop().time()
            }),
            websocket
        )
        
        # 클라이언트로부터 메시지 수신 대기 (keep-alive용)
        while True:
            try:
                # 클라이언트에서 ping 메시지나 기타 메시지 수신
                message = await websocket.receive_text()
                logger.debug(f"클라이언트로부터 메시지 수신: {message}")
                
                # ping 메시지에 대한 pong 응답
                if message == "ping":
                    await manager.send_personal_message("pong", websocket)
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"메시지 수신 중 오류: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info(f"클라이언트가 연결을 종료했습니다: {connection_id}")
    except Exception as e:
        logger.error(f"WebSocket 오류: {e}")
    finally:
        manager.disconnect(websocket)

@router.get("/status")
async def websocket_status():
    """WebSocket 연결 상태 확인"""
    return {
        "active_connections": manager.get_connection_count(),
        "status": "running"
    }