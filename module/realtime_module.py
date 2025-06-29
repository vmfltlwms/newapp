#module.realtime_module.py

import asyncio
from dependency_injector.wiring import inject, Provide
import logging
import json

from config import settings
from container.socket_container import Socket_Container
from module.socket_module import SocketModule
logger = logging.getLogger(__name__)

class RealtimeModule:
    """키움 API와 통신하는 클라이언트"""
    @inject
    def __init__(self,
                socket_module:SocketModule = Provide[Socket_Container.socket_module]):
      # 기본 설정
      self.host = settings.HOST
      self.socket_module = socket_module

      # 로거
      self.logger = logging.getLogger(__name__)
      
      # 실시간 데이터 관리
      self.registered_groups = []
      self.registered_items = {}
      self.websocket_clients = []
      
      # 응답 대기 - Redis pub/sub 방식으로 변경
      self.response_subscribers = {}
      self.condition_responses = {}
      
      # 구독 정보 저장용
      self.saved_subscriptions = {
                                  "groups": {},
                                  "conditions": []     
                                  }
        
    @property
    def connected(self):
      return self.socket_module.connected  

    async def initialize(self):
      """비동기 초기화 - Redis 구독자 시작"""
      # Redis 채널 구독 시작
      await self.start_redis_subscriber()
      logging.info("✅ realtime_module 초기화 완료")
      
    async def start_redis_subscriber(self):
        """Redis pub/sub 구독자 시작"""
        try:
            # Redis 연결 가져오기
            redis_conn = self.socket_module.redis_db
            pubsub = redis_conn.pubsub()
            await pubsub.subscribe('chan')
            
            # 백그라운드에서 메시지 수신
            asyncio.create_task(self.handle_redis_messages(pubsub))
            logging.info("Redis 구독자 시작됨")
        except Exception as e:
            logging.error(f"Redis 구독자 시작 실패: {str(e)}")
    
    # Redis에서 오는 메시지 처리
    async def handle_redis_messages(self, pubsub):
        try:
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        trnm = data.get('trnm')
                        
                        # 조건검색 관련 응답 처리
                        if trnm in ['CNSRLST', 'CNSRREQ', 'CNSRCNC']:
                            await self.process_condition_response(trnm, data)
                            
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logging.error(f"메시지 처리 중 오류: {str(e)}")
        except Exception as e:
            logging.error(f"Redis 메시지 수신 중 오류: {str(e)}")
    
    # 조건검색 응답 처리
    async def process_condition_response(self, trnm, data):
        try:
            # 대기 중인 요청이 있는지 확인
            if trnm in self.response_subscribers:
                future = self.response_subscribers[trnm]
                if not future.done():
                    future.set_result(data)
                    logging.info(f"{trnm} 응답 처리 완료")
                # 처리 완료된 Future 제거
                del self.response_subscribers[trnm]
        except Exception as e:
            logging.error(f"조건검색 응답 처리 중 오류: {str(e)}")
        
    async def shutdown(self):
        """실시간 모듈 종료 및 리소스 정리"""
        try:
            # 등록된 모든 실시간 구독 해제
            for group_no in self.registered_groups:
                try:
                    await self.unsubscribe_realtime_price(group_no=group_no, items=[], data_types=[])
                except Exception as e:
                    logging.error(f"그룹 {group_no} 구독 해제 중 오류: {str(e)}")
            
            # 대기 중인 Future 객체들 정리
            for future in self.response_subscribers.values():
                if not future.done():
                    future.cancel()
            
            # 상태 초기화
            self.registered_groups = []
            self.registered_items = {}
            self.saved_subscriptions = {"groups": {}, "conditions": []}
            self.response_subscribers = {}
            
            logging.info("🛑 실시간 모듈 종료 완료")
        except Exception as e:
            logging.error(f"실시간 모듈 종료 중 오류 발생: {str(e)}")
        
    """ 실시간 시세 정보 구독 함수

    Args:
        group_no (str): 그룹 번호
        items (list): 종목 코드 리스트 (예: ["005930", "000660"])
        data_types (list): 데이터 타입 리스트 (예: ["0D", "0B"])
        refresh (bool): 새로고침 여부 (True: 기존 등록 초기화, False: 기존에 추가)
    
    Returns:
        dict: 요청 결과
    """
    async def subscribe_realtime_price(self, group_no="1", 
                                        items=None, 
                                        data_types=None, 
                                        refresh=True):
  
        if not self.connected:
            await self.socket_module.connect()
  
        if not self.connected:
            logger.error("키움 API에 연결되어 있지 않습니다.")
            return {"error": "키움 API에 연결되어 있지 않습니다."}
        
        # 기본값 설정
        if items is None:
            items = []
        
        if data_types is None:
            data_types = ["0B"]  # 기본적으로 현재가 구독
        
        try:
            # 요청 데이터 구성
            request_data = {
                'trnm': 'REG',                      # 등록 명령
                'grp_no': str(group_no),            # 그룹 번호
                'refresh': '1' if refresh else '0', # 새로고침 여부
                'data': [{
                    'item': items,                  # 종목 코드 리스트
                    'type': data_types              # 데이터 타입 리스트
                }]
            }
            
            
            # 요청 전송
            logger.info(f"실시간 시세 구독 요청: 그룹={group_no}, 종목={items}, 타입={data_types}")
            result = await self.socket_module.send_message(request_data)
            
            if result:
                return {
                    "status": "success", 
                    "message": "실시간 시세 구독 요청 완료",
                    "group_no": group_no,
                    "items": items,
                    "types": data_types
                }
            else:
                return {"error": "실시간 시세 구독 요청 실패"}
                
        except Exception as e:
            logger.error(f"실시간 시세 구독 오류: {str(e)}")
            return {"error": f"실시간 시세 구독 오류: {str(e)}"}
        
    #실시간 시세 정보 구독 해제 함수
    async def unsubscribe_realtime_price(self, group_no="1", 
                                        items=None, 
                                        data_types=None, 
                                        refresh=True):

        
        if not self.connected:
            logger.error("키움 API에 연결되어 있지 않습니다.")
            return {"error": "키움 API에 연결되어 있지 않습니다."}
        
        try:
            # 그룹 번호 문자열 변환
            group_no = str(group_no)

            request_data = {
                'trnm': 'REG',                      # 등록 명령
                'grp_no': str(group_no),            # 그룹 번호
                'refresh': '1' if refresh else '0', # 새로고침 여부
                'data': [{
                    'item': items,                  # 종목 코드 리스트
                    'type': data_types              # 데이터 타입 리스트
                }]
            }
            
            # 요청 전송
            logger.info(f"실시간 시세 구독 해제 요청: 그룹={group_no} (전체 해제)")
            result = await self.socket_module.send_message(request_data)
            if result:
                return {
                    "status": "success", 
                    "message": f"그룹 {group_no} 실시간 시세 구독 해제 완료 (전체)",
                    "group_no": group_no
                }
            else:
                return {"error": "실시간 시세 구독 해제 요청 실패"}
 
        except Exception as e:
            logger.error(f"실시간 시세 구독 해제 오류: {str(e)}")
            return {"error": f"실시간 시세 구독 해제 오류: {str(e)}"}

    """조건검색 목록 조회 (ka10171)"""
    async def get_condition_list(self):
        if not self.connected:
            logger.error("키움 API에 연결되어 있지 않습니다.")
            return {"error": "키움 API에 연결되어 있지 않습니다."}
        
        try:
            # 조건검색 목록 요청 메시지 작성
            request_data = {
                'trnm': 'CNSRLST'  # TR명 (조건검색 목록 조회)
            }
            
            # 요청 전송 및 응답 대기 (Redis 방식)
            response = await self.send_and_wait_for_redis_response(request_data, 'CNSRLST', timeout=10.0)
            logger.info(f"조건검색 요청 완료 : {response}")
            # 오류 확인
            if isinstance(response, dict) and "error" in response:
                return response
                
            return response
            
        except Exception as e:
            logger.error(f"조건검색 목록 조회 오류: {str(e)}")
            return {"error": f"조건검색 목록 조회 오류: {str(e)}"}

    """조건검색 요청 일반 (ka10172)"""
    async def request_condition_search(self, seq="1", search_type="0", stex_tp = "K", cont_yn="N", next_key=""):
        if not self.connected:
            logger.error("키움 API에 연결되어 있지 않습니다.")
            return {"error": "키움 API에 연결되어 있지 않습니다."}
        
        try:
            # 조건검색 요청 메시지 작성
            request_data = {
                'trnm': 'CNSRREQ',  # TR명 (조건검색 요청 일반)
                'seq': seq,  # 조건검색식 일련번호
                'search_type': search_type,  # 조회타입 (0: 일반조건검색)
                'stex_tp': stex_tp	,  # K: KRX
                'cont_yn': cont_yn,  # 연속조회 여부
                'next_key': next_key  # 연속조회 키
            }
            
            # 요청 전송 및 응답 대기 (Redis 방식)
            response = await self.send_and_wait_for_redis_response(request_data, 'CNSRREQ', timeout=20.0)
            # 오류 확인
            if isinstance(response, dict) and "error" in response:
                return response
                
            return response
            
        except Exception as e:
            logger.error(f"조건검색 요청 오류: {str(e)}")
            return {"error": f"조건검색 요청 오류: {str(e)}"}

    """조건검색 요청 실시간 (ka10173)"""
    async def request_realtime_condition(self, seq, search_type="1", stex_tp="K"):
        if not self.connected:
            logger.error("키움 API에 연결되어 있지 않습니다.")
            return {"error": "키움 API에 연결되어 있지 않습니다."}
        
        try:
            # 실시간 조건검색 요청 메시지 작성
            request_data = {
                'trnm': 'CNSRREQ',  # TR명 (조건검색 요청 실시간)
                'seq': seq,  # 조건검색식 일련번호
                'search_type': search_type,  # 조회타입 (1: 조건검색+실시간조건검색)
                'stex_tp': stex_tp # K: KRX
            }
            
            # 요청 전송 및 응답 대기 (Redis 방식)
            response = await self.send_and_wait_for_redis_response(request_data, 'CNSRREQ', timeout=10.0)
            
            # 오류 확인
            if isinstance(response, dict) and "error" in response:
                return response
            
            # 실시간 조건검색 그룹 등록
            condition_group = f"cond_{seq}"
            if condition_group not in self.registered_groups:
                self.registered_groups.append(condition_group)
            
            return response
            
        except Exception as e:
            logger.error(f"실시간 조건검색 요청 오류: {str(e)}")
            return {"error": f"실시간 조건검색 요청 오류: {str(e)}"}

    """조건검색 실시간 해제 (ka10174)"""
    async def cancel_realtime_condition(self, seq):
        if not self.connected:
            logger.error("키움 API에 연결되어 있지 않습니다.")
            return {"error": "키움 API에 연결되어 있지 않습니다."}
        
        try:
            # 실시간 조건검색 해제 메시지 작성
            request_data = {
                'trnm': 'CNSRCNC',  # TR명 (조건검색 실시간 해제)
                'seq': seq  # 조건검색식 일련번호
            }
            
            # 요청 전송 및 응답 대기 (Redis 방식)
            response = await self.send_and_wait_for_redis_response(request_data, 'CNSRCNC', timeout=10.0)
            
            # 오류 확인
            if isinstance(response, dict) and "error" in response:
                return response
                
            # 실시간 조건검색 그룹 제거
            condition_group = f"cond_{seq}"
            if condition_group in self.registered_groups:
                self.registered_groups.remove(condition_group)
            
            return response
            
        except Exception as e:
            logger.error(f"실시간 조건검색 해제 오류: {str(e)}")
            return {"error": f"실시간 조건검색 해제 오류: {str(e)}"}

    """Redis pub/sub을 통해 응답을 기다리는 새로운 방식"""
    async def send_and_wait_for_redis_response(self, message, trnm, timeout=10.0):
        if not self.connected:
            logger.warning("연결이 끊겨 있습니다. 재연결 시도 중...")
            await self.socket_module.connect()
            
        if not self.connected:
            return {"error": "서버에 연결할 수 없습니다."}
            
        try:
            logger.info(f"현재 등록된 response_subscribers 목록: {list(self.response_subscribers.keys())}")
            
            # Future 객체 생성
            future = asyncio.Future()
            
            # 응답 추적을 위해 trnm을 키로 사용
            logger.info(f"{trnm} 응답 대기를 위한 Future 객체 생성")
            self.response_subscribers[trnm] = future
            
            # 메시지 전송
            logger.info(f"{trnm} 요청 메시지 전송: {message}")
            result = await self.socket_module.send_message(message)
            if not result:
                if trnm in self.response_subscribers:
                    del self.response_subscribers[trnm]
                logger.error(f"{trnm} 메시지 전송 실패")
                return {"error": "메시지 전송 실패"}
                
            # Redis를 통한 응답 대기
            try:
                logger.info(f"{trnm} Redis 응답 대기 시작 (타임아웃: {timeout}초)")
                response = await asyncio.wait_for(future, timeout)
                # logger.info(f"{trnm} Redis 응답 수신 성공: {response}")
                return response
            except asyncio.TimeoutError:
                logger.error(f"{trnm} Redis 응답 대기 시간 초과")
                return {"error": f"{trnm} 응답 대기 시간 초과"}
            finally:
                # Future 객체 삭제
                if trnm in self.response_subscribers:
                    logger.info(f"{trnm} Future 객체 삭제")
                    del self.response_subscribers[trnm]
                    
        except Exception as e:
            logger.error(f"Redis 응답 대기 중 오류: {str(e)}")
            if trnm in self.response_subscribers:
                del self.response_subscribers[trnm]
            return {"error": f"Redis 응답 대기 중 오류: {str(e)}"}
          
          