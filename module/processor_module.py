# module.processor_module.py - 수정된 버전
import math
from data.stock_code import KOSPI 
from datetime import date, datetime, time as datetime_time
import json
import time
from typing import Dict, List, Union
from dependency_injector.wiring import inject, Provide
import asyncio, json, logging 
from sqlmodel import select
import pytz
from container.redis_container import Redis_Container
from container.postgres_container import Postgres_Container
from container.socket_container import Socket_Container
from container.kiwoom_container import Kiwoom_Container
from container.step_manager_container import Step_Manager_Container
from container.realtime_container import RealTime_Container
from container.realtime_group_container import RealtimeGroup_container
from db.redis_db import RedisDB
from db.postgres_db import PostgresDB
from module.socket_module import SocketModule
from module.kiwoom_module import KiwoomModule  
from module.realtimegroup_module import RealtimeGroupModule
from module.baseline_module import BaselineModule
from module.step_manager_module import StepManagerModule
from module.realtime_module import RealtimeModule
from redis_util.stock_analysis import StockDataAnalyzer
from models.isfirst import IsFirst
from services.smart_trading_service import SmartTrading
from redis_util.price_tracker_service import PriceTracker

logger = logging.getLogger(__name__)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


class ProcessorModule:
    @inject
    def __init__(self, 
                redis_db: RedisDB = Provide[Redis_Container.redis_db],
                postgres_db : PostgresDB = Provide[Postgres_Container.postgres_db],
                socket_module: SocketModule = Provide[Socket_Container.socket_module],
                kiwoom_module: KiwoomModule = Provide[Kiwoom_Container.kiwoom_module],
                realtime_module:RealtimeModule = Provide[RealTime_Container.realtime_module],
                step_manager_module : StepManagerModule = Provide[Step_Manager_Container.step_manager_module],
                realtime_group_module:RealtimeGroupModule = Provide[RealtimeGroup_container.realtime_group_module] ):
        self.redis_db = redis_db.get_connection()
        self.postgres_db = postgres_db
        self.socket_module = socket_module
        self.kiwoom_module = kiwoom_module
        self.step_manager_module = step_manager_module
        self.realtime_module = realtime_module
        self.realtime_group_module = realtime_group_module
        self.running = False
        self.count = 0 
        self.cancel_check_task = None 
        self.condition_list ={'kospi':set(),'kosdaq':set()} #조건검색 리스트
        
        # 🆕 거래 태스크 관리
        self.trading_tasks = []  # 개별 종목 거래 태스크들
        self.timezone = pytz.timezone('Asia/Seoul')

        self.holding_stock =[]           # 현재 보유중인 주식
        self.stock_qty = {}              # 현재 주식별 보유 수량 관리
        self.deposit = 0                 # 예수금
        self.assigned_per_stock = 0      # 각 주식별 거래가능 금액
        self.account = []                # 내 주식 소유현황
        self.prev_baseline_code = []     # 이전에 유지되고 있는 베이스라인 
        self.order_tracker ={}
        self.order_execution_tracker = {}  # 새로운 추적용
        
        self.StockDataAnalyzer = StockDataAnalyzer(self.redis_db)
        self.PT = PriceTracker(self.redis_db)
        self.ST = SmartTrading( self.kiwoom_module, 
                                self.PT, 
                                self.StockDataAnalyzer,
                                self.redis_db )
        
        self.trnm_callback_table = {
          'LOGIN': self.trnm_callback_login,
          'PING': self.trnm_callback_ping,
          'CNSRLST': self.trnm_callback_cnsrlst,
          'CNSRREQ': self.trnm_callback_cnsrreq,
          'CNSRCLR': self.trnm_callback_cnsrclr,
          'REG': self.trnm_callback_reg,
          'REAL': self.trnm_callback_real,
        }
        
        self.type_callback_table = {
          '00': self.type_callback_00,
          '02': self.type_callback_02,
          '04': self.type_callback_04,
          '0B': self.type_callback_0B,
          '0D': self.type_callback_0D,
        }
        
    async def initialize(self) : # 현재 보유주식별 주식수, 예수금, 주문 취소 확인 및 실행
        
        try:
            # running을 True로 설정한 후 태스크 시작
            self.running = True
            self.holding_stock = await self.extract_stock_codes() # 현재 보유중인 주식 
            # 🔧 수정: stock_qty 딕셔너리 명시적 초기화
            if not hasattr(self, 'stock_qty') or self.stock_qty is None:
                self.stock_qty = {}
            
            # 계좌 수익률 정보로 현재 보유 주식 수량 초기화
            try:
                await self.get_account_return()
            except Exception as e:
                self.stock_qty = {}  # 실패 시 빈 딕셔너리로 초기화
            
            # 예수금 정보 조회
            try:
                self.deposit = await self.clean_deposit()
                
            except Exception as e:
                self.deposit = 0
            # 자동 취소 체크 태스크 시작
            try:
                self.cancel_check_task = asyncio.create_task(self.auto_cancel_checker())
            except Exception as e:
                logger.error(f"❌ 자동 취소 체크 태스크 시작 실패: {str(e)}")
            
            logging.info("✅ ProcessorModule 초기화 완료")
            

                
        except Exception as e:
            logging.error(f"❌ ProcessorModule 초기화 중 오류 발생: {str(e)}")
            # 초기화 실패 시에도 기본 상태 설정
            self.running = True
            self.stock_qty = {}
            self.deposit = 0
            raise

    """프로세서 모듈 종료 및 리소스 정리"""
    async def shutdown(self):
        try:
            # 메시지 수신 루프 중지
            self.running = False
            
            # 🆕 거래 태스크들 중지
            if self.trading_tasks:
                logger.info(f"🛑 {len(self.trading_tasks)}개 거래 태스크 중지 시작")
                for task in self.trading_tasks:
                    task.cancel()
                
                try:
                    await asyncio.gather(*self.trading_tasks, return_exceptions=True)
                    logger.info("🛑 모든 거래 태스크 중지 완료")
                except Exception as e:
                    logger.error(f"거래 태스크 중지 중 오류: {e}")
            
            # 자동 취소 체크 태스크 중지
            if self.cancel_check_task:
                self.cancel_check_task.cancel()
                try:
                    await self.cancel_check_task
                except asyncio.CancelledError:
                    pass
            
            # 추가 대기 - 메시지 처리 루프가 완전히 종료될 때까지 짧게 대기
            await asyncio.sleep(0.5)
            
            logging.info("🛑 프로세서 모듈 종료 완료")
        except Exception as e:
            logging.error(f"프로세서 모듈 종료 중 오류 발생: {str(e)}")

    def is_market_time(self) -> bool:
        """시장 거래 시간 확인"""
        current_time = datetime.now(self.timezone).time()
        market_open = datetime_time(9, 0)
        market_close = datetime_time(15, 30)
        return market_open <= current_time <= market_close

    async def trader_executor(self, stock_code: str):
        """개별 종목 거래 실행기 - 백그라운드에서 지속 실행"""
        logger.info(f"🚀 [{stock_code}] 거래 실행기 시작")
        
        try:
            while self.running:
                # 시장 시간 체크
                if not self.is_market_time():
                    await asyncio.sleep(60)  # 폐장시간엔 1분 대기
                    continue
                
                try:
                    # SmartTrading 거래 실행
                    result = await self.ST.execute_trade_order(stock_code)
                    if result:
                        logger.info(f"✅ [{stock_code}] 거래 실행됨")
                    else:
                        logger.debug(f"⏸️ [{stock_code}] 거래 신호 없음 또는 대기")
                
                except Exception as e:
                    logger.error(f"❌ [{stock_code}] 거래 오류: {e}")
                
                # 30초 대기
                await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            logger.info(f"🛑 [{stock_code}] 거래 실행기 종료")
            raise
        except Exception as e:
            logger.error(f"❌ [{stock_code}] 거래 실행기 예외: {e}")

    # 클린 deposit
    async def clean_deposit(self) -> int :
        await asyncio.sleep(0.3)
        res = await self.kiwoom_module.get_deposit_detail() 
        entr_value = res.get("ord_alow_amt", "0")
        # 문자열이든 숫자든 통합 처리
        cleaned_value = str(entr_value).replace(',', '').strip()
        res = abs(int(cleaned_value)) if cleaned_value.lstrip('-').isdigit() else 0
        return res 
    
    # 2. order_data_tracker 메서드 수정 (변수명 충돌 해결)
    def track_order_execution(self, order_number, order_qty, trade_qty, untrade_qty):
        """주문 체결 추적 및 증분 체결량 계산"""
        try:
            # order_execution_tracker 딕셔너리 사용 (기존 order_tracker와 구분)
            if not hasattr(self, 'order_execution_tracker'):
                self.order_execution_tracker = {}
            
            # 이전 누적 체결량 조회
            if order_number in self.order_execution_tracker:
                prev_total_qty = int(self.order_execution_tracker[order_number].get("trade_qty", 0))
            else:
                prev_total_qty = 0

            # 현재 체결량 (누적값)
            current_total_qty = int(trade_qty) if trade_qty else 0
            
            # 주문 정보 업데이트
            self.order_execution_tracker[order_number] = {
                'order_qty': int(order_qty),
                'trade_qty': current_total_qty,  # 누적 체결량
                'untrade_qty': int(untrade_qty)
            }

            # 전량 체결되었으면 삭제
            if current_total_qty >= int(order_qty) and int(untrade_qty) == 0:
                logger.info(f"{order_number}에 대한 주문이 완료되었습니다")
                del self.order_execution_tracker[order_number]

            # 이번에 체결된 증분 수량 반환
            incremental_qty = max(current_total_qty - prev_total_qty, 0)
            return incremental_qty
            
        except Exception as e:
            logger.error(f"주문 추적 중 오류: {e}")
            return 0
      
    # 현재 주식 보유수량 추출 - 수정된 버전
    async def get_account_return(self) -> dict:
        """계좌 수익률 정보에서 보유 주식 수량 추출"""
        try:
            data = await self.kiwoom_module.get_account_return()
            
            if not data or 'acnt_prft_rt' not in data:
                logger.warning("⚠️ 계좌 수익률 데이터가 없습니다.")
                return {}
            
            # 🔧 수정: 기존 stock_qty 초기화
            if not hasattr(self, 'stock_qty'):
                self.stock_qty = {}
            else:
                self.stock_qty.clear()  # 기존 데이터 정리
            
            account_data = data.get("acnt_prft_rt", [])
            
            for item in account_data:
                try:
                    stk_cd = item.get("stk_cd", "").strip()
                    rmnd_qty_str = item.get("rmnd_qty", "0").strip()
                    
                    # 종목코드 검증
                    if not stk_cd:
                        continue
                    
                    # 🔧 수정: 안전한 수량 변환
                    try:
                        rmnd_qty = int(rmnd_qty_str.replace(',', '')) if rmnd_qty_str.replace(',', '').isdigit() else 0
                    except (ValueError, AttributeError):
                        logger.warning(f"⚠️ 수량 변환 실패: {stk_cd} - {rmnd_qty_str}")
                        rmnd_qty = 0
                    
                    # 수량이 0보다 큰 경우만 저장
                    if rmnd_qty > 0:
                        # A 제거 (A012345 → 012345)
                        clean_code = stk_cd[1:] if stk_cd.startswith('A') else stk_cd
                        self.stock_qty[clean_code] = rmnd_qty
                    
                except Exception as e:
                    logger.error(f"❌ 개별 종목 처리 오류: {item}, 오류: {str(e)}")
                    continue
            return self.stock_qty
            
        except Exception as e:
            logger.error(f"❌ 계좌 수익률 조회 오류: {str(e)}")
            # 오류 발생 시 빈 딕셔너리 반환
            if not hasattr(self, 'stock_qty'):
                self.stock_qty = {}
            return self.stock_qty
       
  
    async def receive_messages(self):
        logging.info("📥 Redis 채널 'chan'에서 메시지 수신 시작")
        self.running = True

        pubsub = self.redis_db.pubsub()
        await pubsub.subscribe('chan')

        try:
            async for message in pubsub.listen():
                if not self.running:
                    break
                  
                if message['type'] != 'message':
                    continue  # 'subscribe', 'unsubscribe' 등은 무시

                try:
                    response = json.loads(message['data'])
                    await self.trnm_callback(response)
                    
                except json.JSONDecodeError as e:
                    logging.error(f'JSON 파싱 오류: {e}, 원본 메시지: {message["data"]}')
                    
                except Exception as e:
                    logging.error(f'메시지 처리 오류: {e}')

        except asyncio.CancelledError:
            logging.info("메시지 수신 태스크가 취소되었습니다.")
            
        except Exception as e:
            logging.error(f"메시지 수신 중 오류 발생: {e}")
            
        finally:
            await pubsub.unsubscribe('chan')
            logging.info("'chan' 채널 구독 해제 완료")

    # trnm callback handelr
    async def trnm_callback(self, response:dict):
        trnm_type = response.get('trnm')
        handler = self.trnm_callback_table.get(trnm_type, self.trnm_callback_unknown)
        await handler(response)    
        
    async def trnm_callback_login(self, response:dict):
        if response.get('return_code') != 0:
            logging.info(f'로그인 실패 : {response.get("return_msg")}')
        else:
            logging.info('로그인 성공')

    async def trnm_callback_ping(self, response:dict):
        await self.socket_module.send_message(response)
        logging.info('ping pong')
        
    async def trnm_callback_real(self, response:dict):
        data = response.get('data', [])
        self.count += 1
        vlaues = data[0]
        request_type = vlaues.get('type')
        request_item = vlaues.get('item')
        request_name = vlaues.get('name')
        # logger.info(f"{self.count} 번째로 호툴된 타입 {request_type}, 코드 : {request_item},  이름 {request_name}")
        await self.type_callback(response)
        
    async def trnm_callback_cnsrlst(self, response:dict):
        pass

    async def trnm_callback_cnsrreq(self, response:dict):
        await self.stock_codes_grouping(response) # 반환되는 코드를 realtime group 에 추가
        logger.info("trnm_callback_cnsrreq 실행")

    async def trnm_callback_cnsrclr(self, response:dict):
        pass

    async def trnm_callback_reg(self, response:dict):
        pass

    async def trnm_callback_unknown(self, response:dict):
        logging.warning(f'알 수 없는 trnm_type: {response.get("trnm")}')            

   # type callback handler

    async def type_callback(self, response: dict):
        """실시간 데이터 타입별 콜백 처리 - 배열의 모든 요소 처리"""
        data = response.get('data', [])
        
        if not data:
            logging.warning("빈 실시간 데이터 수신")
            return
        
        # logging.info(f" {self.count} 번째 데이터 전체 데이터 수신 data \n {data}")
        # 🔧 수정: 배열의 모든 요소를 순회하여 처리
        for index, item in enumerate(data):
            try:
                if not isinstance(item, dict):
                    logging.warning(f"잘못된 데이터 타입 (인덱스 {index}): {type(item)}")
                    continue
                    
                request_type = item.get('type')
                request_item = item.get('item')
                request_name = item.get('name')
                
                if request_type != "0B" :
                    logger.info(f"호출된 타입 {request_type} 아이템 {request_item} 이름 {request_name} (인덱스: {index})")
                
                # 해당 타입의 핸들러 찾기
                handler = self.type_callback_table.get(request_type)
                
                if handler:
                    await handler(item)
                else:
                    logging.warning(f"알 수 없는 실시간 타입 수신: {request_type} (인덱스: {index})")
                    
            except Exception as e:
                logging.error(f"개별 데이터 처리 중 오류 (인덱스 {index}): {str(e)}")
                logging.error(f"문제 데이터: {item}")
                continue

    async def type_callback_00(self, data: dict): 
        try:
            values = data.get('values', {})   
            stock_code = values.get('item')
            stock_code = stock_code[1:] if stock_code and stock_code.startswith('A') else stock_code

            if not stock_code:
                logging.warning("주문체결 데이터에 종목코드(item)가 없습니다.")
                return
            
            # 필요한 필드만 추출 (안전한 기본값 설정)
            def safe_get_value(data_dict, key, default='0'):
                value = data_dict.get(key, default)
                return default if value == '' or value is None else str(value)
            
            # 주문 데이터 구성
            order_data = {
                '9201': safe_get_value(values, '9201', ''),    # 계좌번호
                '9203': safe_get_value(values, '9203', ''),    # 주문번호  
                '9001': safe_get_value(values, '9001', ''),    # 종목코드,업종코드
                '10'  : safe_get_value(values, '10', '0'),     # 현재가격
                '913': safe_get_value(values, '913', ''),      # 주문상태
                '302': safe_get_value(values, '302', ''),      # 종목명
                '900': safe_get_value(values, '900', '0'),     # 주문수량
                '901': safe_get_value(values, '901', '0'),     # 주문가격
                '902': safe_get_value(values, '902', '0'),     # 미체결수량
                '903': safe_get_value(values, '903', '0'),     # 체결누계금액
                '904': safe_get_value(values, '904', ''),      # 원주문번호
                '905': safe_get_value(values, '905', ''),      # 주문구분
                '906': safe_get_value(values, '906', ''),      # 매매구분
                '907': safe_get_value(values, '907', ''),      # 매도수구분
                '908': safe_get_value(values, '908', ''),      # 주문/체결시간
                '910': safe_get_value(values, '910', '0'),     # 체결가
                '911': safe_get_value(values, '911', '0'),     # 체결량
                '914': safe_get_value(values, '914', '0'),     # 단위체결가
                '915': safe_get_value(values, '915', '0'),     # 단위체결량
                '919': safe_get_value(values, '919', ''),      # 거부사유
                'timestamp': time.time(),
                'type': '00',
                'name': data.get('name', ''),
            }
            
            # 안전한 데이터 추출
            order_number = order_data.get('9203', '0')
            order_qty = self.safe_int_convert(order_data.get('900', '0'))
            trade_qty = self.safe_int_convert(order_data.get('911', '0'))
            untrade_qty = self.safe_int_convert(order_data.get('902', '0'))
            execution_price = self.safe_int_convert(order_data.get('910', '0'))
            order_status = str(order_data.get('905', '')).strip()
            order_state = str(order_data.get('913', '')).strip()
            
            # 주문번호 유효성 검사
            if not order_number or order_number == '0':
                logging.warning(f"유효하지 않은 주문번호: {order_number}")
                return
            
            # 증분 체결량 계산
            incremental_trade_qty = self.track_order_execution(order_number, order_qty, trade_qty, untrade_qty)
            
            logger.info(f"📋 주문 {order_number} - 종목: {stock_code}, 주문량: {order_qty}, "
                      f"증분체결량: {incremental_trade_qty}, 총체결량: {trade_qty}")
            
            # 주문 상태 분류
            is_cancelled = '취소' in order_status or '취소' in order_state
            is_rejected = '거부' in order_status or '거부' in order_state
            is_buy_order = '매수' in order_status and not is_cancelled and not is_rejected
            is_sell_order = '매도' in order_status and not is_cancelled and not is_rejected
            
            # 1. 취소/거부 주문 처리
            if is_cancelled or is_rejected:
                order_data['902'] = '0'  # 미체결수량 0으로 설정
                
                # 예수금 업데이트
                prev_deposit = self.deposit
                self.deposit = await self.clean_deposit()
                
                status_text = "취소" if is_cancelled else "거부"
                logging.info(f"🚫 주문 {status_text} 처리 - 종목: {stock_code}, "
                            f"주문번호: {order_number}, 상태: {order_status}")
                logging.info(f"💰 예수금 변화: {prev_deposit:,} → {self.deposit:,}")
            
            # 2. 실제 체결된 경우만 수량 업데이트
            elif incremental_trade_qty > 0 and execution_price > 0:
                # 추적 데이터 조회 (안전한 처리)
                tracking_data = await self.PT.get_tracking_data(stock_code)
                
                if not tracking_data:
                    logging.warning(f"⚠️ 종목 {stock_code}의 추적 데이터가 없습니다. 체결 처리를 건너뜁니다.")
                    return
                
                # 안전한 수량 추출
                current_qty_to_sell = tracking_data.get('qty_to_sell', 0)
                current_qty_to_buy = tracking_data.get('qty_to_buy', 0)
                
                # 전량 체결 시 예수금 업데이트
                if untrade_qty == 0 and trade_qty == order_qty:
                    prev_deposit = self.deposit
                    self.deposit = await self.clean_deposit()
                    logging.info(f"💰 전량 체결로 예수금 업데이트: {prev_deposit:,} → {self.deposit:,}")
                
                # 매수 주문 처리
                if is_buy_order:
                    # 증분 체결량으로 수량 업데이트
                    qty_to_sell = max(current_qty_to_sell + incremental_trade_qty, 0)
                    qty_to_buy = max(current_qty_to_buy - incremental_trade_qty, 0)
                    
                    # Redis 업데이트
                    await self.PT.update_tracking_data(
                          stock_code=stock_code,
                          trade_price = execution_price,
                          qty_to_sell=qty_to_sell,
                          qty_to_buy=qty_to_buy,
                          trade_type="BUY")
                    
                    # 체결 상태 로그
                    completion_status = "완료" if (untrade_qty == 0 and trade_qty == order_qty) else "부분 체결"
                    
                    logging.info(f"💰 매수 체결 {completion_status} - 주문번호: {order_number}, 종목: {stock_code}")
                    logging.info(f"   📈 체결가: {execution_price:,}원, 증분 체결량: {incremental_trade_qty}주")
                    logging.info(f"   📊 매도가능 수량: {current_qty_to_sell} → {qty_to_sell}주")
                    logging.info(f"   📊 매수가능 수량: {current_qty_to_buy} → {qty_to_buy}주")
                
                # 매도 주문 처리
                elif is_sell_order:
                    # 증분 체결량으로 수량 업데이트
                    qty_to_sell = max(current_qty_to_sell - incremental_trade_qty, 0)
                    qty_to_buy = max(current_qty_to_buy + incremental_trade_qty, 0)
                    
                    # Redis 업데이트
                    await self.PT.update_tracking_data(
                          stock_code=stock_code,
                          trade_price = execution_price,
                          qty_to_sell=qty_to_sell,
                          qty_to_buy=qty_to_buy,
                          trade_type="SELL")
                    
                    # 체결 상태 로그
                    completion_status = "완료" if (untrade_qty == 0 and trade_qty == order_qty) else "부분 체결"
                    
                    logging.info(f"💰 매도 체결 {completion_status} - 주문번호: {order_number}, 종목: {stock_code}")
                    logging.info(f"   📉 체결가: {execution_price:,}원, 증분 체결량: {incremental_trade_qty}주")
                    logging.info(f"   📊 매도가능 수량: {current_qty_to_sell} → {qty_to_sell}주")
                    logging.info(f"   📊 매수가능 수량: {current_qty_to_buy} → {qty_to_buy}주")
                
                else:
                    logging.warning(f"⚠️ 알 수 없는 주문 타입: {order_status}")
            
            # 3. 체결량이 없는 경우 (단순 상태 업데이트)
            else:
                if incremental_trade_qty == 0 and execution_price == 0:
                    logging.debug(f"📝 주문 상태 업데이트 - 주문번호: {order_number}, 상태: {order_status}")
                else:
                    logging.warning(f"⚠️ 비정상적인 체결 데이터 - 주문번호: {order_number}, "
                                  f"증분체결량: {incremental_trade_qty}, 체결가: {execution_price}")
            
            # Redis에 주문 데이터 저장 (socket_module에서 처리하므로 여기서는 로그만)
            logger.debug(f"✅ 주문체결 데이터 처리 완료 - 종목: {stock_code}, 주문번호: {order_number}")
            
        except KeyError as e:
            logging.error(f"❌ 필수 데이터 누락: {str(e)}")
            logging.error(f"원본 데이터: {data}")
            
        except ValueError as e:
            logging.error(f"❌ 데이터 타입 변환 오류: {str(e)}")
            logging.error(f"문제 데이터: {data}")
            
        except Exception as e:
            logging.error(f"❌ 주문체결 데이터 처리 중 예상치 못한 오류: {str(e)}")
            logging.error(f"원본 데이터: {data}")
            import traceback
            logging.error(f"상세 오류 정보: {traceback.format_exc()}")
                
    async def type_callback_02(self, data: dict): 
        logger.info(data)
        
    # 보유주식 수량 업데이트
    async def type_callback_04(self, data: dict):
        """현물잔고 데이터 처리 - 최신 데이터로 업데이트"""
        try:
            values = data.get('values', {})   
            stock_code = values.get('item')
            stock_code = stock_code[1:] if stock_code and stock_code.startswith('A') else stock_code
     
            if not stock_code:
                logger.warning("04 데이터에 종목코드(item)가 없습니다.")
                return
            
            # 중요 필드 추출

            quantity = values.get('930', '0')            # 보유수량
            avg_price = values.get('931', '0')           # 평균단가
            
            # 🔧 수정: 안전한 숫자 변환
            try:
                quantity_int = abs(int(quantity.replace(',', ''))) if quantity else 0
                avg_price_int = abs(int(avg_price.replace(',', ''))) if avg_price else 0
                
                # A 제거 (A105560 → 105560)
                stock_code = stock_code[1:] if stock_code.startswith('A') else stock_code
                
                # 보유 수량 업데이트 (self.stock_qty)
                if quantity_int > 0:
                    self.stock_qty[stock_code] = quantity_int
                    logger.info(f"📊 잔고 업데이트 - 종목: {stock_code}, 수량: {quantity_int}주, "
                              f"평균단가: {avg_price_int}원")
                else:
                    # 수량이 0이면 제거
                    if stock_code in self.stock_qty:
                        del self.stock_qty[stock_code]
                        logger.info(f"🗑️ 잔고 제거 - 종목: {stock_code} (수량 0)")
                        
            except (ValueError, AttributeError) as e:
                logger.error(f"04 데이터 숫자 변환 오류: {e}")
                logger.error(f"원본 데이터: quantity={quantity}, avg_price={avg_price}")
            
        except Exception as e:
            logger.error(f"❌ 04 타입 데이터 처리 중 오류: {str(e)}")

    async def type_callback_0B(self, data: dict):
        try:
            values = data.get('values', {})   
            stock_code = values.get('item')
            stock_code = stock_code[1:] if stock_code and stock_code.startswith('A') else stock_code
            
            if not stock_code:
                logger.warning("0B 데이터에 종목코드가 없습니다.")
                return
              

            current_price = abs(int(values.get('10', '0')))

            #PT : PriceTracker    
            if current_price > 0:       
                await self.PT.update_price(stock_code, current_price)
                IsFirst = await self.PT.isfirst(stock_code)
                if IsFirst : 
                    qty_to_buy = math.ceil((self.assigned_per_stock/current_price) / 10) * 10
                    logger.info(f"{stock_code} 첫번째 실행 -> 매수 가능주식 : {qty_to_buy}")
                    await self.PT.initialize_tracking( # 처음 값이 들어오면 qty_to_sell 계산
                                                                  stock_code = stock_code,
                                                                  current_price = 0, 
                                                                  trade_price = 0, 
                                                                  period_type = False,
                                                                  isfirst = False,
                                                                  qty_to_sell = 0,
                                                                  qty_to_buy = qty_to_buy,
                                                                  trade_type = "HOLD" )
                else : 
                    await self.PT.update_tracking_data( stock_code = stock_code, 
                                                        current_price = current_price)

        except Exception as e:
            logger.error(f"0B 데이터 처리 중 오류: {str(e)}")
            # logger.error(f"원본 데이터: {data}")  

    async def type_callback_0D(self, data: dict): pass


    # 주식 데이터에서 코드를 추출하고 시장별로 분류하는 함수 - 수정된 버전
    async def stock_codes_grouping(self, data):
        logger.info("stock_codes_grouping 실행")
        try:
            # 🔧 수정: data 유효성 검사 강화
            if not data:
                logger.warning("⚠️ stock_codes_grouping: data가 None 또는 빈 값입니다.")
                return
            
            if not isinstance(data, dict):
                logger.warning(f"⚠️ stock_codes_grouping: data가 dict가 아닙니다. 타입: {type(data)}")
                return
            
            # seq 필드 검사
            seq_value = data.get('seq')
            if seq_value is None:
                logger.warning("⚠️ stock_codes_grouping: 'seq' 필드가 없습니다.")
                return
            
            try:
                seq = int(str(seq_value).strip())
            except (ValueError, AttributeError) as e:
                logger.error(f"❌ seq 값 변환 실패: {seq_value}, 오류: {e}")
                return
            
            # data 필드 검사
            data_list = data.get('data')
            if data_list is None:
                logger.warning("⚠️ stock_codes_grouping: 'data' 필드가 None입니다.")
                return
            
            if not isinstance(data_list, list):
                logger.warning(f"⚠️ stock_codes_grouping: 'data' 필드가 list가 아닙니다. 타입: {type(data_list)}")
                return
            
            if len(data_list) == 0:
                logger.info("ℹ️ stock_codes_grouping: 조건검색 결과가 비어있습니다.")
                return
            
            logger.info(f"📊 조건검색 결과 처리 시작 - seq: {seq}, 종목 수: {len(data_list)}")
            
            # 🔧 수정: 안전한 종목코드 추출
            processed_count = 0
            error_count = 0
            
            for item in data_list:
                try:
                    if not isinstance(item, dict):
                        logger.warning(f"⚠️ 개별 아이템이 dict가 아님: {type(item)}")
                        error_count += 1
                        continue
                    
                    # 9001 필드에서 종목코드 추출
                    stock_code_raw = item.get('9001')
                    if not stock_code_raw:
                        logger.warning(f"⚠️ '9001' 필드가 없거나 빈 값: {item}")
                        error_count += 1
                        continue
                    
                    # 안전한 종목코드 추출 (A 제거)
                    try:
                        if isinstance(stock_code_raw, str) and len(stock_code_raw) > 1:
                            stock_code = stock_code_raw[1:] if stock_code_raw.startswith('A') else stock_code_raw
                        else:
                            logger.warning(f"⚠️ 잘못된 종목코드 형식: {stock_code_raw}")
                            error_count += 1
                            continue
                    except Exception as e:
                        logger.error(f"❌ 종목코드 추출 오류: {stock_code_raw}, 오류: {e}")
                        error_count += 1
                        continue
                    
                    # 종목코드 유효성 검사 (6자리 숫자인지 확인)
                    if not stock_code.isdigit() or len(stock_code) != 6:
                        logger.warning(f"⚠️ 유효하지 않은 종목코드: {stock_code}")
                        error_count += 1
                        continue
                    
                    # 시장별 분류
                    if seq in [0]:  # KOSPI
                        self.condition_list['kospi'].add(stock_code)
                        processed_count += 1
                    elif seq in [1]:  # KOSDAQ
                        self.condition_list['kosdaq'].add(stock_code)
                        processed_count += 1
                    else:
                        logger.warning(f"⚠️ 알 수 없는 seq 값: {seq}")
                        error_count += 1
                        
                except Exception as e:
                    logger.error(f"❌ 개별 아이템 처리 오류: {item}, 오류: {str(e)}")
                    error_count += 1
                    continue
            
            # 🔧 수정: 안전한 리스트 변환
            try:
                kosdaq_list = list(self.condition_list['kosdaq']) if self.condition_list['kosdaq'] else []
                kospi_list = list(self.condition_list['kospi']) if self.condition_list['kospi'] else []
            except Exception as e:
                logger.error(f"❌ 조건검색 리스트 변환 오류: {e}")
                kosdaq_list = []
                kospi_list = []
            
            logger.info(f"📈 KOSPI 종목 수: {len(kospi_list)}")
            logger.info(f"📊 KOSDAQ 종목 수: {len(kosdaq_list)}")
            logger.info(f"✅ 처리 완료 - 성공: {processed_count}개, 실패: {error_count}개")
            

            # 🔧 수정: 실시간 그룹 추가 시 안전성 강화
            # KOSPI 그룹 처리
            if kospi_list:
                logger.info(f"🔄 KOSPI 그룹에 {len(kospi_list)}개 종목 추가 시작")
                kospi_success = 0
                kospi_errors = 0
                
                for stock in kospi_list:
                    try:
                        if not hasattr(self, 'realtime_group_module') or self.realtime_group_module is None:
                            logger.error("❌ realtime_group_module이 초기화되지 않음")
                            break
                            
                        result = await self.realtime_group_module.add_stock_to_group(0, stock)
                        if result:
                            kospi_success += 1
                            logger.debug(f"✅ KOSPI 종목 추가: {stock}")
                        else:
                            kospi_errors += 1
                            logger.warning(f"⚠️ KOSPI 그룹(0)이 존재하지 않음. 종목: {stock}")
                            
                    except Exception as e:
                        kospi_errors += 1
                        logger.error(f"❌ KOSPI 종목 추가 실패: {stock}, 오류: {str(e)}")
                
                logger.info(f"📈 KOSPI 그룹 처리 완료 - 성공: {kospi_success}개, 실패: {kospi_errors}개")
            
            # KOSDAQ 그룹 처리  
            if kosdaq_list:
                logger.info(f"🔄 KOSDAQ 그룹에 {len(kosdaq_list)}개 종목 추가 시작")
                kosdaq_success = 0
                kosdaq_errors = 0
                
                for stock in kosdaq_list:
                    try:
                        if not hasattr(self, 'realtime_group_module') or self.realtime_group_module is None:
                            logger.error("❌ realtime_group_module이 초기화되지 않음")
                            break
                            
                        result = await self.realtime_group_module.add_stock_to_group(1, stock)
                        if result:
                            kosdaq_success += 1
                            logger.debug(f"✅ KOSDAQ 종목 추가: {stock}")
                        else:
                            kosdaq_errors += 1
                            logger.warning(f"⚠️ KOSDAQ 그룹(1)이 존재하지 않음. 종목: {stock}")
                            
                    except Exception as e:
                        kosdaq_errors += 1
                        logger.error(f"❌ KOSDAQ 종목 추가 실패: {stock}, 오류: {str(e)}")
                
                logger.info(f"📊 KOSDAQ 그룹 처리 완료 - 성공: {kosdaq_success}개, 실패: {kosdaq_errors}개")
            
            # 최종 요약
            total_added = (kospi_success if 'kospi_success' in locals() else 0) + (kosdaq_success if 'kosdaq_success' in locals() else 0)
            total_errors = (kospi_errors if 'kospi_errors' in locals() else 0) + (kosdaq_errors if 'kosdaq_errors' in locals() else 0)
            
            logger.info(f"🎯 stock_codes_grouping 최종 완료 - 총 추가: {total_added}개, 총 실패: {total_errors}개")
                        
        except Exception as e:
            logger.error(f"❌ stock_codes_grouping 처리 중 전체 오류: {str(e)}")
            logger.error(f"입력 데이터 타입: {type(data)}")
            logger.error(f"입력 데이터 내용: {data if data else 'None'}")
            # 🔧 추가: 스택 트레이스 로깅
            import traceback
            logger.error(f"스택 트레이스: {traceback.format_exc()}")

    # 🆕 수정된 short_trading_handler - 거래 태스크 생성
    async def short_trading_handler(self) : # 조건검색 으로 코드 등록 
        try:
            isfirst = await self.isfirst_start() # 오늘 첫번째 실행인지 확인   
            isfirst = 1 # 오늘 첫번째 실행인지 확인   
            if isfirst :
                logger.info("isfirst 실행")
                await self.realtime_group_module.delete_by_group(0)
                await self.realtime_group_module.delete_by_group(1)
                await self.realtime_group_module.create_new(group=0, data_type=[], stock_code=[])
                await self.realtime_group_module.create_new(group=1, data_type=[], stock_code=[])
                # 조건 검색 요청 => 자동으로 realtime_group 에 추가됨
                await self.realtime_module.get_condition_list()
                await asyncio.sleep(0.3)
                await self.realtime_module.request_condition_search(seq="0")
                await asyncio.sleep(0.3)
                await self.realtime_module.request_condition_search(seq="1")
                await asyncio.sleep(0.3)
            
            # 조건 검색으로 만들어진 그룹   
            res = await self.realtime_group_module.get_all_groups()  
            
            condition_stock_codes = [code for group in res for code in group.stock_code]
            all_stock_codes = list(set(condition_stock_codes + self.holding_stock)) 
            
            await self.realtime_module.subscribe_realtime_price(group_no="0", 
                        items=all_stock_codes, 
                        data_types=["00","0B","04"], 
                        refresh=True)

            
            stock_qty = len(all_stock_codes)
            stock_qty =  stock_qty if stock_qty >= 1 else 50 
            self.assigned_per_stock = int(self.deposit / stock_qty)
            
            # 🆕 조건검색 종목들에 대해 거래 태스크 생성
            tasks = []
            for code in condition_stock_codes:
                try:
                    # 트래킹 초기화
                    await self.PT.initialize_tracking( 
                        stock_code = code, 
                        current_price = 0,
                        trade_price = 0, 
                        period_type = False,
                        isfirst = True,
                        qty_to_sell = 0,
                        qty_to_buy = 0,
                        trade_type = "HOLD" 
                    )
                    
                    # 🎯 trader_executor 백그라운드 task 등록
                    task = asyncio.create_task(self.trader_executor(code))
                    tasks.append(task)
                    logger.info(f"🚀 [{code}] 거래 태스크 생성")

                except Exception as e:
                    logger.error(f"❌ 종목 {code} 초기화 오류: {str(e)}")

            # 🆕 생성된 태스크들을 클래스 변수에 저장 (shutdown에서 정리하기 위해)
            self.trading_tasks = tasks
            
            logger.info(f"🎯 조건검색 완료: {len(condition_stock_codes)}개 종목, {len(tasks)}개 거래 태스크 생성")
            logger.info(f"💰 종목당 할당 금액: {self.assigned_per_stock:,}원")

        except Exception as e:
            logger.error(f"❌ short_trading_handler 메서드 전체 오류: {str(e)}")
            raise
    
    def safe_int_convert(self, value, default=0):
        """문자열을 안전하게 정수로 변환"""
        try:
            if value is None:
                return default
            
            if isinstance(value, (int, float)):
                return int(value)
            
            if isinstance(value, str):
                cleaned = value.strip()
                if not cleaned or cleaned == '':
                    return default
                
                # 숫자가 아닌 문자가 포함된 경우 체크
                if not all(c.isdigit() or c in '.-+' for c in cleaned.replace(',', '')):
                    logging.warning(f"숫자가 아닌 문자 포함: '{value}'")
                    return default
                
                try:
                    # 콤마 제거 후 float으로 먼저 변환 후 int로 변환
                    return int(float(cleaned.replace(',', '')))
                except ValueError:
                    logging.warning(f"숫자 변환 불가: '{value}'")
                    return default
            
            else:
                logging.warning(f"지원하지 않는 타입: {type(value)} - {value}")
                return default
                
        except Exception as e:
            logging.warning(f"숫자 변환 중 예외 발생: {value}, 오류: {e}")
            return default
                  

    # 자동 취소 체크 메서드들 (개선된 버전)
    async def auto_cancel_checker(self):
        """10초마다 미체결 주문 체크하여 자동 취소"""
        logging.info("🔄 자동 주문 취사 체크 시작")
        
        while self.running:
            try:
                await self.check_and_cancel_old_orders()
                # 10초마다 체크
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                logging.info("자동 취소 체크 태스크가 취소되었습니다.")
                break
            except Exception as e:
                logging.error(f"자동 취소 체크 중 오류: {str(e)}")
                await asyncio.sleep(10)

    async def check_and_cancel_old_orders(self):
        """10분 이상 미체결 주문 찾아서 취소 - socket_module Redis 데이터 사용"""
        try:
            current_time = time.time()
            ten_minutes_ago  = current_time - 60 * 10  # 10분 = 600초
            
            # socket_module에서 저장한 type_code='00' 데이터 조회
            pattern = "redis:00:*"
            keys = await self.redis_db.keys(pattern)
            
            if not keys:
                logging.debug("주문 데이터 키가 없습니다.")
                return
            
            cancel_targets = []
            completed_orders = []
            
            # 각 종목별 주문 데이터 처리
            for key in keys:
                try:
                    # sorted set에서 모든 데이터 조회 (어차피 10분치만 있음)
                    raw_data_list = await self.redis_db.zrangebyscore(
                        key, 
                        min = ten_minutes_ago ,   # 10분전 부터
                        max = current_time,       # 현재까지
                        withscores=True
                    )
                    
                    if not raw_data_list:
                        continue
                    
                    # 주문번호별로 최신 데이터만 유지 (중복 제거)
                    order_latest_data = {}
                    
                    for data_str, timestamp in raw_data_list:
                        try:
                            order_data = json.loads(data_str)
                            
                            # type이 '00'인지 확인 (주문체결 데이터)
                            if order_data.get('type') != '00':
                                continue
                            
                            order_number = str(order_data.get('9203', '0'))
                            if not order_number or order_number == '0':
                                continue
                            
                            # 같은 주문번호의 최신 데이터만 유지
                            if (order_number not in order_latest_data or 
                                timestamp > order_latest_data[order_number]['timestamp']):
                                order_latest_data[order_number] = {
                                    'data': order_data,
                                    'data_str': data_str,
                                    'timestamp': timestamp,
                                    'key': key
                                }
                                
                        except json.JSONDecodeError as e:
                            logging.error(f"JSON 파싱 오류: {e}, 데이터: {data_str}")
                            # 파싱 불가능한 데이터는 sorted set에서 제거
                            await self.redis_db.zrem(key, data_str)
                            continue
                    
                    # 최신 데이터들에 대해 취소/완료 판단
                    for order_number, order_info in order_latest_data.items():
                        order_data = order_info['data']
                        data_str = order_info['data_str']
                        order_timestamp = order_info['timestamp']
                        
                        # 안전한 데이터 추출
                        order_qty = self.safe_int_convert(order_data.get('900', '0'), 0)
                        trade_qty = self.safe_int_convert(order_data.get('911', '0'), 0)
                        untrade_qty = self.safe_int_convert(order_data.get('902', '0'), 0)
                        order_status = str(order_data.get('905', '')).strip()
                        order_state = str(order_data.get('913', '')).strip()
                        
                        # 1. 주문 완료 체크 (전량 체결)
                        if (order_qty > 0 and trade_qty > 0 and 
                            order_qty == trade_qty and untrade_qty == 0):
                            
                            completed_orders.append({
                                'key': key,
                                'data_str': data_str,
                                'order_number': order_number,
                                'order_data': order_data,
                                'reason': '체결완료'
                            })
                            continue
                        
                        # 2. 이미 취소/거부된 주문 체크
                        if ('취소' in order_status or '취소' in order_state or 
                            '거부' in order_status or '거부' in order_state):
                            
                            completed_orders.append({
                                'key': key,
                                'data_str': data_str,
                                'order_number': order_number,
                                'order_data': order_data,
                                'reason': '취소/거부'
                            })
                            continue
                        
                        # 3. 10분 이상 미체결 주문 체크
                        # 주의: Redis에는 최대 10분치 데이터만 있으므로, 
                        # 10분 이상된 주문은 이미 Redis에서 자동 삭제됨
                        # 따라서 여기서는 5분 이상 미체결 주문을 취소 대상으로 설정
                        five_minutes_ago = current_time - 300  # 5분
                        
                        if (order_timestamp <= five_minutes_ago and 
                            untrade_qty > 0 and 
                            '취소' not in order_status and 
                            '취소' not in order_state and
                            '거부' not in order_status and 
                            '거부' not in order_state):
                            
                            cancel_targets.append({
                                'key': key,
                                'data_str': data_str,
                                'order_data': order_data,
                                'timestamp': order_timestamp,
                                'age_minutes': (current_time - order_timestamp) / 60
                            })
                            
                except Exception as e:
                    logging.error(f"주문 데이터 처리 오류 ({key}): {e}")
                    continue
            
            # 완료된 주문들 정리 (Redis에서 제거)
            if completed_orders:
                logging.info(f"🧹 완료된 주문 {len(completed_orders)}건 정리")
                
                for completed in completed_orders:
                    try:
                        # sorted set에서 해당 데이터 제거
                        removed_count = await self.redis_db.zrem(completed['key'], completed['data_str'])
                        if removed_count > 0:
                            reason = completed.get('reason', '체결완료')
                            logging.info(f"✅ 주문 정리: {completed['order_number']} ({reason})")
                        else:
                            logging.warning(f"⚠️ 주문 데이터 제거 실패: {completed['order_number']}")
                            
                    except Exception as e:
                        logging.error(f"주문 데이터 제거 중 오류: {e}")
            
            # 취소 대상 주문들 처리
            if cancel_targets:
                logging.info(f"🚨 5분 이상 미체결 주문 {len(cancel_targets)}건 발견, 자동 취소 시작")
                
                for target in cancel_targets:
                    await self.cancel_old_order(target)
            else:
                logging.debug("자동 취소 대상 주문 없음")
                
        except Exception as e:
            logging.error(f"미체결 주문 체크 중 오류: {str(e)}")
            import traceback
            logging.error(f"상세 오류 정보: {traceback.format_exc()}")

    async def cancel_old_order(self, target):
        """미체결 주문 취소 실행"""
        try:
            order_data = target['order_data']
            key = target['key']
            data_str = target['data_str']
            age_minutes = target.get('age_minutes', 0)
            
            order_number = order_data.get('9203', '')
            stock_code = order_data.get('9001', '')
            stock_name = order_data.get('302', '')
            untrade_qty = order_data.get('902', '0')
            order_price = order_data.get('901', '0')
            
            # A 접두사 제거 (A005930 -> 005930)
            clean_stock_code = stock_code[1:] if stock_code.startswith('A') else stock_code
            
            logging.warning(f"🔴 미체결 주문 자동 취소 시도: {stock_name}({clean_stock_code}) "
                          f"주문번호:{order_number} 미체결:{untrade_qty}주 "
                          f"경과시간:{age_minutes:.1f}분")
            
            # KiwoomModule 유효성 검사
            if not hasattr(self.kiwoom_module, 'order_stock_cancel'):
                logging.error("KiwoomModule에 order_stock_cancel 메서드가 없습니다.")
                # 취소 불가능한 주문은 Redis에서 제거
                await self.redis_db.zrem(key, data_str)
                logging.warning(f"🗑️ 취소 불가능한 주문 Redis에서 제거: {order_number}")
                return
            
            # 실제 취소 주문 API 호출 
            try:
                result = await self.kiwoom_module.order_stock_cancel(            		
                    dmst_stex_tp='KRX',         # 국내거래소구분
                    orig_ord_no=order_number,   # 원주문번호 
                    stk_cd=clean_stock_code,    # 종목코드 (A 제거된 버전)
                    cncl_qty='0'               # 전량취소
                )
                
                if result:
                    logging.info(f"✅ 주문 취소 API 호출 성공: {order_number}")
                else:
                    logging.warning(f"⚠️ 주문 취소 API 결과 불명: {order_number}")
                    
            except Exception as api_error:
                logging.error(f"❌ 주문 취소 API 호출 실패: {order_number}, 오류: {api_error}")
            
            # API 호출 결과와 관계없이 Redis에서 제거 (무한 반복 방지)
            try:
                removed_count = await self.redis_db.zrem(key, data_str)
                if removed_count > 0:
                    logging.info(f"🗑️ Redis에서 취소 주문 데이터 제거: {order_number}")
                else:
                    logging.warning(f"⚠️ Redis에서 데이터 제거 실패 (이미 없음): {order_number}")
                    
            except Exception as redis_error:
                logging.error(f"❌ Redis 데이터 제거 중 오류: {redis_error}")
            
        except Exception as e:
            logging.error(f"주문 취소 처리 중 전체 오류: {str(e)}")
            logging.error(f"대상 주문 데이터: {target.get('order_data', {})}")
            
            # 예외 발생한 경우에도 Redis에서 제거 (무한 반복 방지)
            try:
                await self.redis_db.zrem(target['key'], target['data_str'])
                logging.warning(f"🗑️ 예외 발생으로 Redis에서 제거: {target['order_data'].get('9203', 'unknown')}")
            except Exception as cleanup_error:
                logging.error(f"❌ Redis 정리 중 오류: {cleanup_error}")

    # 주식 데이터에서 주식코드만 추출하는 함수
    async def extract_stock_codes(self) -> List[str]:
        data = await self.kiwoom_module.get_account_info()
        
        # 입력 데이터가 문자열인 경우 JSON으로 파싱
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                print("잘못된 JSON 형식입니다.")
                return []
        
        # acnt_evlt_remn_indv_tot 배열에서 stk_cd 추출
        if 'acnt_evlt_remn_indv_tot' in data and isinstance(data['acnt_evlt_remn_indv_tot'], list):
            return [item.get('stk_cd', '')[1:] for item in data['acnt_evlt_remn_indv_tot'] if 'stk_cd' in item]
        
        return []
  
    # 오늘 날짜를 확인하여 첫 번째 접근인지 체크하고 상태를 업데이트합니다.
    async def isfirst_start(self) -> bool:
        today = date.today()
        
        async with self.postgres_db.get_session() as session:
            statement = select(IsFirst).where(IsFirst.check_date == today)
            result = await session.exec(statement)
            existing_record = result.first()
            
            if existing_record is None:
                new_record = IsFirst(check_date=today, is_first=False)
                session.add(new_record)
                await session.commit()
                return True
            else:
                if existing_record.is_first:
                    existing_record.is_first = False
                    await session.commit()
                    return True
                else:
                    return False