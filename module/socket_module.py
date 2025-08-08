#module.socket_module.py

import time

from dependency_injector.wiring import inject, Provide
import asyncio,json,logging, redis
from redis.asyncio import Redis
import websockets
from config import settings
from container.token_container import Token_Container
from container.redis_container import Redis_Container
from db.redis_db import RedisDB
from module.token_module import TokenModule
from utils.dummy import stock_data_stream #test 용 더미 데이터 생산산

logger = logging.getLogger("SocketModule")

class SocketModule:
    """키움 API와 통신하는 클라이언트"""
    @inject
    def __init__(self,
                redis_db : RedisDB = Provide[Redis_Container.redis_db] ,
                token_module: TokenModule = Provide[Token_Container.token_module]):
        # 기본 설정
        self.host = settings.HOST
        self.socket_uri = settings.SOCKET
        self.app_key = settings.KIWOOM_APP_KEY
        self.sec_key = settings.KIWOOM_SECRET_KEY
        
        # Token 관련
        self.token_module = token_module
        self.token = None
        
        # WebSocket 관련
        self.websocket = None
        self.connected = False
        self.keep_running = True
        
        # pubsub
        self.redis_db = redis_db.get_connection()
        self.publisher = self.redis_db.pubsub()
        
        # 로거
        self.logger = logging.getLogger(__name__)
        
        # 실시간 데이터 관리
        self.registered_groups = []
        self.registered_items = {}
        self.websocket_clients = []
  
        # 구독 정보 저장용
        self.saved_subscriptions = {
                                    "groups": {},
                                    "conditions": []     
                                    }

    async def initialize(self):
        """비동기 초기화 메서드: 토큰 요청 재시도 포함"""
        max_retries = 3
        retry_delay = 3  # 초

        for attempt in range(1, max_retries + 1):
            try:
                response_data = self.token_module.get_token_info()

                if response_data.get("return_code") == 0 and "token" in response_data:
                    self.token = response_data["token"]
                    logging.info("✅ socket_module 연결 초기화 완료")
                    return

                # 실패한 경우 로그 출력
                logging.warning(
                    f"❌ 토큰 요청 soc 실패 (시도 {attempt}): {response_data.get('return_msg', '알 수 없는 오류')}"
                )

            except Exception as e:
                logging.exception(f"❌ 토큰 요청 중 예외 발생 (시도 {attempt}): {e}")

            if attempt < max_retries:
                await asyncio.sleep(retry_delay)

        # 여기까지 왔다는 것은 모든 시도 실패
        logging.error("🚫 socket_module 초기화 실패: 최대 재시도 초과")
        raise RuntimeError("socket_module 초기화 실패: 토큰을 가져오지 못했습니다.")


    async def shutdown(self):
        """소켓 모듈 종료 및 리소스 정리"""
        try:
            # WebSocket 연결 종료
            self.keep_running = False
            if self.connected and self.websocket:
                await self.websocket.close()
                self.connected = False
            
            # 상태 초기화
            self.registered_groups = []
            self.registered_items = {}
            self.saved_subscriptions = {"groups": {}, "conditions": []}
            
            # Redis PubSub 연결 종료
            if hasattr(self, 'publisher') and self.publisher:
                await self.publisher.close()
            
            logging.info("🛑 소켓 모듈 종료 완료")
        except Exception as e:
            logging.error(f"소켓 모듈 종료 중 오류 발생: {str(e)}")

    # WebSocket 서버에 연결합니다.
    async def connect(self):
      try:
        self.websocket = await websockets.connect(self.socket_uri)
        self.connected = True
        logging.info("서버와 연결을 시도 중입니다.")
        # 로그인 패킷
        param = {
          'trnm': 'LOGIN',
          'token': self.token
        }

        logging.info('실시간 시세 서버로 로그인 패킷을 전송합니다.')
        # 웹소켓 연결 시 로그인 정보 전달
        await self.send_message(message=param)

      except Exception as e:
        logging.info(f'Connection error: {e}')
        self.connected = False

    # WebSocket 연결 종료
    async def disconnect(self):
      self.keep_running = False
      if self.connected and self.websocket:
        await self.websocket.close()
        self.connected = False
        logging.info('Disconnected from WebSocket server')
        
    async def send_message(self, message):
      if not self.connected:
        await self.connect()  # 연결이 끊어졌다면 재연결
      if self.connected:
        
        if not isinstance(message, str):
          message = json.dumps(message)
        # 실시간 항목 등록
        await self.websocket.send(message)
        return True  # 메시지 전송 성공
      return False  # 연결 실패
    
    async def save_price(self,type_code, stock_code, price_data):
        key = f"redis:{type_code}:{stock_code}"
        score = time.time()   # UTC time 
        member = json.dumps(price_data)
        await self.redis_db.zadd(key, {member: score})
        data_holding_time = score - 60 * 20  # 20분이 지난 데이터는 삭제
        await self.redis_db.zremrangebyscore(key, 0, data_holding_time)
        
# 서버에서 오는 메시지를 수신하여 출력합니다.
    async def pub_messages(self):
        # stream = stock_data_stream() # test 용 더미
        while self.keep_running:
            try:
                # 연결이 끊어진 경우 재연결 시도
                if not self.connected:
                    logging.info("WebSocket 연결이 끊어졌습니다. 재연결 시도 중...")
                    await self.connect()
                    if not self.connected:
                        # 재연결 실패 시 잠시 대기 후 다시 시도
                        await asyncio.sleep(5)
                        continue
                # response = next(stream)
                # time.sleep(0.5)
                response = json.loads(await self.websocket.recv())   # 실제 데이터터
                if response and response['trnm'] == 'REAL': 
                    data = response.get('data', [])
                    for index, item in enumerate(data):
                        stock_code = item.get('item')
                        type_code  = item.get('type')
                        await self.save_price(type_code, stock_code, item)
                await self.redis_db.publish('chan', json.dumps(response))
                
            except websockets.ConnectionClosed:
                logging.info('Connection closed by the server')
                self.connected = False
                # 연결이 끊어졌을 때 keep_running을 False로 설정하지 않고, 대신 connected만 False로 설정
                # self.keep_running = False  <- 이 부분을 제거
                await self.websocket.close()
                await asyncio.sleep(5)  # 재연결 전 잠시 대기
            
            except Exception as e:
                logging.error(f"메시지 수신 중 오류 발생: {e}")
                self.connected = False
                await asyncio.sleep(5)  # 오류 발생 시 잠시 대기