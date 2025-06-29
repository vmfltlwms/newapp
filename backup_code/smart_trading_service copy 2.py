# smart_trading_strategy.py - 오류 수정 버전

import logging
from datetime import datetime, time as datetime_time
import time as time_module
import pytz  # zoneinfo 대신 pytz 사용

logger = logging.getLogger(__name__)


class SmartTrading:
    
    def __init__(self,  kiwoom_module, PriceTracker):
        self.kiwoom_module = kiwoom_module
        self.PT = PriceTracker
        
    def safe_percentage_change(self, current, base):
        """안전한 퍼센트 변화율 계산"""
        if base == 0 or base is None or current is None:
            return 0
        return (current - base) / base * 100
      
    # 추세 방향 판단 (모두 분당 평균 기준으로 통일)
    def trend_direction(self, strength_1min,  strength_5min,  strength_day):
        # 단기와 장기 추세 비교
        short_vs_long = strength_1min - strength_5min
        long_vs_day = strength_5min - strength_day
        
        # 강한 상승: 단기 > 장기 > 하루평균, 차이가 큰 경우
        if strength_1min > strength_5min > strength_day and short_vs_long > 20:
            return "STRONG_RISING"
        # 상승: 단기 > 장기 또는 장기 > 하루평균
        elif strength_1min > strength_5min or (strength_5min > strength_day and long_vs_day > 10):
            return "RISING"
        # 강한 하락: 단기 < 장기 < 하루평균, 차이가 큰 경우  
        elif strength_1min < strength_5min < strength_day and short_vs_long < -20:
            return "STRONG_FALLING"
        # 하락: 단기 < 장기 또는 장기 < 하루평균
        elif strength_1min < strength_5min or (strength_5min < strength_day and long_vs_day < -10):
            return "FALLING"
        # 반등: 단기가 크게 상승했지만 하루평균은 낮은 경우
        elif strength_1min > strength_5min > strength_day and short_vs_long > 15:
            return "RISING"
        # 조정: 단기가 하락했지만 하루평균은 높은 경우
        elif strength_1min < strength_5min < strength_day and short_vs_long < -15:
            return "FALLING"
        else:
            return "STABLE"

    def strength_signal_processor(self, daily_strength, signal_trend) -> int:
        # 체결강도 기준별 시그널 매핑
        if daily_strength >= 110:
            strength_mapping = {
                'STRONG_RISING': 2,
                'RISING': 2,
                'STABLE': 0,
                'FALLING': -2,
                'STRONG_FALLING': -2
            }
        elif 90 <= daily_strength < 110:
            strength_mapping = {
                'STRONG_RISING': 2,
                'RISING': 1,
                'STABLE': 0,
                'FALLING': -2,
                'STRONG_FALLING': -2
            }
        else:  # daily_strength < 90
            strength_mapping = {
                'STRONG_RISING': 2,
                'RISING': 0,
                'STABLE': -1,
                'FALLING': -2,
                'STRONG_FALLING': -2
            }
        

        return strength_mapping.get(signal_trend, 0)

    async def trade_signal_processor( self, stock_code: str, current_price: int,  analysis: dict) -> dict:
        try:
            # None 체크 강화
            if not analysis:
                return {'action': 'NEUTRAL', 'quantity': 0}
                

            
            daily_data = analysis.get("latest_data", {})
            analysis_1min = analysis.get("analysis_1min", {})
            analysis_5min = analysis.get("analysis_5min", {}) 
            
            # 필수 데이터 체크
            if not all([daily_data, analysis_1min, analysis_5min]):
                return {'action': 'NEUTRAL', 'quantity': 0}
            
            short_strength = analysis_1min.get('execution_strength', 0)
            long_strength = analysis_5min.get('execution_strength', 0)
            daily_strength = daily_data.get('execution_strength', 0)
            
            signal_trend = self.trend_direction(short_strength, long_strength, daily_strength)

            # PriceTracker 호출 시 안전성 확인
            try:
                if hasattr(self.PT, 'get_account_summary') and callable(getattr(self.PT, 'get_account_summary')):
                    tracking_data = await self.PT.get_account_summary(stock_code) 

                else:
                    tracking_data = {}
                    
            except Exception as e:
                logger.warning(f"[{stock_code}] PriceTracker 호출 오류: {e}")
                tracking_data = {}
                
            if tracking_data is None:
                tracking_data = {}
                
            last_trade_type = tracking_data.get('trade_type',"HOLD")
            trade_price     = tracking_data.get('trade_price', 0)
            qty_to_sell     = tracking_data.get('qty_to_sell',0)
            qty_to_buy      =  tracking_data.get('qty_to_buy',0)
            tracking_duration  =tracking_data.get('tracking_duration',0)

            trade_strength = self.strength_signal_processor(daily_strength, signal_trend)
            
            current_by_trade = self.safe_percentage_change(current_price, trade_price)
            
            # 한국시가 계산
            try:
                # pytz 사용
                kst = pytz.timezone('Asia/Seoul')
                now_kst = datetime.now(kst)
            except:
                # pytz가 없으면 기본 시간 사용
                now_kst = datetime.now()

            # 시간 비교 수정 - 한국시간 09:10 이전에는 매매금지 , 14:30 이후 전량 매도
            if now_kst.time() > datetime_time(14, 40) :
                return {'action': 'SELL', 'quantity': qty_to_sell}
              
            if now_kst.time() < datetime_time(9, 10) or now_kst.time() > datetime_time(14, 20):
                return {'action': 'NEUTRAL', 'quantity': 0}
            
            if current_by_trade <= -2.0 and qty_to_sell >= 1 and trade_strength <= -1:
                return {'action': 'SELL', 'quantity': qty_to_sell}
              
            if current_by_trade <= -3.0 and qty_to_sell >= 1 :
                return {'action': 'SELL', 'quantity': qty_to_sell}
            
            if trade_strength >= 2: pass
              
            if trade_strength >= 1:  # 매수 신호
              
                if last_trade_type == 'SELL':
                    return {'action': 'NEUTRAL', 'quantity': 0}
                  
                elif qty_to_buy >= 1:
                    return {'action': 'BUY', 'quantity': qty_to_buy}

                else:
                    return {'action': 'NEUTRAL', 'quantity': qty_to_buy}
                    
            elif trade_strength <= -1:  # 매도 신호
              
                if qty_to_sell >= 1:
                    return {'action': 'SELL', 'quantity': qty_to_sell}
                  
                else:
                    return {'action': 'NEUTRAL', 'quantity': 0}
                    
            else:  # 중립 신호 (trade_strength == 0)
              
                return {'action': 'NEUTRAL', 'quantity': 0}
                
        except Exception as e:
            logger.error(f"[{stock_code}] trade_signal_processor 오류: {e}")
            return {'action': 'NEUTRAL', 'quantity': 0}
    
    async def trading_executor(self, stock_code: str, current_price: int, analysis: dict): 
      
        strength_signal = await self.trade_signal_processor(stock_code, current_price, analysis)
        
        action = strength_signal.get('action')
        quantity = strength_signal.get('quantity')
      
        tracking_data = await self.PT.get_account_summary(stock_code) 
        gap_time  = tracking_data.get('tracking_duration',0) if tracking_data else 0
        
        # if action == 'BUY' and gap_time > 600 and quantity > 0:  # 10분 이상 경과 후 
        if action == 'BUY' and quantity > 0:  # 10분 이상 경과 후 
            try:
                logger.info(f"{stock_code}를 {current_price}에 {quantity}구매 요청")     
                result = await self.kiwoom_module.order_stock_buy(
                        dmst_stex_tp="KRX",  # 한국거래소
                        stk_cd=stock_code,
                        ord_qty=str(quantity),
                        ord_uv="",   # 시장가는 빈 문자열
                        trde_tp="3",  # 시장가 주문
                        cond_uv="")
                
                if result and result.get('return_code') == 0:
                    logger.info(f"✅ [{stock_code}] 매수 주문 성공: {quantity}주")
                    return True
                  
                else:
                    logger.error(f"❌ [{stock_code}] 매수 주문 실패: {result}")
                    return False
            except Exception as e:
                logger.error(f"❌ [{stock_code}] 매수 주문 예외: {e}")
                return False
              
        elif action == 'SELL' and gap_time > 600  and quantity >= 1: 
            try:
                logger.info(f"{stock_code}를 {current_price}에 {quantity} 매도 요청")     
                result = await self.kiwoom_module.order_stock_sell(
                    dmst_stex_tp="KRX",  # 한국거래소
                    stk_cd=stock_code,
                    ord_qty=str(quantity),
                    ord_uv="",   # 시장가는 빈 문자열
                    trde_tp="3",  # 시장가 주문
                    cond_uv="" )
                
                if result and result.get('return_code') == 0:
                    logger.info(f"✅ [{stock_code}] 매도 주문 성공: {quantity}주")
                    return True
                else:
                    logger.error(f"❌ [{stock_code}] 매도 주문 실패: {result}")
                    return False
            except Exception as e:
                logger.error(f"❌ [{stock_code}] 매도 주문 예외: {e}")
                return False
        else:
            return False