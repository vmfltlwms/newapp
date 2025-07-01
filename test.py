# smart_trading_service.py - 새로운 전략 기반 개선 버전

import logging
from datetime import datetime, time as datetime_time
from dataclasses import dataclass
import pytz
from dependency_injector.wiring import inject, Provide
from container.redis_container import Redis_Container
from db.redis_db import RedisDB

logger = logging.getLogger(__name__)


@dataclass
class TradingConstants:
    """거래 관련 상수들 - 새로운 전략"""
    # 홀딩 존
    HOLDING_ZONE_THRESHOLD: float = 2.0  # ±2%
    
    # 시간대별 구분
    GAP_TRADING_START: datetime_time = datetime_time(9, 5)
    GAP_TRADING_END: datetime_time = datetime_time(9, 30)
    MAIN_TRADING_START: datetime_time = datetime_time(9, 30)
    MAIN_TRADING_END: datetime_time = datetime_time(13, 0)
    AFTERNOON_START: datetime_time = datetime_time(13, 0)
    AFTERNOON_END: datetime_time = datetime_time(14, 40)
    FORCE_SELL_TIME: datetime_time = datetime_time(14, 40)
    
    # 갭상승 매수 조건
    GAP_EXECUTION_STRENGTH_MIN: float = 150.0
    GAP_OPEN_RISE_MIN: float = 1.0  # 시가 대비 1% 이상
    GAP_TRADE_AMOUNT_MIN: int = 100000000  # 1억원
    
    # 오후 매도 조건
    AFTERNOON_HIGH_DROP_THRESHOLD: float = 1.0  # 13시 이후 최고가 대비 1% 하락
    AFTERNOON_BUY_DROP_THRESHOLD: float = 1.0   # 매수가 대비 1% 하락
    
    # 수익 실현 조건 (09:30~13:00)
    PROFIT_ZONE_THRESHOLD: float = 2.0  # 2% 이상 상승
    TRAILING_STOP_THRESHOLD: float = 2.0  # 최고가 대비 2% 하락 시 매도
    PROFIT_RETURN_THRESHOLD: float = 2.0  # 매수가 +2% 되돌림 시 매도


@dataclass
class TradingSignal:
    """거래 신호 데이터 클래스"""
    action: str  # 'BUY', 'SELL', 'NEUTRAL'
    quantity: int
    reason: str
    confidence: float = 0.0
    time_zone: str = ""  # 시간대 정보 추가
    analysis_data: dict = None


class TimeZone:
    """시간대 구분"""
    GAP_TRADING = "GAP_TRADING"      # 09:05~09:30
    MAIN_TRADING = "MAIN_TRADING"    # 09:30~13:00
    AFTERNOON = "AFTERNOON"          # 13:00~15:00
    FORCE_SELL = "FORCE_SELL"        # 15:00 이후
    CLOSED = "CLOSED"                # 장 마감


class SmartTrading:
    """새로운 전략 기반 스마트 트레이딩 클래스"""
    
    @inject
    def __init__(self, 
                 kiwoom_module, 
                 price_tracker,
                 stock_data_analyzer,
                 redis_db: RedisDB = Provide[Redis_Container.redis_db]):
        self.kiwoom_module = kiwoom_module
        self.price_tracker = price_tracker
        self.stock_data_analyzer = stock_data_analyzer
        self.redis_db = redis_db
        self.constants = TradingConstants()
        self.timezone = pytz.timezone('Asia/Seoul')
        
    def safe_percentage_change(self, current: float, base: float) -> float:
        """안전한 퍼센트 변화율 계산"""
        if base == 0 or base is None or current is None:
            return 0.0
        return (current - base) / base * 100
    
    def get_current_time_zone(self, current_time: datetime = None) -> str:
        """현재 시간대 구분"""
        if current_time is None:
            current_time = datetime.now(self.timezone)
        
        current_time_only = current_time.time()
        
        if current_time_only >= self.constants.FORCE_SELL_TIME:
            return TimeZone.FORCE_SELL
        elif current_time_only >= self.constants.AFTERNOON_START:
            return TimeZone.AFTERNOON
        elif current_time_only >= self.constants.MAIN_TRADING_START:
            return TimeZone.MAIN_TRADING
        elif current_time_only >= self.constants.GAP_TRADING_START:
            return TimeZone.GAP_TRADING
        else:
            return TimeZone.CLOSED
    
    async def get_daily_trade_count(self, stock_code: str) -> int:
        """일일 거래 횟수 조회"""
        try:
            today_key = f"daily_trade_count:{stock_code}:{datetime.now(self.timezone).strftime('%Y%m%d')}"
            count = await self.redis_db.get(today_key)
            return int(count) if count else 0
        except Exception as e:
            logger.error(f"[{stock_code}] 일일 거래 횟수 조회 오류: {e}")
            return 0
    
    async def increment_daily_trade_count(self, stock_code: str) -> None:
        """일일 거래 횟수 증가"""
        try:
            today_key = f"daily_trade_count:{stock_code}:{datetime.now(self.timezone).strftime('%Y%m%d')}"
            await self.redis_db.incr(today_key)
            await self.redis_db.expire(today_key, 86400)  # 24시간 만료
        except Exception as e:
            logger.error(f"[{stock_code}] 일일 거래 횟수 증가 오류: {e}")
    
    async def get_13h_highest_price(self, stock_code: str) -> float:
        """13시 이후 최고가 조회"""
        try:
            today_key = f"13h_highest:{stock_code}:{datetime.now(self.timezone).strftime('%Y%m%d')}"
            highest = await self.redis_db.get(today_key)
            return float(highest) if highest else 0.0
        except Exception as e:
            logger.error(f"[{stock_code}] 13시 이후 최고가 조회 오류: {e}")
            return 0.0
    
    async def update_13h_highest_price(self, stock_code: str, current_price: float) -> None:
        """13시 이후 최고가 업데이트"""
        try:
            today_key = f"13h_highest:{stock_code}:{datetime.now(self.timezone).strftime('%Y%m%d')}"
            current_highest = await self.get_13h_highest_price(stock_code)
            
            if current_price > current_highest:
                await self.redis_db.set(today_key, str(current_price))
                await self.redis_db.expire(today_key, 86400)  # 24시간 만료
                logger.debug(f"[{stock_code}] 13시 이후 최고가 업데이트: {current_highest} → {current_price}")
        except Exception as e:
            logger.error(f"[{stock_code}] 13시 이후 최고가 업데이트 오류: {e}")
    
    async def get_5min_trade_amount(self, stock_code: str) -> int:
        """5분간 누적 거래대금 조회"""
        try:
            analysis_data = await self.stock_data_analyzer.get_recent_0b_data(stock_code, 300)  # 5분
            if not analysis_data:
                return 0
            
            total_amount = 0
            for data in analysis_data[-60:]:  # 최근 5분간 데이터 (약 60개 정도)
                amount = data.get('instant_amount', 0)
                if amount > 0:
                    total_amount += amount
            
            return total_amount
        except Exception as e:
            logger.error(f"[{stock_code}] 5분간 거래대금 조회 오류: {e}")
            return 0
    
    async def check_gap_trading_conditions(self, stock_code: str, analysis_data: dict) -> bool:
        """갭상승 매수 조건 확인"""
        try:
            latest_data = analysis_data.get("latest_data", {})
            
            # 체결강도 확인
            execution_strength = latest_data.get('execution_strength', 0)
            if execution_strength < self.constants.GAP_EXECUTION_STRENGTH_MIN:
                return False
            
            # 시가 대비 상승률 확인
            current_price = latest_data.get('current_price', 0)
            open_price = latest_data.get('open_price', 0)
            if open_price > 0:
                open_rise = self.safe_percentage_change(current_price, open_price)
                if open_rise < self.constants.GAP_OPEN_RISE_MIN:
                    return False
            else:
                return False
            
            # 5분간 거래대금 확인
            trade_amount = await self.get_5min_trade_amount(stock_code)
            if trade_amount < self.constants.GAP_TRADE_AMOUNT_MIN:
                return False
            
            logger.info(f"[{stock_code}] 갭상승 조건 충족: 체결강도={execution_strength}, "
                       f"시가상승={open_rise:.2f}%, 거래대금={trade_amount:,}원")
            return True
            
        except Exception as e:
            logger.error(f"[{stock_code}] 갭상승 조건 확인 오류: {e}")
            return False
    
    async def check_main_trading_conditions(self, stock_code: str, analysis_data: dict) -> int:
        """메인 시간대 매매 조건 확인 (기존 로직 활용)"""
        try:
            # 기존 StockDataAnalyzer 기반 신호 생성 로직 활용
            analysis_1min = analysis_data.get("analysis_1min", {})
            analysis_5min = analysis_data.get("analysis_5min", {})
            latest_data = analysis_data.get("latest_data", {})
            
            strength_1min = analysis_1min.get('execution_strength', 0)
            strength_5min = analysis_5min.get('execution_strength', 0)
            momentum_1min = analysis_1min.get('momentum', {}).get('momentum', 'FLAT')
            buy_ratio_1min = analysis_1min.get('buy_ratio', 50)
            
            # 신호 강도 계산 (간소화)
            if strength_1min > 120 and momentum_1min == 'UP' and buy_ratio_1min > 60:
                return 3  # 강한 매수
            elif strength_1min > 100 and buy_ratio_1min > 55:
                return 2  # 일반 매수
            elif strength_1min < 80 and momentum_1min == 'DOWN' and buy_ratio_1min < 40:
                return -2  # 매도
            else:
                return 0  # 중립
                
        except Exception as e:
            logger.error(f"[{stock_code}] 메인 거래 조건 확인 오류: {e}")
            return 0
    
    async def check_holding_zone(self, stock_code: str, current_price: float, tracking_data: dict) -> bool:
        """홀딩 존 확인 (±2%)"""
        try:
            trade_price = tracking_data.get('trade_price', 0)
            if trade_price <= 0:
                return False
            
            change_rate = self.safe_percentage_change(current_price, trade_price)
            in_holding_zone = abs(change_rate) <= self.constants.HOLDING_ZONE_THRESHOLD
            
            logger.debug(f"[{stock_code}] 홀딩존 확인: 변화율={change_rate:.2f}%, 홀딩존={in_holding_zone}")
            return in_holding_zone
            
        except Exception as e:
            logger.error(f"[{stock_code}] 홀딩존 확인 오류: {e}")
            return True  # 에러시 안전하게 홀딩
    
    async def check_profit_zone_conditions(self, stock_code: str, current_price: float, tracking_data: dict) -> tuple:
        """수익 구간 매도 조건 확인"""
        try:
            trade_price = tracking_data.get('trade_price', 0)
            highest_after_buy = tracking_data.get('highest_price', 0)
            
            if trade_price <= 0:
                return False, ""
            
            current_change = self.safe_percentage_change(current_price, trade_price)
            
            # 2% 이상 상승했는지 확인
            if current_change >= self.constants.PROFIT_ZONE_THRESHOLD:
                # 최고가 대비 2% 하락 확인
                if highest_after_buy > 0:
                    drop_from_high = self.safe_percentage_change(current_price, highest_after_buy)
                    if drop_from_high <= -self.constants.TRAILING_STOP_THRESHOLD:
                        return True, f"트레일링 스톱: 최고가 대비 {drop_from_high:.2f}% 하락"
                
                # 매수가 +2% 되돌림 확인
                profit_target = trade_price * (1 + self.constants.PROFIT_RETURN_THRESHOLD / 100)
                if current_price <= profit_target and current_change >= self.constants.PROFIT_RETURN_THRESHOLD:
                    return True, f"수익 확정: 매수가 +{self.constants.PROFIT_RETURN_THRESHOLD}% 되돌림"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"[{stock_code}] 수익구간 조건 확인 오류: {e}")
            return False, ""
    
    async def check_afternoon_sell_conditions(self, stock_code: str, current_price: float, tracking_data: dict) -> tuple:
        """오후 매도 조건 확인"""
        try:
            trade_price = tracking_data.get('trade_price', 0)
            
            # 13시 이후 최고가 대비 1% 하락 확인
            highest_13h = await self.get_13h_highest_price(stock_code)
            if highest_13h > 0:
                drop_from_13h_high = self.safe_percentage_change(current_price, highest_13h)
                if drop_from_13h_high <= -self.constants.AFTERNOON_HIGH_DROP_THRESHOLD:
                    return True, f"13시 이후 최고가 대비 {drop_from_13h_high:.2f}% 하락"
            
            # 매수가 대비 1% 하락 확인
            if trade_price > 0:
                drop_from_buy = self.safe_percentage_change(current_price, trade_price)
                if drop_from_buy <= -self.constants.AFTERNOON_BUY_DROP_THRESHOLD:
                    return True, f"매수가 대비 {drop_from_buy:.2f}% 하락 손절"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"[{stock_code}] 오후 매도 조건 확인 오류: {e}")
            return False, ""
    
    async def generate_trading_signal(self, stock_code: str) -> TradingSignal:
        """새로운 전략 기반 거래 신호 생성"""
        try:
            # 1. 현재 시간대 확인
            time_zone = self.get_current_time_zone()
            
            # 2. 일일 거래 횟수 확인
            daily_count = await self.get_daily_trade_count(stock_code)
            if daily_count >= 1:  # 일일 1회 제한
                return TradingSignal("NEUTRAL", 0, "일일 거래 횟수 초과", time_zone=time_zone)
            
            # 3. 분석 데이터 조회
            analysis_data = await self.stock_data_analyzer.analyze_stock_0b(stock_code)
            if not analysis_data or "error" in analysis_data:
                return TradingSignal("NEUTRAL", 0, "분석 데이터 없음", time_zone=time_zone)
            
            # 4. 현재가 및 추적 데이터 조회
            current_price = analysis_data.get("latest_data", {}).get("current_price", 0)
            tracking_data = await self.price_tracker.get_tracking_data(stock_code)
            
            if not tracking_data:
                tracking_data = {}
            
            qty_to_sell = tracking_data.get('qty_to_sell', 0)
            qty_to_buy = tracking_data.get('qty_to_buy', 0)
            
            # 5. 시간대별 로직 처리
            if time_zone == TimeZone.FORCE_SELL:
                # 15:00 이후 - 전량 매도
                if qty_to_sell > 0:
                    return TradingSignal("SELL", qty_to_sell, "15시 이후 강제 청산", time_zone=time_zone, analysis_data=analysis_data)
                return TradingSignal("NEUTRAL", 0, "매도할 물량 없음", time_zone=time_zone)
            
            elif time_zone == TimeZone.CLOSED:
                return TradingSignal("NEUTRAL", 0, "장 마감", time_zone=time_zone)
            
            elif time_zone == TimeZone.GAP_TRADING:
                # 09:05~09:30 - 갭상승 매수만
                if qty_to_buy > 0:
                    if await self.check_gap_trading_conditions(stock_code, analysis_data):
                        return TradingSignal("BUY", qty_to_buy, "갭상승 매수 조건 충족", time_zone=time_zone, analysis_data=analysis_data)
                return TradingSignal("NEUTRAL", 0, "갭상승 조건 미충족", time_zone=time_zone)
            
            elif time_zone == TimeZone.MAIN_TRADING:
                # 09:30~13:00 - 메인 거래 + 홀딩존 + 수익실현
                
                # 보유 중일 때 홀딩존 확인
                if qty_to_sell > 0:
                    in_holding_zone = await self.check_holding_zone(stock_code, current_price, tracking_data)
                    
                    if in_holding_zone:
                        # 홀딩존 내에서는 수익실현 조건만 확인
                        should_sell, reason = await self.check_profit_zone_conditions(stock_code, current_price, tracking_data)
                        if should_sell:
                            return TradingSignal("SELL", qty_to_sell, reason, time_zone=time_zone, analysis_data=analysis_data)
                        return TradingSignal("NEUTRAL", 0, "홀딩존 내 보유", time_zone=time_zone)
                    else:
                        # 홀딩존 벗어난 경우 (±2% 이상)
                        change_rate = self.safe_percentage_change(current_price, tracking_data.get('trade_price', 0))
                        if change_rate > self.constants.HOLDING_ZONE_THRESHOLD:
                            # 2% 이상 상승 - 수익실현 조건 확인
                            should_sell, reason = await self.check_profit_zone_conditions(stock_code, current_price, tracking_data)
                            if should_sell:
                                return TradingSignal("SELL", qty_to_sell, reason, time_zone=time_zone, analysis_data=analysis_data)
                        # 2% 이상 하락은 일단 홀드 (손절은 오후에만)
                
                # 매수 조건 확인
                if qty_to_buy > 0:
                    signal_strength = await self.check_main_trading_conditions(stock_code, analysis_data)
                    if signal_strength >= 2:
                        return TradingSignal("BUY", qty_to_buy, f"메인 매수 신호: {signal_strength}", time_zone=time_zone, analysis_data=analysis_data)
                
                return TradingSignal("NEUTRAL", 0, "메인 거래 조건 미충족", time_zone=time_zone)
            
            elif time_zone == TimeZone.AFTERNOON:
                # 13:00~15:00 - 매수 금지, 매도만
                
                # 13시 이후 최고가 업데이트
                await self.update_13h_highest_price(stock_code, current_price)
                
                if qty_to_sell > 0:
                    should_sell, reason = await self.check_afternoon_sell_conditions(stock_code, current_price, tracking_data)
                    if should_sell:
                        return TradingSignal("SELL", qty_to_sell, reason, time_zone=time_zone, analysis_data=analysis_data)
                
                return TradingSignal("NEUTRAL", 0, "오후 매도 조건 미충족", time_zone=time_zone)
            
            return TradingSignal("NEUTRAL", 0, "알 수 없는 시간대", time_zone=time_zone)
            
        except Exception as e:
            logger.error(f"[{stock_code}] 거래 신호 생성 오류: {e}")
            return TradingSignal("NEUTRAL", 0, f"오류 발생: {str(e)}")
    
    async def execute_trade_order(self, stock_code: str) -> bool:
        """거래 주문 실행"""
        try:
            # 거래 신호 생성
            signal = await self.generate_trading_signal(stock_code)
            
            if signal.action == "NEUTRAL" or signal.quantity <= 0:
                logger.debug(f"[{stock_code}] 거래 신호 없음: {signal.reason}")
                return False
            
            # 현재가 조회 - get_price_info 사용
            price_info = await self.price_tracker.get_price_info(stock_code)
            if not price_info or price_info.get('current_price', 0) <= 0:
                logger.error(f"[{stock_code}] 현재가 조회 실패")
                return False
            
            current_price = price_info['current_price']
            
            # 주문 실행
            if signal.action == "BUY":
                result = await self._execute_buy_order(stock_code, signal.quantity, current_price)
            else:  # SELL
                result = await self._execute_sell_order(stock_code, signal.quantity, current_price)
            
            if result:
                await self.increment_daily_trade_count(stock_code)
                logger.info(f"✅ [{stock_code}] {signal.action} 주문 성공: {signal.quantity}주 @ {current_price} - {signal.reason}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ [{stock_code}] 주문 실행 예외: {e}")
            return False
        
    async def _execute_buy_order(self, stock_code: str, quantity: int, current_price: float) -> bool:
        """매수 주문 실행"""
        try:
            logger.info(f"[{stock_code}] 매수 주문: {quantity}주 @ {current_price}")
            
            result = await self.kiwoom_module.order_stock_buy(
                dmst_stex_tp="KRX",
                stk_cd=stock_code,
                ord_qty=str(quantity),
                ord_uv="",  # 시장가
                trde_tp="3",  # 시장가 주문
                cond_uv=""
            )
            
            return result and result.get('return_code') == 0
            
        except Exception as e:
            logger.error(f"매수 주문 실행 오류: {e}")
            return False
    
    async def _execute_sell_order(self, stock_code: str, quantity: int, current_price: float) -> bool:
        """매도 주문 실행"""
        try:
            logger.info(f"[{stock_code}] 매도 주문: {quantity}주 @ {current_price}")
            
            result = await self.kiwoom_module.order_stock_sell(
                dmst_stex_tp="KRX",
                stk_cd=stock_code,
                ord_qty=str(quantity),
                ord_uv="",  # 시장가
                trde_tp="3",  # 시장가 주문
                cond_uv=""
            )
            
            return result and result.get('return_code') == 0
            
        except Exception as e:
            logger.error(f"매도 주문 실행 오류: {e}")
            return False
    
    async def get_trading_status(self, stock_code: str) -> dict:
        """종목의 현재 거래 상태 조회"""
        try:
            # 현재 시간대
            time_zone = self.get_current_time_zone()
            
            # 일일 거래 횟수
            daily_count = await self.get_daily_trade_count(stock_code)
            
            # 분석 데이터
            analysis_data = await self.stock_data_analyzer.analyze_stock_0b(stock_code)
            
            # 추적 데이터
            tracking_data = await self.price_tracker.get_tracking_data(stock_code)
            
            # 13시 이후 최고가
            highest_13h = await self.get_13h_highest_price(stock_code)
            
            # 거래 신호
            signal = await self.generate_trading_signal(stock_code)
            
            return {
                "stock_code": stock_code,
                "time_zone": time_zone,
                "daily_trade_count": daily_count,
                "highest_after_13h": highest_13h,
                "signal": {
                    "action": signal.action,
                    "quantity": signal.quantity,
                    "reason": signal.reason,
                    "time_zone": signal.time_zone
                },
                "tracking_data": tracking_data or {},
                "analysis_summary": {
                    "has_data": bool(analysis_data and "error" not in analysis_data),
                    "execution_strength": analysis_data.get("latest_data", {}).get("execution_strength", 0) if analysis_data else 0,
                    "current_price": analysis_data.get("latest_data", {}).get("current_price", 0) if analysis_data else 0
                },
                "timestamp": datetime.now(self.timezone).isoformat()
            }
            
        except Exception as e:
            logger.error(f"[{stock_code}] 거래 상태 조회 오류: {e}")
            return {
                "stock_code": stock_code,
                "error": str(e),
                "timestamp": datetime.now(self.timezone).isoformat()
            }