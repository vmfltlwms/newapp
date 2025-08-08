import asyncio
import logging
import time
from datetime import datetime, time as datetime_time
import pytz
from dependency_injector.wiring import inject, Provide

from container.kiwoom_container import Kiwoom_Container
from container.redis_container import Redis_Container
from container.socket_container import Socket_Container
from db.redis_db import RedisDB
from module.kiwoom_module import KiwoomModule
from module.socket_module import SocketModule
from redis_util.price_tracker_service import PriceTracker

logger = logging.getLogger("Trading_Handler")

class Trading_Handler:
    def __init__(self, 
                redis_db: RedisDB = Provide[Redis_Container.redis_db],
                kiwoom_module: KiwoomModule = Provide[Kiwoom_Container.kiwoom_module]) : 
        self.kiwoom_module = kiwoom_module
        self.redis_db = redis_db.get_connection()
        # ProcessorModule의 속성들을 직접 참조
        self.kospi_index = 0
        self.kosdaq_index = 0
        self.PT = PriceTracker(self.redis_db)
        
    @property
    def holding_stock(self):
        """보유 주식 목록"""
        return getattr(self.processor, 'holding_stock', [])
    
    @property 
    def trade_done(self):
        """거래 완료 목록"""
        return getattr(self.processor, 'trade_done', [])
    
    @property
    def long_trade_code(self):
        """장기거래 종목 코드 목록"""
        return getattr(self.processor, 'long_trade_code', [])
    
    @property
    def long_trade_data(self):
        """장기거래 데이터"""
        return getattr(self.processor, 'long_trade_data', {})
    
    @property
    def PT(self):
        """PriceTracker 인스턴스"""
        return getattr(self.processor, 'PT', None)
    


    def update_market_indices(self, kospi_index=None, kosdaq_index=None):
        """시장 지수 업데이트"""
        if kospi_index is not None:
            self.kospi_index = kospi_index
        if kosdaq_index is not None:
            self.kosdaq_index = kosdaq_index

    async def handle_realtime_data(self, data: dict):
        """실시간 데이터 처리 - 메인 진입점"""
        try:
            # 🔥 1. 시간 및 날짜 정보
            kst = pytz.timezone('Asia/Seoul')
            now = datetime.now(kst)
            now_time = now.time()
            
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

            # 데이터 유효성 검사
            if not self.validate_market_data(market_data):
                return

            # 🔥 3. 시장 지수 업데이트 (ProcessorModule에서 받아옴)
            self.kospi_index = getattr(self.processor, 'kospi_index', 0)
            self.kosdaq_index = getattr(self.processor, 'kosdaq_index', 0)

            # 🔥 4. 시간대별 전략 분기
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
            logger.error(f"❌ Trading_Handler 처리 중 오류: {str(e)}")
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
            final_buy_price = min(calculated_price, tracker_buy_price)
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
        is_long_term = stock_code in self.long_trade_code
        
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
        else:
            high_decline_rate = 0
        
        return True, f"익절 조건 만족: 수익률 {profit_rate:.2%}, 고점 대비 {high_decline_rate:.2%} 하락"

    def should_sell_for_loss(self, stock_code, current_price, trade_price):
        """손절 조건 판단"""
        
        if trade_price <= 0:
            return False, "매수가 정보 없음"
        
        # 손실률 계산
        loss_rate = (current_price - trade_price) / trade_price
        
        # 종목 타입에 따른 손절 기준 설정
        is_long_term = stock_code in self.long_trade_code
        target_loss = -0.10 if is_long_term else -0.05  # 장기: -10%, 일반: -5%
        
        if loss_rate <= target_loss:
            return True, f"손절 조건: {loss_rate:.2%} <= {target_loss:.2%}"
        
        return False, f"손절 기준 미달: {loss_rate:.2%} > {target_loss:.2%}"

    # 🔥 시간대별 전략 메서드들
    async def observation_strategy(self, market_data):
        """09:00-09:30 관망 전략 - 기본 익절/손절만"""
        stock_code = market_data['stock_code']
        current_price = market_data['current_price']
        
        logger.debug(f"👀 [관망시간] {stock_code} - 현재가: {current_price:,}원, 코스피: {self.kospi_index}%")
        
        # 보유주식에 대한 기본 익절/손절만 실행
        if stock_code in self.holding_stock:
            await self.basic_sell_logic(stock_code, market_data)
        
        # 코스피 -3% 이상 하락시에만 매수 (long_trade_data 기준)
        elif self.kospi_index <= -3.0 and stock_code in self.long_trade_data:
            await self.emergency_buy_logic(stock_code, market_data)

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

    # 🔥 유틸리티 함수들
    def get_long_trade_status(self, stock_code):
        """종목의 장기거래 여부 확인"""
        return stock_code in self.long_trade_code

    async def log_trading_decision(self, stock_code, action, reason, market_data):
        """거래 의사결정 로깅"""
        current_price = market_data['current_price']
        open_price = market_data['open_price']
        high_price = market_data['high_price']
        low_price = market_data['low_price']
        
        price_change = ((current_price - open_price) / open_price * 100) if open_price > 0 else 0
        
        logger.info(f"📋 [{action}] {stock_code}")
        logger.info(f"   💰 현재가: {current_price:,}원 (시가 대비 {price_change:+.2f}%)")
        logger.info(f"   📊 고가: {high_price:,}원, 저가: {low_price:,}원")
        logger.info(f"   📈 코스피: {self.kospi_index}%")
        logger.info(f"   📝 사유: {reason}")

    def validate_market_data(self, market_data):
        """시장 데이터 유효성 검사"""
        required_fields = ['stock_code', 'current_price', 'open_price', 'high_price', 'low_price']
        
        for field in required_fields:
            if field not in market_data or market_data[field] <= 0:
                logger.warning(f"⚠️ 유효하지 않은 시장 데이터: {field} = {market_data.get(field, 'None')}")
                return False
        
        return True

    # 🔥 에러 처리 및 복구 함수들
    async def handle_trading_error(self, stock_code, action, error, market_data):
        """거래 오류 처리"""
        logger.error(f"❌ [{action}] {stock_code} 오류: {str(error)}")
        
        # 오류 타입별 복구 처리
        if "주문" in str(error):
            # 주문 관련 오류
            if stock_code in self.trade_done:
                self.trade_done.remove(stock_code)
                logger.info(f"🔄 거래완료 목록에서 제거: {stock_code}")
        
        elif "추적" in str(error):
            # 추적 데이터 오류  
            try:
                if self.PT:
                    # 추적 데이터 재초기화 시도
                    await self.PT.initialize_tracking(
                        stock_code=stock_code,
                        current_price=market_data['current_price'],
                        trade_price=0,
                        period_type=False,
                        isfirst=False
                    )
                    logger.info(f"🔄 추적 데이터 재초기화: {stock_code}")
            except Exception as e:
                logger.error(f"❌ 추적 데이터 재초기화 실패: {str(e)}")

    def get_market_status_summary(self):
        """현재 시장 상태 요약"""
        return {
            'kospi_index': self.kospi_index,
            'kosdaq_index': self.kosdaq_index,
            'holding_stocks': len(self.holding_stock),
            'trade_targets': len(self.long_trade_code),
            'completed_trades': len(self.trade_done),
            'deposit': getattr(self.processor, 'deposit', 0)
        }

    def get_trading_statistics(self):
        """거래 통계 정보"""
        stats = {
            'total_holdings': len(self.holding_stock),
            'total_targets': len(self.long_trade_code),
            'completed_today': len(self.trade_done),
            'long_term_holdings': len([code for code in self.holding_stock if code in self.long_trade_code]),
            'short_term_holdings': len([code for code in self.holding_stock if code not in self.long_trade_code])
        }
        return stats

    async def reset_daily_trading_data(self):
        """일일 거래 데이터 초기화"""
        try:
            # trade_done 리스트 초기화
            if hasattr(self.processor, 'trade_done'):
                self.processor.trade_done.clear()
                
            logger.info("🔄 일일 거래 데이터 초기화 완료")
            
        except Exception as e:
            logger.error(f"❌ 일일 거래 데이터 초기화 실패: {str(e)}")

    def is_trading_time(self):
        """현재가 거래 시간인지 확인"""
        kst = pytz.timezone('Asia/Seoul')
        now = datetime.now(kst)
        now_time = now.time()
        
        time_0900 = datetime_time(9, 0)
        time_1530 = datetime_time(15, 30)
        
        return time_0900 <= now_time <= time_1530

    def get_current_trading_phase(self):
        """현재 거래 단계 반환"""
        kst = pytz.timezone('Asia/Seoul')
        now = datetime.now(kst)
        now_time = now.time()
        
        return self.determine_trading_state(now_time)

    async def emergency_stop_all_trading(self):
        """긴급 거래 중단"""
        try:
            logger.warning("🚨 긴급 거래 중단 신호 수신")
            self.running = False
            
            # 진행 중인 거래 정리
            if self.trade_done:
                logger.info(f"📋 거래 완료 목록 정리: {len(self.trade_done)}개")
                self.trade_done.clear()
            
            logger.warning("🛑 모든 거래 활동 중단 완료")
            
        except Exception as e:
            logger.error(f"❌ 긴급 중단 처리 중 오류: {str(e)}")

    def __str__(self):
        """Trading_Handler 상태 정보 문자열 표현"""
        phase = self.get_current_trading_phase()
        stats = self.get_trading_statistics()
        
        return (f"Trading_Handler(phase={phase}, "
                f"kospi={self.kospi_index}%, "
                f"holdings={stats['total_holdings']}, "
                f"targets={stats['total_targets']}, "
                f"completed={stats['completed_today']})")

    def __repr__(self):
        """Trading_Handler 디버그 정보"""
        return self.__str__()