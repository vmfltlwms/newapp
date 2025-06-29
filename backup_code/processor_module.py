# module.processor_module.py
from data.stock_code import KOSPI 
from datetime import date
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
from container.baseline_container import Baseline_Container
from container.realtime_container import RealTime_Container
from container.realtime_group_container import RealtimeGroup_container
from db.redis_db import RedisDB
from db.postgres_db import PostgresDB
from module.socket_module import SocketModule
from module.kiwoom_module import KiwoomModule  
from module.realtimegroup_module import RealtimeGroupModule
from module.baseline_module import BaselineModule
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
                realtime_group_module:RealtimeGroupModule= Provide[RealtimeGroup_container.realtime_group_module] ):
        self.redis_db = redis_db.get_connection()
        self.postgres_db = postgres_db
        self.socket_module = socket_module
        self.kiwoom_module = kiwoom_module
        self.baseline_module = baseline_module
        self.realtime_module = realtime_module
        self.realtime_group_module = realtime_group_module
        self.running = False
        self.cancel_check_task = None 
        self.condition_list ={'kospi':set(),'kosdaq':set()} #조건검색 리스트

        self.holding_stock =[]           # 현재 보유중인 주식
        self.stock_qty = {}              # 현재 주식별 보유 수량 관리
        self.deposit = 0                 # 예수금
        self.assigned_per_stock = 0      # 각 주식별 거래가능 금액
        self.account = []                # 내 주식 소유현황
        
        self.OrderDataExtractor = OrderDataExtractor(self.redis_db)
        self.StockPricePredictor = StockPricePredictor(self.redis_db)
        self.StockDataAnalyzer = StockDataAnalyzer(self.redis_db)
        self.PE = PriceExpectation(self.redis_db)
        self.BC = BaselineCache(self.postgres_db)
        self.PT = PriceTracker(self.redis_db)
        self.ST = SmartTrading(self.stock_qty, kiwoom_module, self.BC, self.baseline_module, self.PT)
        
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
        
    async def initialize(self):
        """ProcessorModule 초기화 - 수정된 버전"""
        try:
            # running을 True로 설정한 후 태스크 시작
            self.running = True
            
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
                res = await self.kiwoom_module.get_deposit_detail()
                # 🔧 수정: 안전한 숫자 변환
                entr_value = res.get("entr", "0")
                if isinstance(entr_value, str):
                    self.deposit = int(entr_value.replace(',', '')) if entr_value.replace(',', '').isdigit() else 0
                else:
                    self.deposit = int(entr_value) if entr_value else 0
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
          
    # 4. 자동 취소 체크 메서드들 추가
    async def auto_cancel_checker(self):
        """1분마다 미체결 주문 체크하여 자동 취소"""
        logging.info("🔄 자동 주문 취소 체크 시작")
        
        while self.running:
            try:
                await self.check_and_cancel_old_orders()
                # 10초마다 체크 (테스트용으로 자주 체크)
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                logging.info("자동 취소 체크 태스크가 취소되었습니다.")
                break
            except Exception as e:
                logging.error(f"자동 취소 체크 중 오류: {str(e)}")
                await asyncio.sleep(10)

    async def check_and_cancel_old_orders(self):
        """1분 이상 미체결 주문 찾아서 취소"""
        try:
            current_time = time.time()
            cutoff_time = current_time - 60  # 1분 = 60초 (테스트용)
            
            # Redis에서 모든 00 타입 키 조회
            pattern = "redis:00:*"
            keys = await self.redis_db.keys(pattern)
            
            if not keys:
                logging.debug("주문 데이터 키가 없습니다.")
                return
            
            cancel_targets = []
            
            for key in keys:
                # 1분 이전 ~ 현재까지의 모든 주문 데이터 조회
                old_orders = await self.redis_db.zrangebyscore(
                    key, min=0, max=cutoff_time, withscores=True
                )
                
                for order_data_str, score in old_orders:
                    try:
                        order_data = json.loads(order_data_str)
                        
                        # 미체결수량이 0보다 큰 경우 AND 취소상태가 아닌 경우
                        unclosed_qty = order_data.get('902', '0')
                        order_status = order_data.get('905', '').strip()  # 주문구분
                        order_state = order_data.get('913', '').strip()   # 주문상태
                        
                        # 취소된 주문이 아니고 미체결수량이 있는 경우만 취소 대상
                        if (unclosed_qty and int(unclosed_qty) > 0 and 
                            '취소' not in order_status and 
                            '취소' not in order_state):
                            
                            cancel_targets.append({
                                'key': key,
                                'order_data': order_data,
                                'score': score,
                                'data_str': order_data_str
                            })
                        elif int(unclosed_qty) == 0 or '취소' in order_status or '취소' in order_state:
                            # 이미 체결되었거나 취소된 주문은 Redis에서 제거
                            await self.redis_db.zrem(key, order_data_str)
                            logging.debug(f"🧹 완료된 주문 정리: {order_data.get('9203', 'unknown')}")
                            
                    except (json.JSONDecodeError, ValueError) as e:
                        logging.error(f"주문 데이터 파싱 오류: {e}")
                        # 파싱 불가능한 데이터는 제거
                        await self.redis_db.zrem(key, order_data_str)
                        continue
            
            # 취소 대상 주문들 처리
            if cancel_targets:
                logging.info(f"🚨 1분 이상 미체결 주문 {len(cancel_targets)}건 발견, 자동 취소 시작")
                
                for target in cancel_targets:
                    await self.cancel_old_order(target)
            else:
                logging.debug("자동 취소 대상 주문 없음")
                
        except Exception as e:
            logging.error(f"미체결 주문 체크 중 오류: {str(e)}")

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
        vlaues = data[0]
        request_type = vlaues.get('type')
        request_item = vlaues.get('item')
        request_name = vlaues.get('name')
        await self.type_callback(response)
        
    async def trnm_callback_cnsrlst(self, response:dict):
        pass

    async def trnm_callback_cnsrreq(self, response:dict):
        await self.stock_codes_grouping(response) # 반환되는 코드를 realtime group 에 추가가
        logger.info("trnm_callback_cnsrreq 실행")

    async def trnm_callback_cnsrclr(self, response:dict):
        pass

    async def trnm_callback_reg(self, response:dict):
        pass

    async def trnm_callback_unknown(self, response:dict):
        logging.warning(f'알 수 없는 trnm_type: {response.get("trnm")}')            

   # type callback handler

    async def type_callback(self, response: dict):
        data = response.get('data', [])
        if not data:
            logging.warning("빈 실시간 데이터 수신")
            return
        vlaues = data[0]
        request_type = vlaues.get('type')
        handler = self.type_callback_table.get(request_type)
        
        if handler: await handler(vlaues)
        else: logging.warning(f"알 수 없는 실시간 타입 수신: {request_type}")

    """주문체결 데이터 처리 - 특정 필드만 추출하여 Redis에 저장"""
    async def type_callback_00(self, data: dict): 
        try:
            values = data.get('values', {})
            stock_code = data.get('item')
            
            if not stock_code:
                logging.warning("주문체결 데이터에 종목코드(item)가 없습니다.")
                return
                
            # 필요한 필드만 추출
            order_data = {
                '9201': values.get('9201', ''),    # 계좌번호
                '9203': values.get('9203', ''),    # 주문번호  
                '9001': values.get('9001', ''),    # 종목코드,업종코드
                '10'  : values.get('10', ''),      # 현재가가
                '913': values.get('913', ''),      # 주문상태
                '302': values.get('302', ''),      # 종목명
                '900': values.get('900', ''),      # 주문수량
                '901': values.get('901', ''),      # 주문가격
                '902': values.get('902', ''),      # 미체결수량
                '903': values.get('903', ''),      # 체결누계금액
                '904': values.get('904', ''),      # 원주문번호
                '905': values.get('905', ''),      # 주문구분
                '906': values.get('906', ''),      # 매매구분
                '907': values.get('907', ''),      # 매도수구분
                '908': values.get('908', ''),      # 주문/체결시간
                '910': values.get('910', ''),      # 체결가
                '911': values.get('911', ''),      # 체결량
                '914': values.get('914', ''),      # 단위체결가
                '915': values.get('915', ''),      # 단위체결량
                '919': values.get('919', ''),      # 거부사유
                'timestamp': time.time(),          # 수신 시간
                'type': '00',                      # 타입 정보
                'name': data.get('name', ''),      # 이름 (주문체결)
            }
            
            # 🔧 수정: 안전한 숫자 변환 함수
            def safe_int_convert(value, default=0):
                """문자열을 안전하게 정수로 변환"""
                try:
                    if isinstance(value, str):
                        cleaned = value.strip()
                        return int(cleaned) if cleaned else default
                    elif isinstance(value, (int, float)):
                        return int(value)
                    else:
                        return default
                except (ValueError, AttributeError):
                    logging.warning(f"숫자 변환 실패: {value}")
                    return default
            
            # 안전한 데이터 추출
            trade_qty = safe_int_convert(order_data.get('911', '0'))        # 체결량
            execution_price = safe_int_convert(order_data.get('910', '0'))  # 체결가
            order_status = order_data.get('905', '').strip()                # 주문구분
            order_state = order_data.get('913', '').strip()                 # 주문상태
            
            # 🔧 수정: 주문 상태별 처리 로직 개선
            is_cancelled = '취소' in order_status or '취소' in order_state
            is_buy_order = '매수' in order_status and '취소' not in order_status
            is_sell_order = '매도' in order_status and '취소' not in order_status
            
            # 1. 취소 주문 처리
            if is_cancelled:
                order_data['902'] = '0'  # 미체결수량 0으로 설정
                logging.info(f"🚫 주문 취소 처리 - 종목: {stock_code}, 주문번호: {order_data.get('9203')}, 상태: {order_status}")
            
            # 2. 실제 체결된 경우만 수량 업데이트 (체결량이 0보다 큰 경우)
            # 개선된 버전
            elif trade_qty > 0 and execution_price > 0:  # 유효한 체결만 처리
                # 한 번만 계산
                clean_stock_code = stock_code[1:] if stock_code.startswith('A') else stock_code
                last_step = self.BC.get_last_step(clean_stock_code)
                baseline_info = self.BC.get_baseline_info(clean_stock_code,last_step)
                update_time = baseline_info.get('updated_at')
                baseline_qty = baseline_info.get('quantity')
                low_price = baseline_info.get('low_price')
                high_price = baseline_info.get('high_price')
                
                if is_buy_order:
                    # 1. 수량 업데이트
                    current_qty = self.stock_qty.get(clean_stock_code, 0)
                    self.stock_qty[clean_stock_code] = current_qty + trade_qty
                    
                    # 2. 가격 추적 시작
                    await self.PT.initialize_tracking(
                        stock_code=clean_stock_code,
                        highest_price=execution_price,
                        lowest_price=execution_price,
                        trade_price= execution_price,
                        trade_type="BUY")

                    new_qty = baseline_qty if last_step > 0 else int(baseline_qty * 0.2) # 나증에 수정해야함
                    gap_time = time.time() - update_time
                    if last_step < 3 and gap_time > 1800 : # 30분 이상 경과 
                        await self.baseline_module.add_step(clean_stock_code,
                                                            decision_price = execution_price,
                                                            quantity = new_qty, 
                                                            low_price = low_price,
                                                            high_price = high_price)
                        new_baseline = await self.baseline_module.get_last_baseline(clean_stock_code)
                        self.BC.add_to_cache(clean_stock_code, new_baseline)
                    # 3. 통합 로깅
                    logger.info(f"💰 매수 체결 완료 - 종목: {clean_stock_code}, 체결가: {execution_price}, "
                              f"체결량: {trade_qty}주, 수량: {current_qty} → {self.stock_qty[clean_stock_code]}주, "
                              f"가격추적: 시작")
                    
                elif is_sell_order:
                    # 1. 수량 업데이트
                    current_qty = self.stock_qty.get(clean_stock_code, 0)
                    new_qty = max(0, current_qty - trade_qty)
                    if baseline_qty - trade_qty <= 0 and last_step >= 1:
                        self.baseline_module.delete_last_step(clean_stock_code)
                        self.BC.remove_from_cache(clean_stock_code,last_step )
                      
                    # 3. 수량 반영
                    if new_qty <= 0:
                        self.stock_qty.pop(clean_stock_code, None)
                        # 2. 가격 추적 종료
                        await self.PT.remove_tracking(clean_stock_code)
                        status = "포지션 청산"
                    else:
                        self.stock_qty[clean_stock_code] = new_qty
                        await self.PT.initialize_tracking(
                            stock_code=clean_stock_code,
                            trade_price=execution_price,
                            trade_type="SELL")
                        status = "부분 매도"
                    
                    # 4. 통합 로깅
                    logger.info(f"💸 매도 체결 완료 - 종목: {clean_stock_code}, 체결가: {execution_price}, "
                              f"체결량: {trade_qty}주, 수량: {current_qty} → {new_qty}주, "
                              f"상태: {status}")
            

            # Redis에 저장 (Sorted Set 사용)
            type_code = '00'
            key = f"redis:{type_code}:{stock_code}"
            score = time.time()  # 현재 시간을 score로 사용
            value = json.dumps(order_data, ensure_ascii=False)
            
            await self.redis_db.zadd(key, {value: score})
            await self.redis_db.expire(key, 60 * 60 * 12)
            # 🔧 수정: 로그 정리 및 중복 제거
            unclosed_qty = safe_int_convert(order_data.get('902', '0'))
            
            # 상태별 로깅
            if is_cancelled:
                logging.info(f"🚫 주문 취소완료 - 종목: {stock_code}, 주문번호: {order_data.get('9203')}")
            elif unclosed_qty == 0 and trade_qty > 0:
                logging.info(f"✅ 주문 완전체결 - 종목: {stock_code}, 주문번호: {order_data.get('9203')}, 체결량: {trade_qty}주")
            elif unclosed_qty > 0:
                logging.info(f"📋 부분체결 - 종목: {stock_code}, 주문번호: {order_data.get('9203')}, "
                          f"체결량: {trade_qty}주, 미체결: {unclosed_qty}주")
            
            # 🔧 추가: 현재 보유 종목 현황 주기적 출력 (매 10번째 체결마다)
            if not hasattr(self, '_order_count'):
                self._order_count = 0
            self._order_count += 1
            
            if self._order_count % 10 == 0:
                holding_summary = {code: qty for code, qty in self.stock_qty.items() if qty > 0}
                if holding_summary:
                    logging.info(f"📊 현재 보유 종목 현황: {holding_summary}")
                
        except Exception as e:
            logging.error(f"❌ 주문체결 데이터 처리 중 오류 발생: {str(e)}")
            logging.error(f"원본 데이터: {data}")
            # 예외 발생 시에도 기본 Redis 저장은 시도
            try:
                type_code = '00'
                key = f"redis:{type_code}:{stock_code}"
                score = time.time()
                error_data = {'error': str(e), 'timestamp': score, 'original_data': data}
                value = json.dumps(error_data, ensure_ascii=False)
                await self.redis_db.zadd(key, {value: score})
            except:
                pass
          
    async def type_callback_02(self, data: dict): 
        logger.info(data)
        
    async def type_callback_04(self, data: dict):
        stock_code = data.get('item')
        last_order = self.OrderDataExtractor.get_latest_order_info(stock_code)
        logger.info(last_order)

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
            
            # tracking_data = await self.PT.get_tracking_data(stock_code)
            
            # if tracking_data is None: 
            
            await self.PT.initialize_tracking(stock_code, current_price,"")
            
            # 🔧 수정: step을 먼저 구하고 get_baseline_info 호출
            last_step = self.BC.get_last_step(stock_code)
            trading_money = int(self.assigned_per_stock / current_price)
            
            if self.BC.get_isfirst(stock_code, last_step) == True:  # 🔧 수정: step 파라미터 추가
                quantity = trading_money if last_step == 0 else int(trading_money/20)
                self.BC.update_baseline_cache(stock_code,
                                              step=last_step, 
                                              isfirst=False,
                                              quantity=quantity,
                                              open_price=current_price)
                
            if current_price > 0:       #PT : PriceTracker
                await self.PT.update_price(stock_code, current_price)
            
            if current_price > 0 and analysis is not None:
                # SmartTrading 실행
                await self.ST.trading_executor(stock_code, current_price, self.stock_qty, analysis)

            
            

        except Exception as e:
            logger.error(f"0B 데이터 처리 중 오류: {str(e)}")
            # logger.error(f"원본 데이터: {data}")  
    async def type_callback_0D(self, data: dict): pass

    # 주식 데이터에서 코드를 추출하고 시장별로 분류하는 함수
    async def stock_codes_grouping(self, data):
        logger.info("stock_codes_grouping 실행")
        try:
            seq = int(data['seq'].strip())
            
            for item in data['data']:
                stock_code = item['9001'][1:]
                if seq in [0]:
                    self.condition_list['kospi'].add(stock_code)
                elif seq in [1]:
                    self.condition_list['kosdaq'].add(stock_code)
            
            kosdaq_list = list(self.condition_list['kosdaq'])
            kospi_list = list(self.condition_list['kospi'])
            logger.info(kosdaq_list)
            logger.info(kospi_list)
            # KOSPI 그룹 처리
            for stock in kospi_list:
                try:
                    result = await self.realtime_group_module.add_stock_to_group(0, stock)
                    if result:
                        logger.info(f"KOSPI 종목 추가 성공: {stock}")
                    else:
                        logger.warning(f"KOSPI 그룹(0)이 존재하지 않음. 종목: {stock}")
                except Exception as e:
                    logger.error(f"KOSPI 종목 추가 실패: {stock}, 오류: {str(e)}")
            
            # KOSDAQ 그룹 처리  
            for stock in kosdaq_list:
                try:
                    result = await self.realtime_group_module.add_stock_to_group(1, stock)
                    if result:
                        logger.info(f"KOSDAQ 종목 추가 성공: {stock}")
                    else:
                        logger.warning(f"KOSDAQ 그룹(1)이 존재하지 않음. 종목: {stock}")
                except Exception as e:
                    logger.error(f"KOSDAQ 종목 추가 실패: {stock}, 오류: {str(e)}")
                    
        except Exception as e:
            logger.error(f"stock_codes_grouping 처리 중 오류: {str(e)}")
            
    # ProcessorModule의 add_baseline 메서드 수정 (에러 핸들링 추가)
    async def baseline_handler(self):
        # 🔧 수정: 변수들을 메서드 시작 부분에서 초기화
        success_count = 0
        error_count = 0
        
        try:
            self.holding_stock = await self.extract_stock_codes() # 현재 보유중인 주식 
            
            isfirst = await self.isfirst_start() # 오늘 첫번째 실행인지 확인   
            # isfirst = 1 # 오늘 첫번째 실행인지 확인   
            if isfirst :
                await self.realtime_group_module.delete_by_group(0)
                await self.realtime_group_module.delete_by_group(1)
                await self.realtime_group_module.create_new(group=0, data_type=[], stock_code=[])
                await self.realtime_group_module.create_new(group=1, data_type=[], stock_code=[])
                
            # 조건 검색 요청
            await self.realtime_module.get_condition_list()
            await asyncio.sleep(0.3)
            await self.realtime_module.request_condition_search(seq="0")
            await asyncio.sleep(0.3)
            await self.realtime_module.request_condition_search(seq="1")
            await asyncio.sleep(0.3)
            
            # 조건 검색으로 만들어진 그룹   
            res = await self.realtime_group_module.get_all_groups()  
            condition_stock_codes = [code for group in res for code in group.stock_code]
            
            if isfirst: #첫 번째 실행 - 베이스라인 초기화 시작
                # 베이스 라인 초기화 ( 현재 보유 주식에 없는 베이스 라인 삭제)
                baseline_module_codes = await self.baseline_module.get_all_stock_codes()

                clear_list = [x for x in baseline_module_codes if x not in self.holding_stock]
                for code in clear_list : 
                    self.baseline_module.delete_by_code(code)
                
                account_info = await self.extract_stock_codes_and_purchase_prices()
                
                # 현재 보유 주식에 없는 베이스라인 추가
                add_list = [x for x in self.holding_stock if x not in baseline_module_codes]
                for code in add_list : 
                    price = int(account_info.get(code))
                    qty = self.stock_qty.get(code)
                    low = int(price*0.97)
                    high = int(price*1.03)
                    await self.baseline_module.create_new(code,price,qty,low,high)
                    logger.info(f"{code} baseline 추가 : 가격 : {price}, 수량 : {qty}, {low} ~ {high}  ")
                
                # 초기화 완료 후 베이스라인 코드    
                baseline_module_codes = await self.baseline_module.get_all_stock_codes()
                all_stock_codes = list(set(condition_stock_codes + baseline_module_codes)) 
                
                stock_qty = len(all_stock_codes)
                stock_qty =  stock_qty if stock_qty >= 1 else 50 # 임시방법,, 나중에 다시 처리
                self.assigned_per_stock = int(self.deposit / stock_qty)
                trade_money = self.deposit / stock_qty if stock_qty > 0 else 0
                
                for code in condition_stock_codes:
                    try:
                        
                        # 일봉 차트 데이터 저장
                        await self.save_daily_chart_to_redis(code)
                        
                        # 가격 범위 예측
                        price_range = None
                        high = None
                        low = None
                        
                        try:
                            price_range = await self.PE.predict_tomorrow_price_range(code)
                            if price_range:
                                high = int(price_range.get('final_predicted_high'))
                                low = int(price_range.get('final_predicted_low'))
                            else:
                                logger.warning(f"⚠️ 종목 {code} 가격 범위 예측 실패 - None 반환")
                        except Exception as e:
                            logger.error(f"❌ 종목 {code} 가격 범위 예측 오류: {str(e)}")
                        
                        # 패턴 가격 예측
                        predicted_tomorrow_open = None
                        
                        try:
                            ptn_price = await self.StockPricePredictor.predict_from_redis(code)
                            if ptn_price and isinstance(ptn_price, dict):
                                predicted_tomorrow_open = int(ptn_price.get('predicted_tomorrow_open'))
                            else:
                                logger.warning(f"⚠️ 종목 {code} 패턴 가격 예측 실패 - {type(ptn_price)} 반환")
                        except Exception as e:
                            logger.error(f"❌ 종목 {code} 패턴 가격 예측 오류: {str(e)}")

                        try:
                            qty = int(trade_money / predicted_tomorrow_open) if trade_money > 0 and predicted_tomorrow_open and predicted_tomorrow_open > 0 else 1
                            if qty <= 0:
                                qty = 1  # 최소 1주
                        except (ZeroDivisionError, ValueError, TypeError):
                            logger.warning(f"⚠️ 종목 {code} 수량 계산 오류, 기본값 1주 사용")
                            qty = 1
                        
                        logger.info(f"💡 종목 {code} 최종 설정 - 기준가격: {predicted_tomorrow_open}, 범위: {low} ~ {high}, 수량: {qty}")
                        
                        # 🔧 수정: 베이스라인 생성 전 중복 체크 추가
                        if predicted_tomorrow_open is not None and predicted_tomorrow_open > 0:
                            try:
                                # 기존 베이스라인 존재 여부 확인
                                existing_codes = await self.baseline_module.get_all_stock_codes()
                                
                                if code in existing_codes:
                                    logger.warning(f"⚠️ 종목 {code} 베이스라인이 이미 존재함 - 건너뜀")
                                    continue
                                
                                await self.baseline_module.create_new(
                                    stock_code=code, 
                                    decision_price=predicted_tomorrow_open,
                                    quantity=qty,
                                    low_price=low,
                                    high_price=high
                                )
                                
                                success_count += 1
                                logger.info(f"종목 {code} 시작가 : {predicted_tomorrow_open}, 가격 범위 예측 : {low} ~ {high}")
                                logger.info(f"✅ 종목 {code} 베이스라인 생성 완료")
                                
                            except ValueError as ve:
                                # 중복 생성 시도 등의 값 오류
                                logger.warning(f"⚠️ 종목 {code} 베이스라인 생성 건너뜀: {str(ve)}")
                                continue
                            except Exception as e:
                                # 기타 예외
                                error_count += 1
                                logger.error(f"❌ 종목 {code} 베이스라인 생성 실패: {str(e)}")
                                continue
                        else:
                            logger.warning(f"⚠️ 종목 {code} 유효하지 않은 기준가격: {predicted_tomorrow_open}")
                            error_count += 1
                            continue
                        
                    except Exception as e:
                        error_count += 1
                        logger.error(f"❌ 종목 {code} 베이스라인 생성 실패: {str(e)}")
                        continue
                    
                    # API 호출 간격 조절
                
                logger.info(f"🎯 베이스라인 초기화 완료 - 성공: {success_count}개, 실패: {error_count}개")
                
                # 🔧 수정: 모든 베이스라인 생성 완료 후 한 번만 캐시 초기화
                logger.info("📦 BaselineCache 메모리 초기화 시작...")
                await self.BC.initialize_baseline_cache()  # 모든 baseline을 메모리로 로드
                logger.info("✅ BaselineCache 메모리 초기화 완료")
                
                # Price Tracker 초기화화
                for code in all_stock_codes : 
                    await self.PT.initialize_tracking(code, trade_price = 0,trade_type ="")
                
                # 베이스라인 캐시 상태 확인
                cache_count = len(self.BC.baseline_dict) if hasattr(self.BC, 'baseline_dict') else 0
                logger.info(f"📊 캐시된 베이스라인 데이터: {cache_count}개")
                
                # 실시간 가격 구독
                all_codes = await self.baseline_module.get_all_stock_codes()
                
                logger.info(f"🔔 실시간 가격 구독 시작: {len(all_codes)}개 종목")
                await self.realtime_module.subscribe_realtime_price(group_no="1", 
                                        items=all_codes, 
                                        data_types=["00","0B","04"], 
                                        refresh=True)
                
            else: # 첫번째 실행이 아닐 경우
                logger.info("🔄 이미 초기화된 상태 - 베이스라인 초기화 건너뜀")
                
                # 🔧 수정: 기존 데이터 사용 시에도 캐시 초기화
                logger.info("📦 기존 BaselineCache 메모리 로드 시작...")
                await self.BC.initialize_baseline_cache()  # 기존 baseline을 메모리로 로드
                logger.info("✅ 기존 BaselineCache 메모리 로드 완료")
                
                
                # 베이스라인 캐시 상태 확인
                cache_count = len(self.BC.baseline_dict) if hasattr(self.BC, 'baseline_dict') else 0
                logger.info(f"📊 로드된 베이스라인 데이터: {cache_count}개")
                
                # 실시간 가격 구독
                all_codes = await self.baseline_module.get_all_stock_codes()
                stock_qty = len(all_codes)
                stock_qty =  stock_qty if stock_qty >= 1 else 50 # 임시방법,, 나중에 다시 처리
                self.assigned_per_stock = int(self.deposit / stock_qty)
                logger.info(f"🔔 실시간 가격 구독 시작: {len(all_codes)}개 종목")
                await self.realtime_module.subscribe_realtime_price(group_no="1", 
                        items=all_codes, 
                        data_types=["00","0B","04"], 
                        refresh=True)
                
        except Exception as e:
            logger.error(f"❌ add_baseline 메서드 전체 오류: {str(e)}")
            logger.error(f"최종 통계 - 성공: {success_count}개, 실패: {error_count}개")
            raise
          
    # 일봉 차트 데이터를 조회하여 필요한 필드만 Redis에 저장
    async def save_daily_chart_to_redis(self, code):
        try:
            # 키움 API에서 일봉 차트 데이터 조회
            res = await self.kiwoom_module.get_daily_chart(code=code)
            # return_code 확인
            return_code = res.get('return_code', -1)
            if return_code != 0:
                logger.error(f"일봉 차트 조회 실패 - 종목: {code}, 코드: {return_code}, 메시지: {res.get('return_msg', '')}")
                return False
            
            # 차트 데이터 추출
            chart_data = res.get('stk_dt_pole_chart_qry', [])
            if not chart_data:
                logger.warning(f"일봉 차트 데이터가 없습니다 - 종목: {code}")
                return False
            
            # 최신 40개 데이터만 처리 (이미 40개가 최대일 수 있음)
            latest_data = chart_data[:40] if len(chart_data) > 40 else chart_data
                        
            # Redis 키 생성 (타입 코드 'DAILY' 사용)
            redis_key = f"redis:DAILY:{code}"
            
            # 기존 데이터 삭제 (최신 데이터로 완전 교체)
            await self.redis_db.delete(redis_key)
            
            saved_count = 0
            
            for daily_data in latest_data:
                try:
                    # 필요한 필드만 추출
                    filtered_data = {
                        'stk_cd': code,                                    # 종목코드 추가
                        'cur_prc': daily_data.get('cur_prc', ''),         # 현재가
                        'trde_qty': daily_data.get('trde_qty', ''),       # 거래량
                        'trde_prica': daily_data.get('trde_prica', ''),   # 거래대금
                        'dt': daily_data.get('dt', ''),                   # 일자
                        'open_pric': daily_data.get('open_pric', ''),     # 시가
                        'high_pric': daily_data.get('high_pric', ''),     # 고가
                        'low_pric': daily_data.get('low_pric', ''),       # 저가
                        'timestamp': time.time(),                          # 저장 시간
                        'type': 'DAILY'                                    # 데이터 타입
                    }
                    
                    # 일자를 score로 사용 (YYYYMMDD -> 숫자)
                    date_str = daily_data.get('dt', '')
                    if not date_str or len(date_str) != 8:
                        logger.warning(f"잘못된 일자 형식: {date_str}, 종목: {code}")
                        continue
                    
                    # YYYYMMDD를 숫자로 변환하여 score로 사용
                    try:
                        score = int(date_str)  # 20241107 -> 20241107
                    except ValueError:
                        logger.warning(f"일자 변환 실패: {date_str}, 종목: {code}")
                        continue
                    
                    # Redis Sorted Set에 저장
                    value = json.dumps(filtered_data, ensure_ascii=False)
                    await self.redis_db.zadd(redis_key, {value: score})
                    
                    saved_count += 1
                    
                    logger.debug(f"일봉 데이터 저장 - 종목: {code}, 일자: {date_str}, "
                              f"현재가: {filtered_data['cur_prc']}")
                    
                except Exception as e:
                    logger.error(f"개별 일봉 데이터 처리 오류 - 종목: {code}, 데이터: {daily_data}, 오류: {str(e)}")
                    continue
            
            # Redis 키에 만료 시간 설정 (예: 12시간)
            await self.redis_db.expire(redis_key, 43200)  # 12시간 = 43200 초
                        
            return True
            
        except Exception as e:
            logger.error(f"❌ 일봉 차트 데이터 처리 중 오류 - 종목: {code}, 오류: {str(e)}")
            return False

    # 추가적인 유틸리티 함수들
    async def get_daily_chart_from_redis(self, code: str, days: int = 40) -> list:
        """
        Redis에서 일봉 차트 데이터 조회
        
        Args:
            code (str): 종목 코드
            days (int): 조회할 일수 (기본값: 30일)
        
        Returns:
            list: 일봉 데이터 리스트 (최신순)
        """
        try:
            redis_key = f"redis:DAILY:{code}"
            
            # 최근 데이터부터 가져오기 (score 역순)
            raw_data = await self.redis_db.zrevrange(redis_key, 0, days - 1)
            
            results = []
            for item in raw_data:
                try:
                    parsed = json.loads(item)
                    if isinstance(parsed, dict):
                        results.append(parsed)
                except json.JSONDecodeError as e:
                    logger.error(f"일봉 데이터 JSON 파싱 실패: {e}, 원본: {item}")
                    continue
            
            logger.info(f"📈 Redis에서 일봉 데이터 조회 - 종목: {code}, 조회된 데이터: {len(results)}개")
            return results
            
        except Exception as e:
            logger.error(f"Redis 일봉 데이터 조회 오류 - 종목: {code}, 오류: {str(e)}")
            return []

    async def get_latest_price_from_redis(self, code: str) -> dict:
        """
        Redis에서 가장 최근 일봉 데이터 조회
        
        Args:
            code (str): 종목 코드
        
        Returns:
            dict: 최신 일봉 데이터 또는 빈 딕셔너리
        """
        try:
            redis_key = f"redis:DAILY:{code}"
            
            # 가장 최근 데이터 1개만 조회
            raw_data = await self.redis_db.zrevrange(redis_key, 0, 0)
            
            if not raw_data:
                logger.warning(f"최신 일봉 데이터 없음 - 종목: {code}")
                return {}
            
            latest_data = json.loads(raw_data[0])
            logger.debug(f"최신 일봉 데이터 조회 - 종목: {code}, 일자: {latest_data.get('dt')}, "
                        f"현재가: {latest_data.get('cur_prc')}")
            
            return latest_data
            
        except Exception as e:
            logger.error(f"최신 일봉 데이터 조회 오류 - 종목: {code}, 오류: {str(e)}")
            return {}

    async def update_all_daily_charts(self):
        """
        모든 등록된 종목의 일봉 차트 데이터 업데이트
        """
        try:
            # 모든 실시간 그룹에서 종목 코드 추출
            groups = await self.realtime_group_module.get_all_groups()
            all_stock_codes = set()
            
            for group in groups:
                if group.stock_code:
                    all_stock_codes.update(group.stock_code)
            
            logger.info(f"📊 전체 일봉 차트 데이터 업데이트 시작 - 대상 종목: {len(all_stock_codes)}개")
            
            success_count = 0
            error_count = 0
            
            for code in all_stock_codes:
                try:
                    result = await self.make_baseline_info(code)
                    if result:
                        success_count += 1
                    else:
                        error_count += 1
                    
                    # API 호출 간격 조절 (과도한 요청 방지)
                    await asyncio.sleep(0.5)  # 500ms 대기
                    
                except Exception as e:
                    logger.error(f"종목 {code} 일봉 데이터 업데이트 실패: {str(e)}")
                    error_count += 1
            
            logger.info(f"✅ 전체 일봉 차트 데이터 업데이트 완료 - 성공: {success_count}개, 실패: {error_count}개")
            
            return {
                "total": len(all_stock_codes),
                "success": success_count,
                "error": error_count
            }
            
        except Exception as e:
            logger.error(f"전체 일봉 차트 데이터 업데이트 중 오류: {str(e)}")
            return {"total": 0, "success": 0, "error": 0}
          
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
  
    async def extract_stock_codes_and_purchase_prices(self) -> Dict[str, str]:
      data = await self.kiwoom_module.get_account_info()
      
      # 문자열이면 JSON 파싱
      if isinstance(data, str):
          try:
              data = json.loads(data)
          except json.JSONDecodeError:
              print("잘못된 JSON 형식입니다.")
              return {}

      result = {}
      stock_list = data.get('acnt_evlt_remn_indv_tot', [])

      if isinstance(stock_list, list):
          for item in stock_list:
              stk_cd = item.get('stk_cd', '')[1:]  # 'A005930' → '005930'
              pur_pric = item.get('pur_pric', '')
              if stk_cd and pur_pric:
                  result[stk_cd] = pur_pric
      
      return result
    
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
                  
    async def check_special_conditions(self, stock_code: str, analysis: dict):
        """특별한 조건 체크 (알림, 매매 신호 등)"""
        analysis_5min = analysis.get('analysis_5min', {})
        analysis_1min = analysis.get('analysis_1min', {})
        latest = analysis.get('latest_data', {})
        
        strength_5min = analysis_5min.get('execution_strength', 0)
        strength_1min = analysis_1min.get('execution_strength', 0)
        buy_ratio_5min = analysis_5min.get('buy_ratio', 0)
        momentum = analysis_5min.get('momentum', {})
        
        alerts = []
        
        # 체결강도 급증 (5분 평균 > 150% 또는 1분 > 200%)
        if strength_5min > 150 or strength_1min > 200:
            alerts.append(f"🔥 체결강도 급증 (5분: {strength_5min}%, 1분: {strength_1min}%)")
        
        # 매수 우세 (매수비율 > 70%)
        if buy_ratio_5min > 70:
            alerts.append(f"📈 매수 우세 (매수비율: {buy_ratio_5min}%)")
        
        # 가격 급등 (5분간 +3% 이상)
        price_change_rate = momentum.get('price_change_rate', 0)
        if price_change_rate > 2:
            alerts.append(f"🚀 가격 급등 (5분간 +{price_change_rate}%)")
        elif price_change_rate < -2:
            alerts.append(f"📉 가격 급락 (5분간 {price_change_rate}%)")
        
    async def get_price_tracking_summary(self, stock_code: str = None) -> Dict:
        """가격 추적 요약 정보 조회"""
        try:
            if stock_code:
                # 특정 종목 조회
                summary = await self.PT.get_tracking_summary(stock_code)
                return {'single_stock': summary} if summary else {'error': f'종목 {stock_code} 추적 데이터 없음'}
            else:
                # 전체 추적 종목 조회
                tracking_stocks = await self.price_tracker.get_all_tracking_stocks()
                summaries = {}
                
                for code in tracking_stocks:
                    summary = await self.price_tracker.get_tracking_summary(code)
                    if summary:
                        summaries[code] = summary
                
                return {'all_stocks': summaries, 'total_count': len(summaries)}
                
        except Exception as e:
            logger.error(f"가격 추적 요약 조회 오류: {str(e)}")
            return {'error': str(e)}