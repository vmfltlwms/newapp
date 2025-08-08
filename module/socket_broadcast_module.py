# module/websocket_bridge.py
import asyncio
import json
import logging
from dependency_injector.wiring import inject, Provide
from container.redis_container import Redis_Container
from db.redis_db import RedisDB
from api.socket_broadcast import manager

logger = logging.getLogger("WebSocketBroadcast")

class WebSocketBroadcast:
    """Redis Pub/Sub과 WebSocket을 연결하는 브리지"""
    
    @inject
    def __init__(self, 
                 redis_db: RedisDB = Provide[Redis_Container.redis_db]):
        self.redis_db = redis_db.get_connection()
        self.running = False
        self.manager = None  # ConnectionManager는 나중에 주입

    async def initialize(self):
        """비동기 초기화"""
        # api.websocket에서 manager 가져오기
        try:
            self.manager = manager
            logger.info("✅ WebSocket 브리지 초기화 완료")
        except ImportError as e:
            logger.error(f"WebSocket manager 가져오기 실패: {e}")

    async def shutdown(self):
        """브리지 종료"""
        self.running = False
        logger.info("🛑 WebSocket 브리지 종료 완료")

    async def start_bridge(self):
        """Redis Pub/Sub 메시지를 WebSocket으로 전달하는 브리지 시작"""
        if not self.manager:
            logger.error("WebSocket manager가 초기화되지 않았습니다")
            return

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
                            await self.manager.broadcast(data)
                            logger.debug(f"WebSocket으로 실시간 데이터 전송: {data.get('data', [{}])[0].get('item', 'unknown')}")
                        
                        # 다른 메시지 타입도 전달 (LOGIN, PING 등)
                        elif data.get('trnm') in ['LOGIN', 'PING', 'REG']:
                            await self.manager.broadcast(data)
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
                if self.manager:
                    status_message = {
                        "type": "status_update",
                        "active_connections": self.manager.get_connection_count(),
                        "timestamp": asyncio.get_event_loop().time()
                    }
                    await self.manager.broadcast(status_message)
                
                # 30초마다 상태 업데이트
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"상태 업데이트 전송 오류: {e}")
                await asyncio.sleep(30)