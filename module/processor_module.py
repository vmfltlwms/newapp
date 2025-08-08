# module.processor_module.py - 수정된 버전
import math
import os
from data.stock_code import KOSPI 
from data.holiday import holidays
from datetime import date, datetime, timedelta, time as datetime_time
from zoneinfo import ZoneInfo
import json
import time
from typing import Dict, List, Union
from dependency_injector.wiring import inject, Provide
import asyncio, json, logging 
from sqlmodel import select
import pytz
from container.redis_container import Redis_Container
from container.socket_container import Socket_Container
from container.kiwoom_container import Kiwoom_Container
from container.realtime_container import RealTime_Container
from db.redis_db import RedisDB
from module.socket_module import SocketModule
from module.kiwoom_module import KiwoomModule  
from module.realtime_module import RealtimeModule
from redis_util.price_tracker_service import PriceTracker
from utils.long_trading import LongTradingAnalyzer

logger = logging.getLogger(__name__)
log_path = f"logs/new_trading_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
os.makedirs(os.path.dirname(log_path), exist_ok=True)

file_handler = logging.FileHandler(log_path, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

class ProcessorModule:
    @inject
    def __init__(self, 
                redis_db: RedisDB = Provide[Redis_Container.redis_db],
                socket_module: SocketModule = Provide[Socket_Container.socket_module],
                kiwoom_module: KiwoomModule = Provide[Kiwoom_Container.kiwoom_module],
                realtime_module:RealtimeModule = Provide[RealTime_Container.realtime_module]):
        self.redis_db = redis_db.get_connection()
        self.socket_module = socket_module
        self.kiwoom_module = kiwoom_module
        self.realtime_module = realtime_module
        self.running = False
        self.count = 0 
        self.cancel_check_task = None 
        self.condition_list ={'kospi':set(),'kosdaq':set()} #조건검색 리스트
        
        # 🆕 거래 태스크 관리
        self.trading_tasks = []  # 개별 종목 거래 태스크들
        self.timezone = ZoneInfo("Asia/Seoul")
        self.ping_counter = 0
        
        self.kospi_index  = 0 
        self.kosdaq_index = 0
        self.kospi_group  = [] 
        self.kosdaq_group = []   
        self.long_trade_code = []        # 장기거래 주식코드 리스트
        self.long_trade_data = {}        # 장기거래 주식코드 데이터
        self.holding_stock =[]           # 현재 보유중인 주식
        self.account_info ={}            # 현재 보유중인 주식 / 처음 실행할 때 매도 수량 관리용
        self.stock_qty = {}              # 현재 주식별 보유 수량 관리
        self.deposit = 0                 # 예수금
        self.assigned_per_stock = 0      # 각 주식별 거래가능 금액
        self.account = []                # 내 주식 소유현황
        self.trade_done = []
        self.trade_group = []
        self.order_tracker ={}
        self.order_execution_tracker = {}  # 새로운 추적용
        
        self.PT = PriceTracker(self.redis_db)
        self.LTH = LongTradingAnalyzer(self.kiwoom_module)
        
        self.daily_flags = {
            'long_trading': None,
            'condition_search': None,
            'morning_setup': None,
            'afternoon_setup': None,
            'system_check': None
        }
        
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
          '0J': self.type_callback_0J,
        }
        


        
    async def initialize(self) : # 현재 보유주식별 주식수, 예수금, 주문 취소 확인 및 실행

        try:
            # running을 True로 설정한 후 태스크 시작
            self.running = True
            self.holding_stock = await self.extract_stock_codes() # 현재 보유중인 주식
        
            # 주식코드, 보유수량, 평균 매매가격 추출(stock_code, stock_qty, avg_price)
            account_info = await self.kiwoom_module.get_account_info()
            self.account_info = self.extract_holding_stocks_info(account_info)

            # 예수금 정보 조회
            try:
                self.deposit = await self.clean_deposit()
            except Exception as e:
                self.deposit = 0
                
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
    def track_order_execution(self, stock_code, order_qty, trade_qty, untrade_qty):
        """주문 체결 추적 및 증분 체결량 계산"""
        try:
            # order_execution_tracker 딕셔너리 사용 (기존 order_tracker와 구분)
            if not hasattr(self, 'order_execution_tracker'):
                self.order_execution_tracker = {}
            
            # 이전 누적 체결량 조회
            if stock_code in self.order_execution_tracker:
                prev_total_qty = int(self.order_execution_tracker[stock_code].get("trade_qty", 0))
            else:
                prev_total_qty = 0

            # 현재 체결량 (누적값)
            current_total_qty = int(trade_qty) if trade_qty else 0
            
            # 주문 정보 업데이트
            self.order_execution_tracker[stock_code] = {
                'order_qty': int(order_qty),
                'trade_qty': current_total_qty,  # 누적 체결량
                'untrade_qty': int(untrade_qty)
            }

            # 전량 체결되었으면 삭제
            if current_total_qty >= int(order_qty) and int(untrade_qty) == 0:
                logger.info(f"{stock_code}에 대한 주문이 완료되었습니다")
                del self.order_execution_tracker[stock_code]

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
        self.ping_counter +=1
        if self.ping_counter // 20 == 1:
            self.ping_counter = 0
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
        
        # 🔧 수정: 배열의 모든 요소를 순회하여 처리
        for index, item in enumerate(data):
            try:
                if not isinstance(item, dict):
                    logging.warning(f"잘못된 데이터 타입 (인덱스 {index}): {type(item)}")
                    continue
                    
                request_type = item.get('type')
                request_item = item.get('item')
                request_name = item.get('name')
                
                # 🆕 00 타입만 집중적으로 디버깅

                # 해당 타입의 핸들러 찾기
                handler = self.type_callback_table.get(request_type)
                
                if handler:
                    await handler(item)

                else:
                    print(f"❌ 알 수 없는 실시간 타입: {request_type}")
                    logging.warning(f"알 수 없는 실시간 타입 수신: {request_type} (인덱스: {index})")
                    
            except Exception as e:
                print(f"❌ 개별 데이터 처리 오류 (인덱스 {index}): {str(e)}")
                logging.error(f"개별 데이터 처리 중 오류 (인덱스 {index}): {str(e)}")
                logging.error(f"문제 데이터: {item}")
                continue
              
    async def type_callback_00(self, data: dict): 
        try:
            # 🆕 함수 시작 로그 (00 타입만)
            
            values = data.get('values', {})   
            stock_code = data.get('item')
            stock_code = stock_code[1:] if stock_code and stock_code.startswith('A') else stock_code

            if not stock_code:
                return
            
            # 🆕 주요 데이터 추출 로그
            order_number = values.get('9203', '0')
            order_status = values.get('905', '')
            order_state = values.get('913', '')
            
            logging.info(f"📋 [00타입] 주문체결 데이터 수신 - 종목: {stock_code}, 주문번호: {order_number}, 상태: {order_status}, 구분: {order_state}")
 
            
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
                logging.warning(f"[00타입] 유효하지 않은 주문번호: {order_number}")
                return
                        
            # 증분 체결량 계산
            incremental_trade_qty = self.track_order_execution(stock_code, order_qty, trade_qty, untrade_qty)
            # 🆕 주요 변수 로그
            logging.info(
                f"\n📊 [주문 체결 정보] ───────────────────────────────\n"
                f"📌 종목코드     : {stock_code}\n"
                f"🆔 주문번호     : {order_number}\n"
                f"📦 주문량       : {order_qty:,}주\n"
                f"🔄 증분체결량   : {incremental_trade_qty:,}주\n"
                f"✅ 총체결량     : {trade_qty:,}주\n"
                f"⏳ 미체결량     : {untrade_qty:,}주\n"
                f"💰 체결가격     : {execution_price:,}원\n"
                f"─────────────────────────────────────────────────"
            )
            
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
                logging.info(f"💰 예수금 변화: {self.deposit:,} → {prev_deposit:,}")
                
                # 이 부분 로직 설명()
                if stock_code in self.trade_done : self.trade_done.remove(str(stock_code))
                else :  self.holding_stock.append(str(stock_code))
            
            # 2. 실제 체결된 경우만 수량 업데이트
            elif incremental_trade_qty > 0 and execution_price > 0:
                # 추적 데이터 조회 (안전한 처리)
                tracking_data = await self.PT.get_price_info(stock_code)
                
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
                    if (untrade_qty == 0 and trade_qty == order_qty) :
                        completion_status = "완료"
                        # if stock_code not in self.holding_stock :
                        #     self.holding_stock.append(str(stock_code)) 
 
                    else : completion_status = "부분 체결"
                    
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
                    if (untrade_qty == 0 and trade_qty == order_qty) :
                        completion_status = "완료"
                        if stock_code in self.holding_stock:
                            self.holding_stock.remove(str(stock_code))
                    else : completion_status = "부분 체결"
                    
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
        logger.info("data")
                
    # 보유주식 수량 업데이트
    async def type_callback_04(self, data: dict):
        """현물잔고 데이터 처리 - 최신 데이터로 업데이트"""
        try:
            values = data.get('values', {})   
            stock_code = data.get('item')
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
                
                # 보유 수량 업데이트 (self.stock_qty)  * tracker update
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

    async def type_callback_0D(self, data: dict): pass
    
    async def type_callback_0J(self, data: dict):
        try:
            values = data.get('values', {})
            item_code = data.get('item', '')
            
            # 등락률 데이터 (12번 필드)
            change_rate = round(float(values.get('12', '0')),2)
            
            # 🔧 수정: KOSPI 지수 (001)
            if item_code == '001' and self.kospi_index != change_rate:
                self.kospi_index = change_rate
                # logger.info(f"📈 KOSPI 지수 업데이트: 등락률 {change_rate}%")  
            
            # 🔧 수정: KOSDAQ 지수 (101)
            elif item_code == '101' and self.kosdaq_index != change_rate:
                self.kosdaq_index = change_rate
                # logger.info(f"📊 KOSDAQ 지수 업데이트: 등락률 {change_rate}%") 

                
        except Exception as e:
            logger.error(f"❌ 업종지수 실시간 데이터 처리 중 오류: {str(e)}")
            logger.error(f"수신 데이터: {data}")
            
    # =================================================================
    # 메인 처리 로직
    # =================================================================

    async def type_callback_0B(self, data: dict):
        """통합된 실시간 데이터 처리 - 시간대별 전략 실행"""
        try:
            # 🔥 1. 시간 및 날짜 정보
            kst = pytz.timezone('Asia/Seoul')
            now = datetime.now(kst)
            now_time = now.time()
            today = now.date()
            
            # 🔥 2. 공통 데이터 추출
            values = data.get('values', {})   
            stock_code = data.get('item')
            stock_code = stock_code[1:] if stock_code and stock_code.startswith('A') else stock_code

            if not stock_code:
                logger.warning("0B 데이터에 종목코드가 없습니다.")
                return

            # 공통 시장 데이터 추출
            market_data = {
                'stock_code': stock_code,
                'current_price': abs(int(values.get('10', '0'))),
                'open_price': abs(int(values.get('16', '0'))),
                'high_price': abs(int(values.get('17', '0'))),
                'low_price': abs(int(values.get('18', '0'))),
                'execution_strength': float(values.get('228', '0')),
                'timestamp': time.time()
            }

            # 🔥 3. 시간대별 전략 분기
            current_state = self.determine_trading_state(now_time)
            
            # 상태별 전략 실행
            if current_state == "OBSERVATION":       # 09:00-09:30
                await self.observation_strategy(market_data)
            elif current_state == "ACTIVE_TRADING":  # 09:30-12:00  
                await self.active_trading_strategy(market_data)
            elif current_state == "CONSERVATIVE":    # 12:00-15:30
                await self.conservative_trading_strategy(market_data)
            else:
                # 거래시간 외에는 로그만 (필요시)
                logger.debug(f"거래시간 외 데이터 수신: {stock_code} - {market_data['current_price']:,}원")
                
        except Exception as e:
            logger.error(f"❌ type_callback_0B 처리 중 오류: {str(e)}")
            import traceback
            logger.error(f"상세 스택 트레이스: {traceback.format_exc()}")

    def determine_trading_state(self, now_time):
        """현재 시간에 맞는 거래 상태 결정"""
        time_0900 = datetime_time(9, 0)
        time_0930 = datetime_time(9, 30)
        time_1200 = datetime_time(12, 0)
        time_1530 = datetime_time(15, 30)
        
        if time_0900 <= now_time < time_0930:
            return "OBSERVATION"      # 관망 시간
        elif time_0930 <= now_time < time_1200:
            return "ACTIVE_TRADING"   # 적극 매매
        elif time_1200 <= now_time < time_1530:
            return "CONSERVATIVE"     # 보수적 매매
        else:
            return "INACTIVE"         # 거래시간 외

    # 🔥 1. 시간대별 전략 메서드 틀 (다음 단계에서 구현)
    async def observation_strategy(self, market_data):
        """09:00-09:30 관망 전략"""
        stock_code = market_data['stock_code']
        current_price = market_data['current_price']
        
        logger.debug(f"👀 [관망시간] {stock_code} - 현재가: {current_price:,}원, 코스피: {self.kospi_index}%")
        
        # 보유주식에 대한 기본 익절/손절만 실행
        if stock_code in self.holding_stock:
            await self.basic_sell_logic(stock_code, market_data)

    async def active_trading_strategy(self, market_data):
        """09:30-12:00 적극 매매 전략"""
        stock_code = market_data['stock_code']
        
        logger.debug(f"🚀 [적극매매] {stock_code} - 코스피: {self.kospi_index}%")
        
        if stock_code in self.holding_stock:
            await self.active_sell_logic(stock_code, market_data)
        else:
            await self.active_buy_logic(stock_code, market_data)

    async def conservative_trading_strategy(self, market_data):
        """12:00-15:30 보수적 매매 전략"""
        stock_code = market_data['stock_code']
        
        logger.debug(f"🛡️ [보수매매] {stock_code} - 코스피: {self.kospi_index}%")
        
        if stock_code in self.holding_stock:
            await self.conservative_sell_logic(stock_code, market_data)
        else:
            await self.conservative_buy_logic(stock_code, market_data)
    
    # 🔥 매수가 계산 함수
    def calculate_unified_buy_price(self, market_data, tracker_buy_price=0):
        """통합 매수가 계산 - 단순화된 버전"""
        
        current_price = market_data['current_price']
        open_price = market_data['open_price']
        kospi_index = self.kospi_index
        
        # 1단계: 코스피 지수로 기본 할인율 결정
        if kospi_index >= 1.5:
            base_discount = 0.015      # 강세장: 1.5% 할인
        elif kospi_index <= -1.5:
            base_discount = 0.025      # 약세장: 2.5% 할인  
        else:
            base_discount = 0.02       # 보통장: 2.0% 할인
        
        # 2단계: 현재가/시가 비교로 추가 할인 계산
        if open_price > 0:
            price_change_rate = (current_price - open_price) / open_price
            
            if price_change_rate > 0.01:        # +1% 이상 상승
                additional_discount = 0.005     # 0.5% 추가 할인
            elif price_change_rate < -0.01:     # -1% 이상 하락  
                additional_discount = -0.005    # 0.5% 할인 줄임 (더 적극적)
            else:
                additional_discount = 0         # 변화 없음
        else:
            additional_discount = 0
        
        # 3단계: 최종 매수가 계산
        total_discount = base_discount + additional_discount
        reference_price = min(current_price, open_price) if open_price > 0 else current_price
        calculated_price = int(reference_price * (1 - total_discount))
        
        # 4단계: tracker_buy_price와 비교해서 더 안전한 가격 선택
        if tracker_buy_price > 0:
            final_buy_price = min(calculated_price, tracker_buy_price)  # 이 부분 수정
        else:
            final_buy_price = calculated_price
        
        logger.debug(f"💰 매수가 계산: 기준가 {reference_price:,}원 × (1-{total_discount:.3f}) = {calculated_price:,}원 "
                    f"→ 최종: {final_buy_price:,}원")
        
        return final_buy_price

    def should_sell_for_profit(self, stock_code, current_price, trade_price, high_price, kospi_index=None, time_period="NORMAL"):
        """익절 조건 판단"""
        
        if trade_price <= 0:
            return False, "매수가 정보 없음"
        
        # 수익률 계산
        profit_rate = (current_price - trade_price) / trade_price
        
        # 시간대와 종목 타입에 따른 익절 기준 설정
        is_long_term = stock_code in getattr(self, 'long_trade_code', [])
        
        if time_period == "OBSERVATION":  # 09:00-09:30
            target_profit = 0.03 if is_long_term else 0.02
        elif time_period == "ACTIVE_TRADING":  # 09:30-12:00
            if kospi_index is not None and kospi_index >= -1.5:
                target_profit = 0.03  # 코스피 -1.5% 이상일 때
            else:
                target_profit = 0.02  # 코스피 -1.5% 이하일 때
        else:  # CONSERVATIVE (12:00-15:30)
            target_profit = 0.02  # 고정 2%
        
        # 수익률 조건 확인
        if profit_rate < target_profit:
            return False, f"수익률 부족: {profit_rate:.2%} < {target_profit:.2%}"
        
        # 반전 조건 확인: 고점 대비 0.5% 이상 하락
        if high_price > 0:
            high_decline_rate = (high_price - current_price) / high_price
            if high_decline_rate < 0.005:  # 0.5%
                return False, f"반전 신호 부족: 고점 대비 {high_decline_rate:.2%} 하락"
        
        return True, f"익절 조건 만족: 수익률 {profit_rate:.2%}, 고점 대비 {high_decline_rate:.2%} 하락"

    def should_sell_for_loss(self, stock_code, current_price, trade_price):
        """손절 조건 판단"""
        
        if trade_price <= 0:
            return False, "매수가 정보 없음"
        
        # 손실률 계산
        loss_rate = (current_price - trade_price) / trade_price
        
        # 종목 타입에 따른 손절 기준 설정
        is_long_term = stock_code in getattr(self, 'long_trade_code', [])
        target_loss = -0.10 if is_long_term else -0.05  # 장기: -10%, 일반: -5%
        
        if loss_rate <= target_loss:
            return True, f"손절 조건: {loss_rate:.2%} <= {target_loss:.2%}"
        
        return False, f"손절 기준 미달: {loss_rate:.2%} > {target_loss:.2%}"

    # 🔥 매도 로직들
    async def basic_sell_logic(self, stock_code, market_data):
        """기본 매도 로직 - 관망시간용"""
        current_price = market_data['current_price']
        high_price = market_data['high_price']
        
        try:
            # 추적 데이터 조회
            if not self.PT:
                logger.error("PriceTracker가 초기화되지 않음")
                return
                
            tracking_data = await self.PT.get_price_info(stock_code)
            if not tracking_data:
                logger.warning(f"⚠️ {stock_code} 추적 데이터 없음")
                return
            
            trade_price = tracking_data.get('trade_price', 0)
            qty_to_sell = tracking_data.get('qty_to_sell', 0)
            
            if trade_price <= 0 or qty_to_sell <= 0:
                logger.warning(f"⚠️ {stock_code} 매도 불가 - 매수가: {trade_price}, 수량: {qty_to_sell}")
                return
            
            # 익절 조건 확인
            should_profit_sell, profit_reason = self.should_sell_for_profit(
                stock_code, current_price, trade_price, high_price, 
                kospi_index=self.kospi_index, time_period="OBSERVATION"
            )
            
            if should_profit_sell:
                logger.info(f"🎯 [관망-익절] {stock_code} 매도 시작 - {profit_reason}")
                await self.execute_sell_order(stock_code, qty_to_sell, "익절매도")
                return
            
            # 손절 조건 확인  
            should_loss_sell, loss_reason = self.should_sell_for_loss(stock_code, current_price, trade_price)
            
            if should_loss_sell:
                logger.warning(f"🛑 [관망-손절] {stock_code} 매도 시작 - {loss_reason}")
                await self.execute_sell_order(stock_code, qty_to_sell, "손절매도")
                return
                
        except Exception as e:
            logger.error(f"❌ {stock_code} 기본 매도 로직 오류: {str(e)}")

    async def active_sell_logic(self, stock_code, market_data):
        """적극 매매 시간대 매도 로직"""
        current_price = market_data['current_price']
        high_price = market_data['high_price']
        
        try:
            if not self.PT:
                return
                
            tracking_data = await self.PT.get_price_info(stock_code)
            if not tracking_data:
                logger.warning(f"⚠️ {stock_code} 추적 데이터 없음")
                return
            
            trade_price = tracking_data.get('trade_price', 0)
            qty_to_sell = tracking_data.get('qty_to_sell', 0)
            
            if trade_price <= 0 or qty_to_sell <= 0:
                return
            
            # 익절 조건 확인 (코스피 지수 고려)
            should_profit_sell, profit_reason = self.should_sell_for_profit(
                stock_code, current_price, trade_price, high_price,
                kospi_index=self.kospi_index, time_period="ACTIVE_TRADING"
            )
            
            if should_profit_sell:
                logger.info(f"🎯 [적극-익절] {stock_code} 매도 시작 - {profit_reason}")
                await self.execute_sell_order(stock_code, qty_to_sell, "적극익절")
                return
            
            # 손절 조건 확인
            should_loss_sell, loss_reason = self.should_sell_for_loss(stock_code, current_price, trade_price)
            
            if should_loss_sell:
                logger.warning(f"🛑 [적극-손절] {stock_code} 매도 시작 - {loss_reason}")
                await self.execute_sell_order(stock_code, qty_to_sell, "적극손절")
                return
                
        except Exception as e:
            logger.error(f"❌ {stock_code} 적극 매도 로직 오류: {str(e)}")

    async def conservative_sell_logic(self, stock_code, market_data):
        """보수적 매매 시간대 매도 로직"""
        current_price = market_data['current_price']
        high_price = market_data['high_price']
        
        try:
            if not self.PT:
                return
                
            tracking_data = await self.PT.get_price_info(stock_code)
            if not tracking_data:
                logger.warning(f"⚠️ {stock_code} 추적 데이터 없음")
                return
            
            trade_price = tracking_data.get('trade_price', 0)
            qty_to_sell = tracking_data.get('qty_to_sell', 0)
            
            if trade_price <= 0 or qty_to_sell <= 0:
                return
            
            # 익절 조건 확인 (보수적: 고정 2%)
            should_profit_sell, profit_reason = self.should_sell_for_profit(
                stock_code, current_price, trade_price, high_price,
                time_period="CONSERVATIVE"
            )
            
            if should_profit_sell:
                logger.info(f"🎯 [보수-익절] {stock_code} 매도 시작 - {profit_reason}")
                await self.execute_sell_order(stock_code, qty_to_sell, "보수익절")
                return
            
            # 손절 조건 확인
            should_loss_sell, loss_reason = self.should_sell_for_loss(stock_code, current_price, trade_price)
            
            if should_loss_sell:
                logger.warning(f"🛑 [보수-손절] {stock_code} 매도 시작 - {loss_reason}")
                await self.execute_sell_order(stock_code, qty_to_sell, "보수손절")
                return
                
        except Exception as e:
            logger.error(f"❌ {stock_code} 보수 매도 로직 오류: {str(e)}")

    # 🔥 매수 로직들
    async def emergency_buy_logic(self, stock_code, market_data):
        """긴급 매수 로직 - 코스피 -3% 이상 하락시"""
        current_price = market_data['current_price']
        
        try:
            # long_trade_data에서 매수 정보 조회
            trade_info = self.long_trade_data.get(stock_code, {})
            if not trade_info:
                return
                
            target_buy_price = trade_info.get('buy_price', 0)
            target_buy_qty = trade_info.get('buy_qty', 0)
            
            if target_buy_price <= 0 or target_buy_qty <= 0:
                logger.warning(f"⚠️ {stock_code} 긴급 매수 데이터 부족 - 가격: {target_buy_price}, 수량: {target_buy_qty}")
                return
            
            # 목표가 이하에서 매수
            if current_price <= target_buy_price and stock_code not in self.trade_done:
                logger.warning(f"🚨 [긴급매수] {stock_code} - 코스피: {self.kospi_index}%, 현재가: {current_price:,}원 <= 목표: {target_buy_price:,}원")
                
                self.trade_done.append(stock_code)
                await self.execute_buy_order(stock_code, target_buy_qty, target_buy_price, "긴급매수")
                
        except Exception as e:
            logger.error(f"❌ {stock_code} 긴급 매수 로직 오류: {str(e)}")

    async def active_buy_logic(self, stock_code, market_data):
        """적극 매매 시간대 매수 로직"""
        current_price = market_data['current_price']
        open_price = market_data['open_price']
        low_price = market_data['low_price']
        
        try:
            # 코스피 -3% 이하면 매수 금지
            if self.kospi_index <= -3.0:
                logger.debug(f"📵 [매수금지] {stock_code} - 코스피 {self.kospi_index}% <= -3%")
                return
            
            # 장기거래 종목이 아니면 매수 안함
            if stock_code not in self.long_trade_code:
                return
                
            # 이미 거래 완료된 종목은 제외
            if stock_code in self.trade_done:
                return
            
            if not self.PT:
                return
                
            # 추적 데이터에서 매수 수량 조회
            tracking_data = await self.PT.get_price_info(stock_code)
            if not tracking_data:
                return
                
            target_buy_qty = tracking_data.get('qty_to_buy', 0)
            tracker_buy_price = tracking_data.get('price_to_buy', 0)
            
            if target_buy_qty <= 0:
                logger.warning(f"⚠️ {stock_code} 매수 수량 없음: {target_buy_qty}")
                return
            
            # 통합 매수가 계산
            calculated_buy_price = self.calculate_unified_buy_price(market_data, tracker_buy_price)
            
            # 매수 조건 확인: 현재가가 계산된 매수가 이하
            if current_price <= calculated_buy_price:
                # 추가 안전장치: 저점 대비 너무 높지 않은지 확인 (저점 대비 +2% 이내)
                if low_price > 0 and current_price <= low_price * 1.02:
                    logger.info(f"🛒 [적극매수] {stock_code} - 현재가: {current_price:,}원 <= 목표: {calculated_buy_price:,}원")
                    logger.info(f"    코스피: {self.kospi_index}%, 시가: {open_price:,}원, 저가: {low_price:,}원")
                    
                    self.trade_done.append(stock_code)
                    await self.execute_buy_order(stock_code, target_buy_qty, calculated_buy_price, "적극매수")
                else:
                    logger.debug(f"🚫 [매수보류] {stock_code} - 저점 대비 상승폭 과다: {current_price:,}원 vs 저가 {low_price:,}원")
            else:
                logger.debug(f"💰 [매수대기] {stock_code} - 현재가: {current_price:,}원 > 목표: {calculated_buy_price:,}원")
                
        except Exception as e:
            logger.error(f"❌ {stock_code} 적극 매수 로직 오류: {str(e)}")

    async def conservative_buy_logic(self, stock_code, market_data):
        """보수적 매매 시간대 매수 로직"""
        current_price = market_data['current_price']
        
        try:
            # 장기거래 종목이 아니면 매수 안함
            if stock_code not in self.long_trade_code:
                return
                
            # 이미 거래 완료된 종목은 제외
            if stock_code in self.trade_done:
                return
            
            if not self.PT:
                return
                
            # 추적 데이터에서 매수 정보 조회
            tracking_data = await self.PT.get_price_info(stock_code)
            if not tracking_data:
                return
                
            target_buy_qty = tracking_data.get('qty_to_buy', 0)
            tracker_buy_price = tracking_data.get('price_to_buy', 0)  # price_tracker의 buy_price 사용
            
            if target_buy_qty <= 0 or tracker_buy_price <= 0:
                logger.warning(f"⚠️ {stock_code} 보수 매수 데이터 부족 - 수량: {target_buy_qty}, 가격: {tracker_buy_price}")
                return
            
            # 보수적 매수: tracker_buy_price 이하에서만 매수
            if current_price <= tracker_buy_price:
                logger.info(f"🛡️ [보수매수] {stock_code} - 현재가: {current_price:,}원 <= 목표: {tracker_buy_price:,}원")
                
                self.trade_done.append(stock_code)
                await self.execute_buy_order(stock_code, target_buy_qty, tracker_buy_price, "보수매수")
            else:
                logger.debug(f"💰 [보수대기] {stock_code} - 현재가: {current_price:,}원 > 목표: {tracker_buy_price:,}원")
                
        except Exception as e:
            logger.error(f"❌ {stock_code} 보수 매수 로직 오류: {str(e)}")

    # 🔥 주문 실행 함수들
    async def execute_sell_order(self, stock_code, qty, order_type="매도"):
        """매도 주문 실행"""
        try:
            if not self.kiwoom_module:
                logger.error("Kiwoom 모듈이 초기화되지 않음")
                return
                
            # 보유주식 목록에서 제거
            if stock_code in self.holding_stock:
                self.holding_stock.remove(stock_code)
                
            await self.kiwoom_module.order_stock_sell(
                dmst_stex_tp="KRX",
                stk_cd=stock_code,
                ord_qty=str(qty),
                ord_uv="",      # 시장가
                trde_tp="3",    # 시장가 주문
                cond_uv=""
            )
            logger.info(f"✅ [{order_type}] {stock_code} 주문 완료 - {qty}주 시장가 매도")
            
        except Exception as e:
            logger.error(f"❌ [{order_type}] {stock_code} 주문 실패: {str(e)}")
            # 실패시 보유주식 목록 복원
            if stock_code not in self.holding_stock:
                self.holding_stock.append(stock_code)

    async def execute_buy_order(self, stock_code, qty, price, order_type="매수"):
        """매수 주문 실행"""
        try:
            if not self.kiwoom_module:
                logger.error("Kiwoom 모듈이 초기화되지 않음")
                return
                
            await self.kiwoom_module.order_stock_buy(
                dmst_stex_tp="KRX", 
                stk_cd=stock_code,
                ord_qty=str(qty),
                ord_uv="",      # 시장가 
                trde_tp="3",    # 시장가 주문
                cond_uv=""
            )
            logger.info(f"✅ [{order_type}] {stock_code} 주문 완료 - {qty}주 시장가 매수 (목표가: {price:,}원)")
            
        except Exception as e:
            logger.error(f"❌ [{order_type}] {stock_code} 주문 실패: {str(e)}")
            # 실패시 trade_done에서 제거
            if stock_code in self.trade_done:
                self.trade_done.remove(stock_code)

    # =================================================================
    # 시간대별
    # =================================================================
    async def long_trading_handler(self) : # 조건검색 으로 코드 등록 
        try:
            long_trade_code = {}
            
            # 거래 가능 종목 초기화
            trade_group  =[]
            
            # 조건 검색 요청 => 자동으로 realtime_group 에 추가됨
            await self.realtime_module.get_condition_list()
            kospi  = await self.realtime_module.request_condition_search(seq="0")
            kosdaq = await self.realtime_module.request_condition_search(seq="1")
            
            kospi  = self.cond_to_list(kospi)
            kosdaq = self.cond_to_list(kosdaq)
                
            # 계좌 정보에서 보유 주식 정보 추출 / 매도수량 관리용
            #주식코드, 보유수량, 평균 매매가격
            account_info = await self.kiwoom_module.get_account_info()
            self.account_info = self.extract_holding_stocks_info(account_info)
            
            # 현재 보유중인 주식
            self.holding_stock = await self.extract_stock_codes()
            
            # 현재 보유주식과 조건검색에서 찾은 모든 코드를 통합 
            condition_stock_codes = kospi + kosdaq
            all_stock_codes = list(set(condition_stock_codes) | set(self.holding_stock)) 
            
            # 거래 가능금액 추출 및 종목 별 할당
            self.deposit = await self.clean_deposit()
            self.assigned_per_stock = min(int(self.deposit / len(all_stock_codes)), 10000000)

            j = 0
            stock_qty = 0
            for stock_code in all_stock_codes :
                try:
                    j += 1
                    base_df = await self.LTH.daily_chart_to_df(stock_code)
                    odf = self.LTH.process_daychart_df(base_df)
                    dec_price5, dec_price10,dec_price20, = self.LTH.price_expectation(odf)
                    logger.info(f"주식 {stock_code} : {dec_price5},{dec_price10},{dec_price20}")
                    df = odf.head(20)

                    current_price = int(odf.iloc[0]["close"])
                    ma10_dif = round(((odf.iloc[0]['close'] -odf.iloc[0]['ma10']) / odf.iloc[0]['close'] * 100),2)
                    ma5_dif = round(((odf.iloc[0]['close'] -odf.iloc[0]['ma5']) / odf.iloc[0]['close'] * 100),2)
                    
                    if ma5_dif >= 5: 
                        buy_price = int(odf.iloc[0]["ma5"])
                        sell_price = max(int(current_price * 1.05), int(odf.iloc[0]["ma5"] * 1.1))
                        step = 'ma5'
                    elif ma10_dif >= 5 :
                        buy_price = int(odf.iloc[0]["ma10"])
                        sell_price =  max(int(current_price * 1.05), int(odf.iloc[0]["ma10"] * 1.1) )
                        step = 'ma10'
                    else :
                        buy_price = int(odf.iloc[0]["ma20"])
                        sell_price =  int(odf.iloc[0]["ma20"] * 1.10)
                        step = 'ma20'
                    avg_slope = self.LTH.average_slope(df)
                    buy_qty   = max(int(self.assigned_per_stock / current_price * 1.1), 1)
                    # 매수 가능한 주식만 선별해서 trade_group에 추가
                    if  avg_slope['avg_ma20_slope'] >= 0.1 and odf.iloc[0]["ma20_slope"] >= 0.1 :
                        stock_qty += 1
                        trade_group.append(stock_code)
                        logger.info(f"{stock_code} - 현재가 :{current_price}, 매수 목표가 :{buy_price}, 매도 목표가 :{sell_price} ")
                        long_trade_code[stock_code] = { 'current_price' : current_price,
                                                        'step'          : step,
                                                        'buy_price'     : buy_price,
                                                        'buy_qty'       : buy_qty,
                                                        'sell_price'    : sell_price }
                        

                except Exception as e:
                    logger.error(f"❌ 종목 {stock_code} 초기화 오류: {str(e)}")
                    
            # 주식 거래 데이터 업데이트
            self.save_long_trade_code(long_trade_code)
            await asyncio.sleep(1) # 저장시간 보장을 위해 1초 기다림
            self.load_long_trade_data = self.load_long_trade_code()
            self.trade_group = trade_group
            
            logger.info(f"🎯 장기거래 가능 : {stock_qty}개 종목")


        except Exception as e:
            logger.error(f"❌ short_trading_handler 메서드 전체 오류: {str(e)}")
        except asyncio.CancelledError:
            logger.warning("🛑 long_trading_handler 작업이 취소되었습니다.")
            # 여기에서 리소스 정리 등 작업 가능
        except KeyboardInterrupt:
            logger.warning("🛑 키보드 인터럽트 감지됨.")
        
    # =================================================================
    # 하루에 한 번만 실행하는 작업들
    # =================================================================
    async def time_handler(self):
        last_run = {}
        daily_trading_check = {}  # 일일 거래일 체크 결과 저장
        kst = pytz.timezone('Asia/Seoul')
        
        while True:
            try:
                # KST 기준 현재 시간
                now = datetime.now(kst)
                now_time = now.time()
                today = now.date()
                
                # 🔥 하루에 한 번만 거래일 체크
                if daily_trading_check.get(today) is None:
                    daily_trading_check[today] = self.system_daily_check()
                    # 이전 날짜 데이터 정리
                    daily_trading_check = {k: v for k, v in daily_trading_check.items() if k >= today}
                
                is_trading_day = daily_trading_check[today]
                
                # 휴장일이면 내일까지 대기
                if not is_trading_day:
                    logger.info("🚫 휴장일이므로 모든 거래 작업을 건너뜁니다.")
                    try:
                        tomorrow = today + timedelta(days=1)
                        target = kst.localize(datetime.combine(tomorrow, datetime_time(8, 30)))
                        sleep_time = max((target - now).total_seconds(), 3600)
                    except Exception:
                        sleep_time = 21600  # 6시간
                    await asyncio.sleep(sleep_time)
                    continue
                
                time_0830 = datetime_time(8, 30)
                time_0900 = datetime_time(9, 0)
                time_0930 = datetime_time(9, 30)
                time_1200 = datetime_time(12, 0)
                time_1530 = datetime_time(15, 30)
                
                # 다음 작업까지의 대기 시간 계산
                sleep_time = 300  # 기본 5분
                
                # 08:30-09:00 - 장기거래 코드 로딩
                if time_0830 <= now_time < time_0900:
                    if last_run.get('long_trading') != today:
                        logger.info("🌅 [08:30-09:00] 장기거래 코드 로딩")
                        await self.prepare_daily_trading()
                        last_run['long_trading'] = today
                    else:
                        # 09:00까지 남은 시간
                        try:
                            target = kst.localize(datetime.combine(today, time_0900))
                            sleep_time = max((target - now).total_seconds(), 60)
                        except Exception:
                            sleep_time = 300

                # 09:00-09:30 - 조건검색 및 거래 준비
                elif time_0900 <= now_time < time_0930:
                    if last_run.get('condition_search') != today:
                        logger.info("📋 [09:00-09:30] 조건검색 및 거래 준비")
                        # 필요한 TODO 함수 로직 : 현재는 없음
                        last_run['condition_search'] = today
                    else:
                        try:
                            target = kst.localize(datetime.combine(today, time_0930))
                            sleep_time = max((target - now).total_seconds(), 60)
                        except Exception:
                            sleep_time = 300
                            
                elif time_0930 <= now_time < time_1200:
                    if last_run.get('condition_search') != today:
                        logger.info("📋 [09:30-12:00] 조건검색 및 거래 준비")
                        await self.setup_morning_trading()
                        last_run['condition_search'] = today
                    else:
                        try:
                            target = kst.localize(datetime.combine(today, time_1200))
                            sleep_time = max((target - now).total_seconds(), 300)
                        except Exception:
                            sleep_time = 600
                            
                elif time_1200 <= now_time < time_1530:
                    if last_run.get('condition_search') != today:
                        logger.info("📋 [12:00-15:30] 조건검색 및 거래 준비")
                        await self.setup_afternoon_trading()
                        last_run['condition_search'] = today
                    else:
                        try:
                            target = kst.localize(datetime.combine(today, time_1530))
                            sleep_time = max((target - now).total_seconds(), 300)
                        except Exception:
                            sleep_time = 600
                            
                # 15:30 이후 - 장마감 후 처리
                elif now_time >= time_1530:
                    if last_run.get('post_market') != today:
                        logger.info("📊 [장마감 후] 장기거래 핸들러 실행")
                        await self.long_trading_handler()
                        last_run['post_market'] = today
                    else:
                        try:
                            tomorrow = today + timedelta(days=1)
                            target = kst.localize(datetime.combine(tomorrow, time_0830))
                            sleep_time = max((target - now).total_seconds(), 3600)
                        except Exception:
                            sleep_time = 3600

                # sleep_time 최종 검증
                if sleep_time <= 0 or sleep_time > 86400:
                    sleep_time = 300
                    
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"time_handler 실행 중 오류: {e}")
                await asyncio.sleep(300)

    def system_daily_check(self):
        try:
            logger.info("🔧 주식 개장일 체크 시작")
            
            today = date.today()
            
            # 주말 체크
            if today.weekday() >= 5:
                weekday_name = "토요일" if today.weekday() == 5 else "일요일"
                logger.info(f"🚫 {weekday_name}입니다. 프로그램 중단.")
                return False
            
            # 공휴일 체크
            if today in holidays:
                holiday_name = holidays[today]
                logger.info(f"🚫 공휴일({holiday_name})입니다. 프로그램 중단.")
                return False
            
            logger.info(f"✅ 거래일 확인 완료 - {today.strftime('%Y년 %m월 %d일')}")
            return True
            
        except Exception as e:
            logger.exception(f"❌ 시스템 점검 중 예외 발생: {str(e)}")
            return False
    
    # =================================================================
    # 시간대별 전략 메서드들 (실시간 실행)
    # =================================================================
    # 0830 ~ 0900 로직
    async def prepare_daily_trading(self):
        """일일 거래 준비 - 09:00-09:30"""
        logger.info("일일 거래 준비 시작")
        
        # 현재 보유중인 주식 코드 추출
        self.holding_stock = await self.extract_stock_codes()
        self.long_trade_data = self.load_long_trade_code()
        self.long_trade_code = list(self.long_trade_data.keys())
        
        logger.info(f"보유 주식 수: {len(self.holding_stock)}, 거래 대상 주식 수: {len(self.long_trade_code)}")
        
        self.trade_group = list(set(self.holding_stock) | set(self.long_trade_code))
        # 실시간 코스피, 코스닥 지수 등록
        try:
            await self.realtime_module.subscribe_realtime_price(
                group_no="0", 
                items=['001', '101'],  # 코스피, 코스닥 지수
                data_types=["0J"], 
                refresh=True
            )
            logger.info("코스피, 코스닥 지수 실시간 등록 완료")
        except Exception as e:
            logger.error(f"코스피 코스닥 실시간 등록 실패: {str(e)}")
            # 지수 등록 실패는 치명적이지 않으므로 계속 진행
        
        # 거래 대상 주식 실시간 데이터 등록
        if self.trade_group :  # 거래 대상이 있을 때만 실행
            try:
                await self.realtime_module.subscribe_realtime_price(
                    group_no="0", 
                    items=self.trade_group, 
                    data_types=["00", "0B", "04"],  # 현재가, 호가, 체결
                    refresh=True
                )
                logger.info(f"거래 대상 주식 {len(self.trade_group)}개 실시간 등록 완료")
            except Exception as e:
                logger.error(f"주식 실시간 등록 실패: {str(e)}")
                # 실시간 등록 실패 시에도 거래는 가능하므로 계속 진행
        else:
            logger.warning("거래 대상 주식이 없습니다")
        
        # 계정 정보 및 보유 주식 수량 업데이트
        try:
            await self.get_account_return()  # self.stock_qty 업데이트
            logger.info("계정 정보 조회 완료")
        except Exception as e:
            logger.error(f"계정 정보 조회 실패: {str(e)}")
            self.stock_qty = {}  # 실패 시 빈 딕셔너리로 초기화
            logger.warning("stock_qty를 빈 딕셔너리로 초기화")
        
        # 트래커 초기화 및 업데이트
        try:
            await self.initialize_tracker(self.trade_group)
            await self.update_long_trade()
            await self.update_holding_stock()
            logger.info("트래커 초기화 및 업데이트 완료")
        except Exception as e:
            logger.error(f"트래커 초기화/업데이트 실패: {str(e)}")
            # 트래커 실패는 거래에 영향을 줄 수 있으므로 예외를 재발생시킬 수도 있음
            # raise  # 필요시 주석 해제
        
        logger.info("일일 거래 준비 완료")

    # 0930 ~ 1200
    async def setup_morning_trading(self):
        """오전 거래 설정"""
        logger.info("🌅 오전 거래 모드 설정")
        await self.long_trading_handler()
        await asyncio.sleep(1)
        await self.prepare_daily_trading()
        # 오전 거래 특별 설정이 있다면 여기에

    # 1200 ~ 1530
    async def setup_afternoon_trading(self):
        """오후 거래 설정"""
        logger.info("🌆 오후 거래 모드 설정")

        await self.long_trading_handler()
        await asyncio.sleep(1)
        await self.prepare_daily_trading()        
        # 오후 거래 특별 설정이 있다면 여기에

    # =================================================================
    # 기타 helper 함수
    # =================================================================
    async def initialize_tracker(self, stock_codes):
        """보유종목 추적 초기화"""
        if not stock_codes:
            logger.warning("초기화할 종목이 없습니다.")
            return
        
        logger.info(f"📊 {len(stock_codes)}개 종목 추적 초기화 시작")
        
        for i, stock_code in enumerate(stock_codes, 1):
            try:
                logger.info(f"[{i}/{len(stock_codes)}] {stock_code} 초기화 중...")
                
                await self.PT.initialize_tracking(
                    stock_code=stock_code,
                    current_price=0,
                    trade_price=0,
                    period_type=False,
                    isfirst=False,
                    price_to_buy=0,
                    price_to_sell=0,
                    qty_to_sell=0,
                    qty_to_buy=0,
                    ma20_slope=0,
                    ma20_avg_slope=0,
                    ma20=0,
                    trade_type="HOLD"
                )
                
            except Exception as e:
                logger.error(f"❌ {stock_code} 초기화 실패: {str(e)}")
                continue
        
        logger.info("✅ 종목 추적 초기화 완료")

    async def update_holding_stock(self):
        """보유주식 추적 데이터 업데이트"""
        if not self.holding_stock:
            logger.warning("업데이트할 종목이 없습니다.")
            return {"success": 0, "error": 0}
        
        logger.info(f"📈 {len(self.holding_stock)}개 보유주식 추적 데이터 업데이트 시작")
        
        success_count = 0
        error_count = 0
        
        for i, stock_code in enumerate(self.holding_stock, 1):
            try:
                logger.info(f"[{i}/{len(self.holding_stock)}] 보유주식: {stock_code}")
                
                # 계좌 정보에서 종목 정보 가져오기
                stock_info = self.account_info.get(stock_code, {})
                logger.info(f"{stock_code} 정보\n{stock_info}")
                
                qty = int(stock_info.get('qty', 0))  # 보유 수량
                avg_price = int(stock_info.get('avg_price', 0))  # 평균 매수가
                
                # 입력 데이터 유효성 검사
                if qty <= 0:
                    logger.warning(f"⚠️ {stock_code}: 수량이 0 이하입니다. qty={qty}")
                    error_count += 1
                    continue
                    
                if avg_price <= 0:
                    logger.warning(f"⚠️ {stock_code}: 평균가가 0 이하입니다. avg_price={avg_price}")
                    error_count += 1
                    continue
                
                # 거래가 업데이트 시도
                logger.info(f"🔄 {stock_code} 거래가 업데이트 시도 - 평균가: {avg_price:,}원, 수량: {qty}주")
                
                try:
                    result = await self.PT.update_tracking_data(
                        stock_code=stock_code,
                        trade_price=avg_price,
                        qty_to_sell=qty,
                        trade_type="BUY"
                    )
                    
                    # 결과 확인
                    if result is not None:
                        success_count += 1
                        logger.info(f"✅ {stock_code} 거래가 업데이트 성공 - 평균가: {avg_price:,}원, 수량: {qty}주")
                    else:
                        error_count += 1
                        logger.error(f"❌ {stock_code} 거래가 업데이트 실패 - result=None")
                    
                except Exception as pt_error:
                    error_count += 1
                    logger.error(f"❌ {stock_code} PriceTracker 업데이트 예외: {str(pt_error)}")
                    logger.error(f"   - 종목코드: {stock_code}")
                    logger.error(f"   - 평균가: {avg_price}")
                    logger.error(f"   - 수량: {qty}")

            except Exception as e:
                error_count += 1
                logger.error(f"❌ {stock_code} 전체 처리 중 예외: {str(e)}")
                continue
        
        # 결과 요약
        total_count = len(self.holding_stock)
        logger.info(f"✅ 보유주식 업데이트 완료 - 성공: {success_count}/{total_count}, 실패: {error_count}")
        
        if error_count > 0:
            logger.warning(f"⚠️ {error_count}개 종목 업데이트 실패")
        
    async def update_long_trade(self):
        """장기거래 데이터를 로드하고 price_tracker 업데이트"""
        
        # 장기거래 데이터 로드
        self.long_trade_data = self.load_long_trade_code()
        
        if not self.long_trade_data:
            logger.warning("업데이트할 장기거래 데이터가 없습니다.")
            return {"success": 0, "error": 0}
        
        logger.info(f"📈 {len(self.long_trade_data)}개 장기거래 종목 추적 데이터 업데이트 시작")
        
        success_count = 0
        error_count = 0
        
        for i, (stock_code, trade_info) in enumerate(self.long_trade_data.items(), 1):
            try:
                logger.info(f"[{i}/{len(self.long_trade_data)}] 장기거래 종목: {stock_code}")
                
                # 장기거래 정보에서 데이터 가져오기
                logger.info(f"{stock_code} 장기거래 정보\n{trade_info}")
                
                current_price = int(trade_info.get('current_price', 0))  # 현재가
                buy_price = int(trade_info.get('buy_price', 0))         # 매수 목표가
                sell_price = int(trade_info.get('sell_price', 0))       # 매도 목표가
                buy_qty = int(trade_info.get('buy_qty', 0))             # 매수 수량
                
                # 입력 데이터 유효성 검사
                if current_price <= 0:
                    logger.warning(f"⚠️ {stock_code}: 현재가가 0 이하입니다. current_price={current_price}")
                    error_count += 1
                    continue
                    
                if buy_price <= 0:
                    logger.warning(f"⚠️ {stock_code}: 매수가가 0 이하입니다. buy_price={buy_price}")
                    error_count += 1
                    continue
                    
                if sell_price <= 0:
                    logger.warning(f"⚠️ {stock_code}: 매도가가 0 이하입니다. sell_price={sell_price}")
                    error_count += 1
                    continue
                    
                if buy_qty <= 0:
                    logger.warning(f"⚠️ {stock_code}: 매수수량이 0 이하입니다. buy_qty={buy_qty}")
                    error_count += 1
                    continue
                
                # price_tracker 업데이트 시도
                logger.info(f"🔄 {stock_code} 장기거래 데이터 업데이트 시도 - 매수목표가: {buy_price:,}원, 매도목표가: {sell_price:,}원, 수량: {buy_qty}주")
                
                try:
                    result = await self.PT.update_tracking_data(
                        stock_code=stock_code,
                        current_price=current_price,
                        price_to_buy=buy_price,
                        price_to_sell=sell_price,
                        qty_to_buy=buy_qty,
                        period_type=False,
                        isfirst=False
                    )
                    
                    # 결과 확인
                    if result is not None:
                        success_count += 1
                        logger.info(f"✅ {stock_code} 장기거래 데이터 업데이트 성공 - 매수가: {buy_price:,}원, 매도가: {sell_price:,}원, 수량: {buy_qty}주")
                    else:
                        error_count += 1
                        logger.error(f"❌ {stock_code} 장기거래 데이터 업데이트 실패 - result=None")
                    
                except Exception as pt_error:
                    error_count += 1
                    logger.error(f"❌ {stock_code} PriceTracker 업데이트 예외: {str(pt_error)}")
                    logger.error(f"   - 종목코드: {stock_code}")
                    logger.error(f"   - 매수목표가: {buy_price}")
                    logger.error(f"   - 매도목표가: {sell_price}")
                    logger.error(f"   - 매수수량: {buy_qty}")

            except Exception as e:
                error_count += 1
                logger.error(f"❌ {stock_code} 전체 처리 중 예외: {str(e)}")
                continue
        
        # 결과 요약
        total_count = len(self.long_trade_data)
        logger.info(f"✅ 장기거래 데이터 업데이트 완료 - 성공: {success_count}/{total_count}, 실패: {error_count}")
        
        if error_count > 0:
            logger.warning(f"⚠️ {error_count}개 종목 업데이트 실패")
        
        return {"success": success_count, "error": error_count}
      
    def save_long_trade_code(self, data: dict):
        os.makedirs("trade", exist_ok=True)
        file_path = os.path.join("trade", "long_trade_code.json")
        temp_path = file_path + ".tmp"
        backup_path = os.path.join("trade", "long_trade_code_backup.json")

        try:
            # 1. 임시 파일에 저장
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 2. 원자적 교체 (Ubuntu에서 안전)
            os.replace(temp_path, file_path)

            # 3. 정상 저장 후 backup 삭제
            if os.path.exists(backup_path):
                os.remove(backup_path)

        except Exception as e:
            print(f"⚠ 저장 실패: {e}")

            # 4. 실패 시 backup 저장
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 5. tmp 파일 정리
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def load_long_trade_code(self) -> dict:
        file_path = os.path.join("trade", "long_trade_code.json")
        backup_path = os.path.join("trade", "long_trade_code_backup.json")

        # 1. 백업 파일이 있으면 그것을 우선 읽기
        if os.path.exists(backup_path):
            try:
                with open(backup_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print("⚠ 백업 파일에서 데이터를 복구했습니다.")
                return data
            except Exception as e:
                print(f"⚠ 백업 파일 읽기 실패: {e}")

        # 2. 정상 파일 읽기
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠ 메인 파일 읽기 실패: {e}")
                return {}
        else:
            return {}
            
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
                      
    def extract_holding_stocks_info(self, account_info):
        """계좌 정보에서 보유 주식 정보 추출"""
        holding_stocks = {}
        
        try:
            if not account_info or not isinstance(account_info, dict):
                logger.warning("계좌 정보가 없거나 잘못된 형식입니다.")
                return holding_stocks
            
            # acnt_evlt_remn_indv_tot 배열에서 주식 정보 추출
            stock_list = account_info.get('acnt_evlt_remn_indv_tot', [])
            
            for stock_item in stock_list:
                try:
                    # 종목코드 (A 제거)
                    stock_code = stock_item.get('stk_cd', '')
                    if stock_code.startswith('A'):
                        stock_code = stock_code[1:]
                    
                    if not stock_code:
                        continue
                    
                    # 보유 수량 (rmnd_qty)
                    rmnd_qty_str = stock_item.get('rmnd_qty', '0')
                    rmnd_qty = self.safe_int_convert(rmnd_qty_str)
                    
                    # 평균 매수가 (pur_pric)
                    pur_pric_str = stock_item.get('pur_pric', '0')
                    pur_pric = self.safe_int_convert(pur_pric_str)
                    
                    # 현재가 (cur_prc)
                    cur_prc_str = stock_item.get('cur_prc', '0')
                    cur_prc = self.safe_int_convert(cur_prc_str)
                    
                    # 종목명
                    stock_name = stock_item.get('stk_nm', '')
                    
                    # 수익률
                    prft_rt_str = stock_item.get('prft_rt', '0')
                    try:
                        prft_rt = float(prft_rt_str)
                    except (ValueError, TypeError):
                        prft_rt = 0.0
                    
                    # 보유 수량이 0보다 큰 종목만 저장
                    if rmnd_qty > 0:
                        holding_stocks[stock_code] = {
                            'qty': rmnd_qty,           # 보유 수량
                            'avg_price': pur_pric,     # 평균 매수가
                            'current_price': cur_prc,  # 현재가
                            'stock_name': stock_name,  # 종목명
                            'profit_rate': prft_rt,    # 수익률
                            'trade_able_qty': self.safe_int_convert(stock_item.get('trde_able_qty', '0'))  # 거래가능수량
                        }
                        
                        logger.info(f"📊 보유 종목 발견: {stock_code}({stock_name}) - {rmnd_qty}주, 평단가: {pur_pric:,}원, 현재가: {cur_prc:,}원, 수익률: {prft_rt:.2f}%")
                    
                except Exception as e:
                    logger.error(f"❌ 주식 정보 파싱 오류: {e}, 데이터: {stock_item}")
                    continue
            
            logger.info(f"💼 총 보유 종목 수: {len(holding_stocks)}개")
            return holding_stocks
            
        except Exception as e:
            logger.error(f"❌ 보유 주식 정보 추출 실패: {e}")
            return holding_stocks

    def cond_to_list(self, data):
        """
        JSON 데이터에서 주식코드('9001' 필드)를 추출하여 리스트로 반환
        A로 시작하는 경우 A를 제거하고 6자리 코드만 반환
        
        Args:
            data: JSON 문자열 또는 딕셔너리
        
        Returns:
            list: 주식코드 리스트 (6자리)
        """
        
        # 문자열인 경우 JSON으로 파싱
        if isinstance(data, str):
            data = json.loads(data)
        
        stock_codes = []
        
        # 'data' 키가 있고 리스트인지 확인
        if 'data' in data and isinstance(data['data'], list):
            for item in data['data']:
                if '9001' in item:
                    code = item['9001']
                    # A로 시작하는 경우 A 제거
                    if code.startswith('A'):
                        code = code[1:]
                    stock_codes.append(code)
        
        return stock_codes

