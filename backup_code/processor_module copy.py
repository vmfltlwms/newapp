# module.processor_module.py
import math
from data.stock_code import KOSPI 
from datetime import date, datetime
import json
import time
from typing import Dict, List, Union
from dependency_injector.wiring import inject, Provide
import asyncio, json, logging 
from utils.patten_expectation import StockPricePredictor
from sqlmodel import select
from container.redis_container import Redis_Container
from container.postgres_container import Postgres_Container
from container.socket_container import Socket_Container
from container.kiwoom_container import Kiwoom_Container
from container.step_manager_container import Step_Manager_Container
from container.baseline_container import Baseline_Container
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
from redis_util.price_expectation import PriceExpectation
from redis_util.stock_analysis import StockDataAnalyzer
from models.isfirst import IsFirst
from services.baseline_cache_service import BaselineCache
from services.smart_trading_service import SmartTrading
from redis_util.order_data_service import OrderDataExtractor
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
                baseline_module:BaselineModule =Provide[Baseline_Container.baseline_module] ,
                step_manager_module : StepManagerModule = Provide[Step_Manager_Container.step_manager_module],
                realtime_group_module:RealtimeGroupModule = Provide[RealtimeGroup_container.realtime_group_module] ):
        self.redis_db = redis_db.get_connection()
        self.postgres_db = postgres_db
        self.socket_module = socket_module
        self.kiwoom_module = kiwoom_module
        self.baseline_module = baseline_module
        self.step_manager_module = step_manager_module
        self.realtime_module = realtime_module
        self.realtime_group_module = realtime_group_module
        self.running = False
        self.count = 0 
        self.cancel_check_task = None 
        self.condition_list ={'kospi':set(),'kosdaq':set()} #조건검색 리스트

        self.holding_stock =[]           # 현재 보유중인 주식
        self.stock_qty = {}              # 현재 주식별 보유 수량 관리
        self.deposit = 0                 # 예수금
        self.assigned_per_stock = 0      # 각 주식별 거래가능 금액
        self.account = []                # 내 주식 소유현황
        self.prev_baseline_code = []     # 이전에 유지되고 있는 베이스라인 
        self.order_tracker ={}
        self.order_execution_tracker = {}  # 새로운 추적용
        
        self.OrderDataExtractor = OrderDataExtractor(self.redis_db)
        self.StockPricePredictor = StockPricePredictor(self.redis_db)
        self.StockDataAnalyzer = StockDataAnalyzer(self.redis_db)
        self.PE = PriceExpectation(self.kiwoom_module, self.redis_db)
        self.BC = BaselineCache(self.postgres_db)
        self.PT = PriceTracker(self.redis_db)
        self.ST = SmartTrading(self.kiwoom_module, self.PT)
        
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
                # res = await self.kiwoom_module.get_deposit_detail()
                # # 🔧 수정: 안전한 숫자 변환
                # entr_value = res.get("entr", "0")
                # # 문자열이든 숫자든 통합 처리
                # cleaned_value = str(entr_value).replace(',', '').strip()
                # self.deposit = abs(int(cleaned_value)) if cleaned_value.lstrip('-').isdigit() else 0
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
       
    async def cancel_old_order(self, target: dict):
        """개별 주문 취소 처리"""
        try:
            order_data = target['order_data']
            orig_ord_no = order_data.get('9203')  # 주문번호
            stk_cd = order_data.get('9001')       # 종목코드
            unclosed_qty = order_data.get('902')  # 미체결수량
            order_time = order_data.get('908')    # 주문시간
            
            if not orig_ord_no or not stk_cd:
                logging.warning(f"주문번호 또는 종목코드 없음: {order_data}")
                # 잘못된 데이터는 Redis에서 제거
                await self.redis_db.zrem(target['key'], target['data_str'])
                return
                
            logging.info(f"📋 주문 취소 시도 - 종목: {stk_cd}, 주문번호: {orig_ord_no}, "
                        f"미체결수량: {unclosed_qty}, 주문시간: {order_time}")
            
            # KiwoomModule 타입 체크 및 의존성 주입 확인
            if not hasattr(self.kiwoom_module, 'order_stock_cancel'):
                logging.error(f"KiwoomModule에 order_stock_cancel 메서드가 없습니다. 타입: {type(self.kiwoom_module)}")
                # 의존성 주입 문제로 취소할 수 없는 주문은 Redis에서 제거 (무한 반복 방지)
                await self.redis_db.zrem(target['key'], target['data_str'])
                logging.warning(f"🗑️ 취소 불가능한 주문 Redis에서 제거: {orig_ord_no}")
                return
            
            # 키움 API를 통한 주문 취소
            result = await self.kiwoom_module.order_stock_cancel(
                dmst_stex_tp="KRX",  # 기본값으로 한국거래소 사용
                orig_ord_no=orig_ord_no,
                stk_cd=stk_cd,
                cncl_qty="0"  # 0 입력시 잔량 전부 취소
            )
            
            if result:
                logging.info(f"✅ 주문 취소 성공 - 주문번호: {orig_ord_no}")
                
                # Redis에서 해당 주문 데이터 제거 (이미 취소되었으므로)
                await self.redis_db.zrem(target['key'], target['data_str'])
                logging.info(f"🗑️ Redis에서 취소된 주문 데이터 제거: {orig_ord_no}")
                
            else:
                logging.warning(f"⚠️ 주문 취소 결과 불명 - 주문번호: {orig_ord_no}")
                # 취소 결과가 불명확한 경우에도 Redis에서 제거 (무한 반복 방지)
                await self.redis_db.zrem(target['key'], target['data_str'])
                logging.warning(f"🗑️ 취소 결과 불명으로 Redis에서 제거: {orig_ord_no}")
                
        except Exception as e:
            logging.error(f"주문 취소 처리 중 오류: {str(e)}")
            logging.error(f"대상 주문: {target.get('order_data', {})}")
            
            # 예외 발생한 주문도 Redis에서 제거 (무한 반복 방지)
            try:
                await self.redis_db.zrem(target['key'], target['data_str'])
                logging.warning(f"🗑️ 예외 발생으로 Redis에서 제거: {target['order_data'].get('9203', 'unknown')}")
            except Exception as cleanup_error:
                logging.error(f"Redis 정리 중 오류: {cleanup_error}")
    
    async def get_recent_prices(self,type_code, stock_code, seconds=300):
        key = f"redis:{type_code}:{stock_code}"
        now = time.time()
        since = now - seconds
        raw_data = await self.redis_db.zrangebyscore(key, min=since, max=now)

        results = []
        for item in raw_data:
            try:
                parsed = json.loads(item)
                if isinstance(parsed, dict):
                    results.append(parsed)
                else:
                    logging.warning(f"🚨 예상치 못한 타입 무시됨: {type(parsed)}, 내용: {parsed}")
            except json.JSONDecodeError as e:
                logging.error(f" 🥷 JSON 파싱 실패: {e}, 원본: {item}")
        
        return results
  
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

    async def type_callback(self, response: dict):
        """실시간 데이터 타입별 콜백 처리 - 배열의 모든 요소 처리"""
        data = response.get('data', [])
        
        if not data:
            logging.warning("빈 실시간 데이터 수신")
            return
        
        for index, item in enumerate(data):
            try:
                if not isinstance(item, dict):
                    logging.warning(f"잘못된 데이터 타입 (인덱스 {index}): {type(item)}")
                    continue
                    
                request_type = item.get('type')
                request_item = item.get('item')
                request_name = item.get('name')
                
                if request_type in ["00", "04"] : # 주식주문 과 실시간 계좌만 실시간으로 처리
                    logger.info(f"호출된 타입 {request_type} 아이템 {request_item} 이름 {request_name} (인덱스: {index})")
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
            stock_code = data.get('item')
            stock_code = stock_code[1:] if stock_code and stock_code.startswith('A') else stock_code
            if not stock_code:
                logging.warning("주문체결 데이터에 종목코드(item)가 없습니다.")
                return
                
            # 필요한 필드만 추출 (안전한 기본값 설정)
            def safe_get_value(data_dict, key, default='0'):
                value = data_dict.get(key, default)
                return default if value == '' or value is None else str(value)
            
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
            
            sum_of_trade_qty = trade_qty
            
            # 수정된 메서드 호출
            incremental_trade_qty = self.track_order_execution(order_number, order_qty, trade_qty, untrade_qty)
            logger.info(f"{order_number}에 주문량: {order_qty}, 증분체결량: {incremental_trade_qty}, 총체결량: {sum_of_trade_qty}")
            
            # 주문 상태별 처리 로직
            is_cancelled = '취소' in order_status or '취소' in order_state
            is_buy_order = '매수' in order_status and '취소' not in order_status
            is_sell_order = '매도' in order_status and '취소' not in order_status
            
            # 1. 취소 주문 처리 (prev_deposit 오류 수정)
            if is_cancelled:
                order_data['902'] = '0'  # 미체결수량 0으로 설정
                prev_deposit = self.deposit  # 이전 예수금 저장
                self.deposit = await self.clean_deposit()
                logger.info(f"예수금 변화: {prev_deposit} -> {self.deposit}")
                logging.info(f"🚫 주문 취소 처리 - 종목: {stock_code}, 주문번호: {order_data.get('9203')}, 상태: {order_status}")
            
            # 2. 실제 체결된 경우만 수량 업데이트 (증분 체결량 사용)
            elif incremental_trade_qty > 0 and execution_price > 0:
                tracking_data = await self.PT.get_tracking_data(stock_code)
                
                # 전량 체결 시 예수금 업데이트
                if untrade_qty == 0 and sum_of_trade_qty == order_qty:
                    prev_deposit = self.deposit
                    self.deposit = await self.clean_deposit()
                    logger.info(f"예수금 변화: {prev_deposit} -> {self.deposit}")
                
                if is_buy_order:
                    # 증분 체결량만 사용하여 수량 업데이트
                    qty_to_sell = max(tracking_data['qty_to_sell'] + incremental_trade_qty, 0)             
                    qty_to_buy = max(tracking_data['qty_to_buy'] - incremental_trade_qty, 0)

                    await self.PT.update_quantity(
                        stock_code=stock_code,
                        qty_to_sell=qty_to_sell,
                        qty_to_buy=qty_to_buy,
                        trade_type="BUY")

                    if sum_of_trade_qty == order_qty:
                        logger.info(f"💰 주문번호 {order_number} 주식: {stock_code} 매수 체결 완료")
                    else:
                        logger.info(f"💰 주문번호 {order_number} 주식: {stock_code} 매수 부분 체결")

                    logger.info(f"💰체결가: {execution_price}, 증분 체결량: {incremental_trade_qty}주, 매도가능 수량: {tracking_data['qty_to_sell']} → {qty_to_sell}주")
                    
                elif is_sell_order:
                    # 증분 체결량만 사용하여 수량 업데이트
                    
                    qty_to_sell = max(tracking_data['qty_to_sell'] - incremental_trade_qty, 0)             
                    qty_to_buy = max(tracking_data['qty_to_buy'] + incremental_trade_qty, 0)
                    
                    await self.PT.update_quantity(
                        stock_code=stock_code,
                        qty_to_sell=qty_to_sell,
                        qty_to_buy=qty_to_buy,
                        trade_type="SELL")
                    
                    if sum_of_trade_qty == order_qty:
                        logger.info(f"💰 주문번호 {order_number} 주식: {stock_code} 매도 체결 완료")
                    else:
                        logger.info(f"💰 주문번호 {order_number} 주식: {stock_code} 매도 부분 체결")

                    logger.info(f"💰체결가: {execution_price}, 증분 체결량: {incremental_trade_qty}주, 매수가능 수량: {tracking_data['qty_to_buy']} → {qty_to_buy}주")
                    
            score = time.time()
            value = json.dumps(order_data, ensure_ascii=False)
            
            # 안전한 Sorted Set 저장
            key = self.get_redis_key("trade_data", stock_code)
            await self.safe_redis_operation("zadd", key, mapping={value: score})
            await self.redis_db.expire(key, 60 * 60 * 0.5)  # 30분 만료
            
            logger.debug(f"✅ trade_data 저장 완료 - 종목: {stock_code}")

        except Exception as e:
            logging.error(f"❌ 주문체결 데이터 처리 중 오류 발생: {str(e)}")
            import traceback
            logging.error(f"상세 오류 정보: {traceback.format_exc()}")
            


    async def type_callback_02(self, data: dict): 
        logger.info(data)
        
    async def type_callback_04(self, data: dict):
        """현물잔고 데이터 처리 - 최신 데이터로 업데이트"""
        try:
            # logger.info(f" 04 handler 에서  전달받은 데이터 \n {data}")
            values = data.get('values', {})
            stock_code = data.get('item')
            
            
            if not stock_code:
                logger.warning("04 데이터에 종목코드(item)가 없습니다.")
                return
            
            # 중요 필드 추출
            account_no = values.get('9201', '')          # 계좌번호
            current_price = values.get('10', '')         # 현재가
            quantity = values.get('930', '0')            # 보유수량
            avg_price = values.get('931', '0')           # 평균단가
            eval_amount = values.get('932', '0')         # 평가금액
            profit_loss = values.get('950', '0')         # 평가손익
            profit_rate = values.get('8019', '0')        # 수익률
            
            # 🔧 수정: 안전한 숫자 변환
            try:
                quantity_int = abs(int(quantity.replace(',', ''))) if quantity else 0
                avg_price_int = abs(int(avg_price.replace(',', ''))) if avg_price else 0
                
                # A 제거 (A105560 → 105560)
                clean_code = stock_code[1:] if stock_code.startswith('A') else stock_code
                
                # 보유 수량 업데이트 (self.stock_qty)
                if quantity_int > 0:
                    self.stock_qty[clean_code] = quantity_int
                    logger.info(f"📊 잔고 업데이트 - 종목: {clean_code}, 수량: {quantity_int}주, "
                              f"평균단가: {avg_price_int}원, 수익률: {profit_rate}%")
                else:
                    # 수량이 0이면 제거
                    if clean_code in self.stock_qty:
                        del self.stock_qty[clean_code]
                        logger.info(f"🗑️ 잔고 제거 - 종목: {clean_code} (수량 0)")
                        
            except (ValueError, AttributeError) as e:
                logger.error(f"04 데이터 숫자 변환 오류: {e}")
                logger.error(f"원본 데이터: quantity={quantity}, avg_price={avg_price}")
            
            # 🆕 Redis에 최신 데이터로 업데이트 (축적 X, 교체 O)
            type_code = '04'
            key = f"redis:{type_code}:{stock_code}"
            
            # 저장할 데이터 구성
            balance_data = {
                '9201': account_no,
                '9001': stock_code,
                '10': current_price,
                '930': quantity,
                '931': avg_price,
                '932': eval_amount,
                '950': profit_loss,
                '8019': profit_rate,
                'timestamp': time.time(),
                'type': '04',
                'name': data.get('name', '현물잔고'),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            key = self.get_redis_key("string", "04", stock_code)
            value = json.dumps(balance_data, ensure_ascii=False)
            
            # 🔧 핵심 수정: 기존 데이터 삭제 후 새 데이터 저장
            await self.safe_redis_operation("set", key, value=value)
            await self.redis_db.expire(key, 60 * 60 * 24)  # 24시간 만료
            
            logger.debug(f"✅ 04 타입 Redis 최신 데이터 저장 완료 - 종목: {stock_code}")
            
        except Exception as e:
            logger.error(f"❌ 04 타입 데이터 처리 중 오류: {str(e)}")
            logger.error(f"원본 데이터: {data}")

    async def type_callback_0B(self, data: dict):
        try:
            stock_code = data.get('item')  

            # 종목코드 정제 (예: A005930 -> 005930)  
            stock_code = stock_code[1:] if stock_code.startswith('A') else stock_code
            
            if not stock_code:
                logger.warning("0B 데이터에 종목코드가 없습니다.")
                return
              
            # 데이터 파싱
            parsed_data = self.StockDataAnalyzer.parse_0b_data(data)
            
            # Redis에 저장
            await self.StockDataAnalyzer.store_0b_data(stock_code, parsed_data)
            
            # 실시간 분석 수행
            analysis = await self.StockDataAnalyzer.analyze_stock_0b(stock_code)
            
            # 🆕 현재가로 가격 추적 업데이트
            current_price = abs(int(parsed_data.get('current_price')))
            

            #PT : PriceTracker    
            if current_price > 0:       
                # await self.PT.update_price(stock_code, current_price)
                IsFirst = await self.PT.isfirst(stock_code)
                if IsFirst : 
                    qty_to_buy = math.ceil((self.assigned_per_stock/current_price) / 10) * 10
                    logger.info(f"{stock_code}IsFirst 매수 가능주식 {qty_to_buy}실행")
                    await self.PT.initialize_tracking( # 처음 값이 들어오면 qty_to_sell 계산
                                                                  stock_code = stock_code, 
                                                                  trade_price = 0, 
                                                                  period_type = False,
                                                                  isfirst = False,
                                                                  qty_to_sell = 0,
                                                                  qty_to_buy = qty_to_buy,
                                                                  trade_type = "HOLD" )
            
            
            # SmartTrading 실행
            # if analysis is not None:
            #     await self.ST.trading_executor(stock_code, current_price, analysis)


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

    # 🆕 추가: 조건검색 상태 확인 메서드
    async def get_condition_search_status(self):
        """조건검색 결과 상태 확인"""
        try:
            kospi_count = len(self.condition_list.get('kospi', set()))
            kosdaq_count = len(self.condition_list.get('kosdaq', set()))
            
            status = {
                'kospi': {
                    'count': kospi_count,
                    'codes': list(self.condition_list.get('kospi', set()))[:10]  # 처음 10개만
                },
                'kosdaq': {
                    'count': kosdaq_count, 
                    'codes': list(self.condition_list.get('kosdaq', set()))[:10]  # 처음 10개만
                },
                'total': kospi_count + kosdaq_count
            }
            
            logger.info(f"📊 조건검색 상태 - KOSPI: {kospi_count}개, KOSDAQ: {kosdaq_count}개, 총합: {status['total']}개")
            return status
            
        except Exception as e:
            logger.error(f"❌ 조건검색 상태 확인 오류: {str(e)}")
            return {'error': str(e)}
            
    # ProcessorModule의 add_baseline 메서드 수정 (에러 핸들링 추가)
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
            
            # logger.info(f"condition_stock_codes = {condition_stock_codes}")
            for code in condition_stock_codes :

                try:
                    await self.PT.initialize_tracking( # 처음 값이 들어오면 qty_to_sell 계산
                                              stock_code = code, 
                                              trade_price = 0, 
                                              period_type = False,
                                              isfirst = True,
                                              qty_to_sell = 0,
                                              qty_to_buy = 0,
                                              trade_type = "HOLD" ) 

                except Exception as e:
                    logger.error(f"❌ 종목 {code} 가격 범위 예측 오류: {str(e)}")

        except Exception as e:
            logger.error(f"❌ realtime_group_handler 메서드 전체 오류: {str(e)}")
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
        logging.info("🔄 자동 주문 취소 체크 시작")
        
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
        """10분 이상 미체결 주문 찾아서 취소"""
        try:
            current_time = time.time()
            cutoff_time = current_time - 60  # 10분 = 600초
            
            # Redis에서 모든 00 타입 주문 키 조회
            pattern = "trade_data:*"  # redis:00:종목코드:주문번호 패턴
            keys = await self.redis_db.keys(pattern)
            
            if not keys:
                logging.debug("주문 데이터 키가 없습니다.")
                return
            
            cancel_targets = []
            completed_orders = []
            
            for key in keys:
                try:
                    # 각 주문의 최신 데이터 조회
                    order_data_str = await self.redis_db.get(key)
                    
                    if not order_data_str:
                        continue
                        
                    order_data = json.loads(order_data_str)
                    order_timestamp = order_data.get('timestamp', current_time)
                    
                    # 안전한 데이터 추출 - 타입 보장
                    order_number = str(order_data.get('9203', '0'))
                    
                    # safe_int_convert 함수 사용 (이미 정수를 반환하므로 추가 int() 불필요)
                    order_qty = self.safe_int_convert(order_data.get('900', '0'), 0)
                    trade_qty = self.safe_int_convert(order_data.get('911', '0'), 0)
                    untrade_qty = self.safe_int_convert(order_data.get('902', '0'), 0)
                    execution_price = self.safe_int_convert(order_data.get('910', '0'), 0)
                    
                    order_status = str(order_data.get('905', '')).strip()
                    order_state = str(order_data.get('913', '')).strip()
                    
                    # timestamp도 숫자형으로 보장
                    try:
                        order_timestamp = float(order_timestamp)
                    except (ValueError, TypeError):
                        order_timestamp = current_time
                    
                    # 1. 주문 완료 체크 (주문량 == 체결량 AND 미체결량 == 0)
                    if (order_qty > 0 and trade_qty > 0 and 
                        order_qty == trade_qty and untrade_qty == 0):
                        
                        completed_orders.append({
                            'key': key,
                            'order_number': order_number,
                            'order_data': order_data
                        })
                        continue
                    
                    # 2. 이미 취소된 주문 체크
                    if ('취소' in order_status or '취소' in order_state or 
                        '거부' in order_status or '거부' in order_state):
                        
                        completed_orders.append({
                            'key': key,
                            'order_number': order_number,
                            'order_data': order_data,
                            'reason': '취소/거부'
                        })
                        continue
                    
                    # 3. 10분 이상 미체결 주문 체크
                    if (order_timestamp <= cutoff_time and 
                        untrade_qty > 0 and 
                        '취소' not in order_status and 
                        '취소' not in order_state and
                        '거부' not in order_status and 
                        '거부' not in order_state):
                        
                        cancel_targets.append({
                            'key': key,
                            'order_data': order_data,
                            'timestamp': order_timestamp,
                            'age_minutes': (current_time - order_timestamp) / 60
                        })
                        
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    logging.error(f"주문 데이터 파싱 오류 ({key}): {e}")
                    # 파싱 불가능한 데이터는 제거
                    await self.redis_db.delete(key)
                    continue
            
            # 완료된 주문들 정리
            if completed_orders:
                logging.info(f"🧹 완료된 주문 {len(completed_orders)}건 정리")
                
                for completed in completed_orders:
                    await self.redis_db.delete(completed['key'])
                    reason = completed.get('reason', '체결완료')
                    logging.info(f"✅ 주문 정리: {completed['order_number']} ({reason})")
            
            # 취소 대상 주문들 처리
            if cancel_targets:
                logging.info(f"🚨 10분 이상 미체결 주문 {len(cancel_targets)}건 발견, 자동 취소 시작")
                
                for target in cancel_targets:
                    await self.cancel_old_order(target)
            else:
                logging.debug("자동 취소 대상 주문 없음")
                
        except Exception as e:
            logging.error(f"미체결 주문 체크 중 오류: {str(e)}")
            # 추가 디버그 정보
            import traceback
            logging.error(f"상세 오류 정보: {traceback.format_exc()}")

    async def cancel_old_order(self, target):
        """미체결 주문 취소 실행"""
        try:
            order_data = target['order_data']
            key = target['key']
            age_minutes = target.get('age_minutes', 0)
            
            order_number = order_data.get('9203', '')
            stock_code = order_data.get('9001', '')
            stock_name = order_data.get('302', '')
            untrade_qty = order_data.get('902', '0')
            order_price = order_data.get('901', '0')
            
            logging.warning(f"🔴 미체결 주문 자동 취소 시도: {stock_name}({stock_code}) "
                          f"주문번호:{order_number} 미체결:{untrade_qty}주 "
                          f"경과시간:{age_minutes:.1f}분")
            
            # 실제 취소 주문 API 호출 
            await self.kiwoom_module.order_stock_cancel(            		
                                    dmst_stex_tp= 'KRX',        # 국내거래소구분 KRX,NXT,SOR
                                    orig_ord_no = order_number, # 원주문번호 
                                    stk_cd= stock_code,         # 종목코드 
                                    cncl_qty= '0', )            # 전량취소

            
            # 취소 시도 후 Redis에서 제거 (실제 취소 성공 여부와 관계없이)
            await self.redis_db.delete(key)
            logging.info(f"🗑️ 취소 시도 완료 후 Redis 정리: {order_number}")
            
            # 취소 이력 저장 (선택적)
            cancel_record = {
                'cancelled_at': time.time(),
                'reason': 'auto_cancel_timeout',
                'age_minutes': age_minutes,
                **order_data
            }
            
            # 취소 이력을 별도 키에 저장 (24시간 보관)
            cancel_key = f"redis:cancel:{stock_code}:{order_number}"
            await self.redis_db.setex(
                cancel_key, 
                60 * 60 * 1,  # 24시간
                json.dumps(cancel_record, ensure_ascii=False)
            )
            
        except Exception as e:
            logging.error(f"주문 취소 처리 중 오류: {str(e)}")

    # 주문 데이터 저장 부분 (수정된 버전)
    async def save_order_data(self, order_data, stock_code):
        """주문 데이터를 개별 키로 저장"""
        try:
            type_code = '00'
            order_number = order_data.get('9203', '0')
            
            # 개별 주문 키 생성
            key = self.get_redis_key("trade_data", stock_code)
            
            # 최신 데이터로 업데이트 (덮어쓰기)
            value = json.dumps(order_data, ensure_ascii=False)
            
            # 12시간 TTL 설정
            await self.redis_db.setex(key, 60 * 60 * 0.5, value)
            
            logging.debug(f"📝 주문 데이터 저장: {key}")
            
        except Exception as e:
            logging.error(f"주문 데이터 저장 중 오류: {str(e)}")


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
     
          
    def get_redis_key(self, data_type: str,  stock_code: str) -> str:

        return f"{data_type}:{stock_code}"
    
    async def safe_redis_operation(self, operation_type: str, key: str, **kwargs):
        """
        Redis 타입 충돌을 안전하게 처리하는 헬퍼 메서드
        """
        try:
            if operation_type == "zadd":
                return await self.redis_db.zadd(key, kwargs.get('mapping', {}))
            elif operation_type == "set":
                return await self.redis_db.set(key, kwargs.get('value', ''))
            elif operation_type == "get":
                return await self.redis_db.get(key)
            elif operation_type == "zrevrange":
                return await self.redis_db.zrevrange(key, kwargs.get('start', 0), kwargs.get('end', -1))
            elif operation_type == "zrangebyscore":
                return await self.redis_db.zrangebyscore(key, 
                                                       min=kwargs.get('min', 0), 
                                                       max=kwargs.get('max', time.time()))
                
        except self.redis.exceptions.WrongTypeError:
            # 타입 충돌 발생 시 키 삭제 후 재시도
            logger.warning(f"🔧 Redis 타입 충돌 감지, 키 초기화: {key}")
            await self.redis_db.delete(key)
            
            # 재시도
            if operation_type == "zadd":
                return await self.redis_db.zadd(key, kwargs.get('mapping', {}))
            elif operation_type == "set":
                return await self.redis_db.set(key, kwargs.get('value', ''))
                
        except Exception as e:
            logger.error(f"❌ Redis 연산 오류 - 타입: {operation_type}, 키: {key}, 오류: {str(e)}")
            return None

