# smart_trading_service.py - 완전히 새로 작성된 버전

import logging
from datetime import datetime, time as datetime_time
from dataclasses import dataclass
import time
from dependency_injector.wiring import inject, Provide
from container.redis_container import Redis_Container
from db.redis_db import RedisDB
from zoneinfo import ZoneInfo  # Python 3.9+

logger = logging.getLogger(__name__)


@dataclass
class TradingConstants:
    """거래 관련 상수들"""
    # 홀딩 존
    HOLDING_ZONE_THRESHOLD: float = 2.0  # ±2%
    
    # 시간대별 구분 (한국시간)
    MONITOR_START: datetime_time = datetime_time(9, 0)   # 09:00
    MONITOR_END: datetime_time = datetime_time(9, 5)     # 09:05
    GAP_TRADING_START: datetime_time = datetime_time(9, 5)   # 09:05
    GAP_TRADING_END: datetime_time = datetime_time(9, 30)    # 09:30
    MAIN_TRADING_START: datetime_time = datetime_time(9, 30) # 09:30
    MAIN_TRADING_END: datetime_time = datetime_time(13, 0)   # 13:00
    AFTERNOON_START: datetime_time = datetime_time(13, 0)    # 13:00
    AFTERNOON_END: datetime_time = datetime_time(15, 0)      # 15:00
    
    # 갭상승 매수 조건 (09:05~09:30)
    GAP_EXECUTION_STRENGTH_MIN: float = 150.0           # 체결강도 150 이상
    GAP_AVG_TRADE_AMOUNT_MIN: int = 100_000_000         # 5분간 평균거래대금 1억원 이상
    GAP_OPEN_RISE_MIN: float = 1.0                      # 시가 대비 1% 이상 상승
    
    # 갭상승 매도 조건 (09:05~09:30)
    GAP_HIGH_DROP_THRESHOLD: float = 2.0                # 최고가 대비 2% 하락
    GAP_BUY_DROP_THRESHOLD: float = 1.0                 # 매수가 대비 1% 하락
    
    # 메인 거래 조건 (09:30~13:00) - 기존 로직 사용
    PROFIT_ZONE_THRESHOLD: float = 2.0                  # 2% 이상 상승
    TRAILING_STOP_THRESHOLD: float = 2.0                # 최고가 대비 2% 하락 시 매도
    PROFIT_RETURN_THRESHOLD: float = 2.0                # 매수가 +2% 되돌림 시 매도
    
    # 오후 매도 조건 (13:00~15:00)
    AFTERNOON_HIGH_DROP_THRESHOLD: float = 1.0          # 13시 이후 최고가 대비 1% 하락
    AFTERNOON_BUY_DROP_THRESHOLD: float = 1.0           # 매수가 대비 1% 하락
    
    # 데이터 에러 기반 매도 조건 (삭제됨)
    # ERROR_DURATION_THRESHOLD: int = 300


@dataclass
class TradingSignal:
    """거래 신호 데이터 클래스"""
    action: str  # 'BUY', 'SELL', 'NEUTRAL'
    quantity: int
    reason: str
    confidence: float = 0.0
    time_zone: str = ""
    analysis_data: dict = None


class TimeZone:
    """시간대 구분"""
    MONITOR = "MONITOR"                  # 09:00~09:05 모니터링
    GAP_TRADING = "GAP_TRADING"          # 09:05~09:30 갭상승 매수
    MAIN_TRADING = "MAIN_TRADING"        # 09:30~13:00 메인 거래
    AFTERNOON = "AFTERNOON"              # 13:00~15:00 오후 거래
    CLOSED = "CLOSED"                    # 장 마감


class SmartTrading:
    """스마트 트레이딩 클래스 - 완전히 새로 작성된 버전"""
    
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
    
    def safe_percentage_change(self, current: float, base: float) -> float:
        """안전한 퍼센트 변화율 계산"""
        if base == 0 or base is None or current is None:
            return 0.0
        return (current - base) / base * 100
    
    def get_current_time_zone(self) -> str:
        """현재 시간대 구분"""
        current_time = datetime.now(ZoneInfo("Asia/Seoul"))
        
        # datetime.datetime에서 time 부분만 추출하여 비교
        current_time_only = current_time.time()
        
        if current_time_only >= self.constants.AFTERNOON_START:
            return TimeZone.AFTERNOON
        elif current_time_only >= self.constants.MAIN_TRADING_START:
            return TimeZone.MAIN_TRADING
        elif current_time_only >= self.constants.GAP_TRADING_START:
            return TimeZone.GAP_TRADING
        elif current_time_only >= self.constants.MONITOR_START:
            return TimeZone.MONITOR
        else:
            return TimeZone.CLOSED
    
    async def is_daily_trade_completed(self, stock_code: str) -> bool:
        """
        일일 거래 완료 여부 확인
        
        완료 조건:
        1. qty_to_sell = 0 (매도할 물량이 모두 소진됨)
        2. trade_type = "SELL" (마지막 거래가 매도였음)
        
        Returns:
            bool: 일일 거래 완료 여부
        """
        try:
            tracking_data = await self.price_tracker.get_tracking_data(stock_code)
            
            if not tracking_data:
                logger.debug(f"[{stock_code}] 추적 데이터가 없습니다 - 거래 미완료")
                return False
            
            qty_to_sell = tracking_data.get('qty_to_sell', 0)
            trade_type = tracking_data.get('trade_type', 'HOLD')
            
            # 완료 조건: 매도 완료 (qty_to_sell=0 + trade_type="SELL")
            is_completed = (qty_to_sell == 0 and trade_type == "SELL")
            
            if is_completed:
                logger.info(f"[{stock_code}] ✅ 일일 거래 완료 - 매수/매도 모두 완료")
                
            else:
                logger.debug(f"[{stock_code}] ⏳ 거래 진행 중 - qty_to_sell: {qty_to_sell}, trade_type: {trade_type}")
            
            return is_completed
            
        except Exception as e:
            logger.error(f"[{stock_code}] 일일 거래 완료 확인 오류: {e}")
            return False
    
    async def get_5min_average_trade_amount(self, stock_code: str) -> int:
        """
        5분간 평균 거래대금 조회 
        
        계산법: (09:00부터 현재까지 누적거래대금 / 거래시간) * 5분
        
        Returns:
            int: 5분간 평균 거래대금 (원)
        """
        try:
            # 최신 0B 원시 데이터 조회
            data_list = await self.stock_data_analyzer.get_recent_0b_data(stock_code, 60)  # 1분간 데이터
            if not data_list:
                logger.debug(f"[{stock_code}] 0B 데이터 없음")
                return 0
            
            # 가장 최신 데이터에서 누적거래대금 조회
            latest_data = data_list[-1]
            acc_amount = latest_data.get("acc_amount", 0)  # 파싱된 데이터의 acc_amount 사용
            
            if acc_amount <= 0:
                logger.debug(f"[{stock_code}] 누적거래대금 없음: {acc_amount}")
                return 0
            
            # 현재 시간 (09:00부터 경과 시간 계산)
            current_time = datetime.now(ZoneInfo("Asia/Seoul")).time()
            market_start = datetime_time(9, 0)  # 09:00
            
            # 경과 시간 계산 (분 단위)
            if current_time < market_start:
                logger.debug(f"[{stock_code}] 장 시작 전")
                return 0
            
            # 시간 차이를 분으로 계산
            current_minutes = current_time.hour * 60 + current_time.minute
            start_minutes = market_start.hour * 60 + market_start.minute
            elapsed_minutes = current_minutes - start_minutes
            
            if elapsed_minutes <= 0:
                logger.debug(f"[{stock_code}] 경과 시간 없음: {elapsed_minutes}분")
                return 0
            
            # 5분간 평균 거래대금 계산
            # (누적거래대금 / 경과시간) * 5분
            avg_per_minute = acc_amount / elapsed_minutes
            avg_5min = int(avg_per_minute * 5)
            
            logger.debug(f"[{stock_code}] 5분간 평균 거래대금: {avg_5min:,}원 "
                        f"(누적: {acc_amount:,}, 경과: {elapsed_minutes}분)")
            return avg_5min
            
        except Exception as e:
            logger.error(f"[{stock_code}] 5분간 평균 거래대금 조회 오류: {e}")
            return 0
    
    async def check_gap_trading_conditions(self, stock_code: str, analysis_data: dict) -> bool:
        """
        갭상승 매수 조건 확인 (09:05~09:30)
        
        조건:
        1. 체결강도 150 이상
        2. 5분간 평균 거래대금 1억원 이상  
        3. 시가 대비 현재가 1% 이상 상승
        """
        try:
            latest_data = analysis_data.get("latest_data", {})
            
            # 1. 체결강도 확인
            execution_strength = latest_data.get('execution_strength', 0)
            if execution_strength < self.constants.GAP_EXECUTION_STRENGTH_MIN:
                logger.debug(f"[{stock_code}] 체결강도 부족: {execution_strength} < {self.constants.GAP_EXECUTION_STRENGTH_MIN}")
                return False
            
            # 2. 5분간 평균 거래대금 확인
            avg_trade_amount = await self.get_5min_average_trade_amount(stock_code)
            if avg_trade_amount < self.constants.GAP_AVG_TRADE_AMOUNT_MIN:
                logger.debug(f"[{stock_code}] 거래대금 부족: {avg_trade_amount:,} < {self.constants.GAP_AVG_TRADE_AMOUNT_MIN:,}")
                return False
            
            # 3. 시가 대비 상승률 확인
            current_price = latest_data.get('current_price', 0)
            open_price = latest_data.get('open_price', 0)
            
            if open_price <= 0:
                logger.debug(f"[{stock_code}] 시가 데이터 없음: {open_price}")
                return False
            
            open_rise = self.safe_percentage_change(current_price, open_price)
            if open_rise < self.constants.GAP_OPEN_RISE_MIN:
                logger.debug(f"[{stock_code}] 시가 상승률 부족: {open_rise:.2f}% < {self.constants.GAP_OPEN_RISE_MIN}%")
                return False
            
            logger.info(f"[{stock_code}] ✅ 갭상승 조건 충족: 체결강도={execution_strength:.1f}, "
                       f"거래대금={avg_trade_amount:,}원, 시가상승={open_rise:.2f}%")
            return True
            
        except Exception as e:
            logger.error(f"[{stock_code}] 갭상승 조건 확인 오류: {e}")
            return False
    
    async def check_gap_sell_conditions(self, stock_code: str, current_price: float, tracking_data: dict) -> tuple:
        """
        갭상승 매도 조건 확인 (09:05~09:30)
        
        조건:
        1. 최고가 대비 2% 하락
        2. 매수가 대비 1% 하락
        """
        try:
            trade_price = tracking_data.get('trade_price', 0)
            highest_price = tracking_data.get('highest_price', 0)
            
            if trade_price <= 0:
                return False, "매수가 정보 없음"
            
            # 1. 최고가 대비 2% 하락 확인
            if highest_price > 0:
                drop_from_high = self.safe_percentage_change(current_price, highest_price)
                if drop_from_high <= -self.constants.GAP_HIGH_DROP_THRESHOLD:
                    return True, f"최고가 대비 {drop_from_high:.2f}% 하락"
            
            # 2. 매수가 대비 1% 하락 확인
            drop_from_buy = self.safe_percentage_change(current_price, trade_price)
            if drop_from_buy <= -self.constants.GAP_BUY_DROP_THRESHOLD:
                return True, f"매수가 대비 {drop_from_buy:.2f}% 하락"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"[{stock_code}] 갭상승 매도 조건 확인 오류: {e}")
            return False, "조건 확인 실패"
    
    async def check_main_trading_conditions(self, stock_code: str, analysis_data: dict) -> int:
        """메인 시간대 매매 조건 확인 (기존 로직 사용)"""
        try:
            analysis_1min = analysis_data.get("analysis_1min", {})
            
            strength_1min = analysis_1min.get('execution_strength', 0)
            momentum_1min = analysis_1min.get('momentum', {}).get('momentum', 'FLAT')
            buy_ratio_1min = analysis_1min.get('buy_ratio', 50)
            
            # 신호 강도 계산 (기존 로직)
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
        """홀딩 존 확인 (±2%) - 메인 거래 시간용"""
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
        """
        수익 구간 매도 조건 확인 - 메인 거래 시간용
        
        구간별 전략:
        - 4% 이상 상승: 트레일링 스톱만 (최고가 대비 2% 하락)
        - 2%~4% 상승: 수익 확정 우선 (매수가+2% 도달 시 매도)
        """
        try:
            trade_price = tracking_data.get('trade_price', 0)
            highest_price = tracking_data.get('highest_price', 0)
            
            if trade_price <= 0:
                return False, ""
            
            current_change = self.safe_percentage_change(current_price, trade_price)
            profit_target = trade_price * (1 + self.constants.PROFIT_RETURN_THRESHOLD / 100)  # 매수가 + 2%
            
            # 현재가가 매수가 대비 2% 이상 상승한 상태인지 확인
            if current_change >= self.constants.PROFIT_ZONE_THRESHOLD:
                
                if current_change >= 4.0:
                    # 4% 이상 상승 구간: 트레일링 스톱만
                    if highest_price > 0:
                        drop_from_high = self.safe_percentage_change(current_price, highest_price)
                        if drop_from_high <= -self.constants.TRAILING_STOP_THRESHOLD:
                            return True, f"트레일링 스톱 (4%+ 구간): 최고가 대비 {drop_from_high:.2f}% 하락"
                else:
                    # 2%~4% 상승 구간: 수익 확정 우선
                    if current_price <= profit_target:
                        return True, f"수익 확정 (2-4% 구간): 매수가+{self.constants.PROFIT_RETURN_THRESHOLD}% 지점 도달"
                    
                    # 트레일링 스톱도 체크
                    if highest_price > 0:
                        drop_from_high = self.safe_percentage_change(current_price, highest_price)
                        if drop_from_high <= -self.constants.TRAILING_STOP_THRESHOLD:
                            return True, f"트레일링 스톱 (2-4% 구간): 최고가 대비 {drop_from_high:.2f}% 하락"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"[{stock_code}] 수익구간 조건 확인 오류: {e}")
            return False, ""
    
    async def check_afternoon_sell_conditions(self, stock_code: str, current_price: float, tracking_data: dict) -> tuple:
        """
        오후 매도 조건 확인 (13:00~15:00)
        
        조건:
        1. 13시 이후 최고가 대비 1% 하락 (price_tracker의 highest_price 사용)
        2. 매수가 대비 1% 하락
        """
        try:
            trade_price = tracking_data.get('trade_price', 0)
            highest_price = tracking_data.get('highest_price', 0)  # 13시 이후 리셋된 최고가
            
            # 1. 13시 이후 최고가 대비 1% 하락 확인
            if highest_price > 0:
                drop_from_high = self.safe_percentage_change(current_price, highest_price)
                if drop_from_high <= -self.constants.AFTERNOON_HIGH_DROP_THRESHOLD:
                    return True, f"13시 이후 최고가 대비 {drop_from_high:.2f}% 하락"
            
            # 2. 매수가 대비 1% 하락 확인
            if trade_price > 0:
                drop_from_buy = self.safe_percentage_change(current_price, trade_price)
                if drop_from_buy <= -self.constants.AFTERNOON_BUY_DROP_THRESHOLD:
                    return True, f"매수가 대비 {drop_from_buy:.2f}% 하락 손절"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"[{stock_code}] 오후 매도 조건 확인 오류: {e}")
            return False, ""

    async def generate_trading_signal(self, stock_code: str) -> TradingSignal:
        """거래 신호 생성 - 완전히 새로 작성된 버전"""
        try:
            # 1. 현재 시간대 확인
            time_zone = self.get_current_time_zone()
            
            # 2. 일일 거래 완료 여부 확인
            is_completed = await self.is_daily_trade_completed(stock_code)
            if is_completed:
                return TradingSignal("NEUTRAL", 0, "일일 거래 완료", time_zone=time_zone)
            
            # 3. 추적 데이터 조회
            tracking_data = await self.price_tracker.get_tracking_data(stock_code)
            if not tracking_data:
                tracking_data = {}
            
            qty_to_sell = tracking_data.get('qty_to_sell', 0)
            qty_to_buy = tracking_data.get('qty_to_buy', 0)
            price_info = await self.price_tracker.get_price_info(stock_code)
            cur_pri = price_info.get('current_price',0)
            tra_pri = price_info.get('trade_price',0)
            logger.info(f"{stock_code}, {cur_pri} / {tra_pri} ,{qty_to_sell} ")
            # 4. 분석 데이터 조회
            analysis_data = await self.stock_data_analyzer.analyze_stock_0b(stock_code)
            
            # 5. 데이터 에러 처리 (삭제됨)
            if not analysis_data or "error" in analysis_data:
                return TradingSignal("NEUTRAL", 0, "데이터 없음", time_zone=time_zone)
            
            # 6. 현재가 확인
            current_price = tracking_data.get('current_price', 0)
            if current_price <= 0:
                return TradingSignal("NEUTRAL", 0, "현재가 정보 없음", time_zone=time_zone)
            
            
            # 8. 시간대별 거래 로직
            if time_zone == TimeZone.CLOSED:
                return TradingSignal("NEUTRAL", 0, "장 마감", time_zone=time_zone)
            
            elif time_zone == TimeZone.MONITOR:
                # 09:00~09:05 모니터링만
                return TradingSignal("NEUTRAL", 0, "모니터링 시간", time_zone=time_zone)
            
            elif time_zone == TimeZone.GAP_TRADING:
                # 09:05~09:30 갭상승 매수/매도
                
                # 매도 조건 확인 (보유 중일 때)
                if qty_to_sell > 0:
                    should_sell, reason = await self.check_gap_sell_conditions(stock_code, current_price, tracking_data)
                    if should_sell:
                        return TradingSignal("SELL", qty_to_sell, f"갭상승 {reason}", time_zone=time_zone, analysis_data=analysis_data)
                
                # 매수 조건 확인
                if qty_to_buy > 0:
                    if await self.check_gap_trading_conditions(stock_code, analysis_data):
                        return TradingSignal("BUY", qty_to_buy, "갭상승 매수 조건 충족", time_zone=time_zone, analysis_data=analysis_data)
                
                return TradingSignal("NEUTRAL", 0, "갭상승 조건 미충족", time_zone=time_zone)
            
            elif time_zone == TimeZone.MAIN_TRADING:
                # 09:30~13:00 메인 거래 (기존 로직 사용)
  
                if qty_to_sell > 0:
                    # 홀딩존 확인
                    in_holding_zone = await self.check_holding_zone(stock_code, current_price, tracking_data)
                    
                    
                    if in_holding_zone:
                        # 홀딩존 내에서는 아무것도 하지 않음 (보유 유지)
                        return TradingSignal("NEUTRAL", 0, "홀딩존 내 보유", time_zone=time_zone)
                    else:
                        # 홀딩존 벗어난 경우
                        change_rate = self.safe_percentage_change(current_price, tracking_data.get('trade_price', 0))
                        
                        if change_rate > self.constants.HOLDING_ZONE_THRESHOLD:
                            # 상승해서 홀딩존을 벗어난 경우: 수익실현 조건 확인
                            should_sell, reason = await self.check_profit_zone_conditions(stock_code, current_price, tracking_data)
                            if should_sell:
                                return TradingSignal("SELL", qty_to_sell, reason, time_zone=time_zone, analysis_data=analysis_data)
                            # 수익실현 조건 미충족시 계속 보유
                            return TradingSignal("NEUTRAL", 0, f"수익구간 보유 중 ({change_rate:.2f}%)", time_zone=time_zone)
                        
                        elif change_rate < -self.constants.HOLDING_ZONE_THRESHOLD:
                            # 하락해서 홀딩존을 벗어난 경우: 손절 실행
                            return TradingSignal("SELL", qty_to_sell, f"손절: 매수가 대비 {change_rate:.2f}% 하락", time_zone=time_zone, analysis_data=analysis_data)
                
                # 매수 조건 확인
                if qty_to_buy > 0:
                    signal_strength = await self.check_main_trading_conditions(stock_code, analysis_data)
                    if signal_strength >= 2:
                        return TradingSignal("BUY", qty_to_buy, f"메인 매수 신호: {signal_strength}", time_zone=time_zone, analysis_data=analysis_data)
                
                return TradingSignal("NEUTRAL", 0, "메인 거래 조건 미충족", time_zone=time_zone)
                # 매수 조건 확인

            
            elif time_zone == TimeZone.AFTERNOON:
                # 13:00~15:00 오후 거래 (매도만)
                
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
            
            # 현재가 조회
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
            time_zone = self.get_current_time_zone()
            is_completed = await self.is_daily_trade_completed(stock_code)
            analysis_data = await self.stock_data_analyzer.analyze_stock_0b(stock_code)
            tracking_data = await self.price_tracker.get_tracking_data(stock_code)
            signal = await self.generate_trading_signal(stock_code)
            
            return {
                "stock_code": stock_code,
                "time_zone": time_zone,
                "daily_trade_completed": is_completed,
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
                "timestamp": datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
            }
            
        except Exception as e:
            logger.error(f"[{stock_code}] 거래 상태 조회 오류: {e}")
            return {
                "stock_code": stock_code,
                "error": str(e),
                "timestamp": datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
            }