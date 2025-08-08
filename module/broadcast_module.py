# module/socket_broadcast_module.py
import asyncio
import json
import logging
from typing import List, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
from dependency_injector.wiring import inject, Provide
from container.redis_container import Redis_Container
from db.redis_db import RedisDB

logger = logging.getLogger("BroadcastModule")

class BroadcastModule:
    """Redis Pub/Sub과 WebSocket 연결 관리를 통합한 클래스"""
    
    @inject
    def __init__(self, 
                 redis_db: RedisDB = Provide[Redis_Container.redis_db]):
        self.redis_db = redis_db.get_connection()
        self.running = False
        # WebSocket 연결 관리
        self.active_connections: List[WebSocket] = []
        self.connection_count = 0

    async def initialize(self):
        """비동기 초기화"""
        logger.info("✅ WebSocket 브리지 초기화 완료")
        

    async def shutdown(self):
        """브리지 종료"""
        self.running = False
        # 모든 WebSocket 연결 종료
        for connection in self.active_connections.copy():
            try:
                await connection.close()
            except Exception as e:
                logger.error(f"WebSocket 연결 종료 중 오류: {e}")
        self.active_connections.clear()
        logger.info("🛑 WebSocket 브리지 종료 완료")

    # WebSocket 연결 관리 메서드들
    async def connect(self, websocket: WebSocket) -> str:
        """WebSocket 클라이언트 연결"""
        await websocket.accept()
        self.running = True
        self.active_connections.append(websocket)
        self.connection_count += 1
        connection_id = f"conn_{self.connection_count}"
        logger.info(f"WebSocket 클라이언트 연결: {connection_id} (총 {len(self.active_connections)}개)")
        return connection_id

    def disconnect(self, websocket: WebSocket):
        """WebSocket 클라이언트 연결 해제"""
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
        """활성 연결 수 반환"""
        return len(self.active_connections)

    # Redis Pub/Sub 브리지 메서드들
    async def start_bridge(self):
        """Redis Pub/Sub 메시지를 WebSocket으로 전달하는 브리지 시작"""
        self.running = True
        pubsub = self.redis_db.pubsub()
        
        try:
            await pubsub.subscribe('chan')
            logger.info("📡 WebSocket 브리지 시작 - Redis 'chan' 채널 구독")
            
            async for message in pubsub.listen():
                if not self.running:
                    break
                    
                if message['type'] == 'message':
                    try:
                        # Redis에서 받은 메시지를 파싱
                        data = json.loads(message['data'])
                        
                        # 실시간 데이터만 WebSocket으로 전달
                        if data.get('trnm') == 'REAL':
                            # WebSocket 클라이언트들에게 브로드캐스트
                            await self.broadcast(data)
                            logger.debug(f"WebSocket으로 실시간 데이터 전송: {data.get('data', [{}])[0].get('item', 'unknown')}")
                        
                        # 다른 메시지 타입도 전달 (LOGIN, PING 등)
                        elif data.get('trnm') in ['LOGIN', 'PING', 'REG']:
                            await self.broadcast(data)
                            logger.debug(f"WebSocket으로 시스템 메시지 전송: {data.get('trnm')}")
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON 파싱 오류: {e}")
                    except Exception as e:
                        logger.error(f"메시지 브로드캐스트 오류: {e}")
                        
        except Exception as e:
            logger.error(f"WebSocket 브리지 오류: {e}")
        finally:
            try:
                await pubsub.unsubscribe('chan')
                logger.info("Redis 'chan' 채널 구독 해제")
            except Exception as e:
                logger.error(f"Redis 구독 해제 오류: {e}")

    async def send_status_update(self):
        """WebSocket 연결 상태를 주기적으로 전송"""
        while self.running:
            try:
                status_message = {
                    "type": "status_update",
                    "active_connections": self.get_connection_count(),
                    "timestamp": asyncio.get_event_loop().time()
                }
                await self.broadcast(status_message)
                
                # 30초마다 상태 업데이트
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"상태 업데이트 전송 오류: {e}")
                await asyncio.sleep(30)

    async def handle_websocket_connection(self, websocket: WebSocket):
        """WebSocket 연결을 처리하는 통합 핸들러"""
        connection_id = await self.connect(websocket)
        
        try:
            # 연결 확인 메시지 전송
            await self.send_personal_message(
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
                        await self.send_personal_message("pong", websocket)
                        
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
            self.disconnect(websocket)

