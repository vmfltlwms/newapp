# smart_trading_strategy.py - 최종 통합 버전

import logging
from datetime import datetime
from zoneinfo import ZoneInfo 
import time

logger = logging.getLogger(__name__)


class SmartTrading :
    
    def __init__(self, stock_qty, kiwoom_module, baseline_cache, baseline_module, PriceTracker):
        self.kiwoom_module = kiwoom_module
        self.stock_qty = stock_qty
        self.BC = baseline_cache
        self.baseline_module = baseline_module
        self.PT = PriceTracker
        
    def safe_percentage_change(self, current, base):
        """안전한 퍼센트 변화율 계산"""
        if base == 0 or base is None or current is None:
            return 0
        return (current - base) / base * 100
      
    # 추세 방향 판단 (모두 분당 평균 기준으로 통일)
    def trend_direction(self, 
                        strength_1min, 
                        strength_5min, 
                        strength_day):
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
        elif strength_1min > strength_5min > strength_day  and short_vs_long > 15:
            return "RISING"
        # 조정: 단기가 하락했지만 하루평균은 높은 경우
        elif strength_1min < strength_5min < strength_day and short_vs_long < -15:
            return "FALLING"
        else:
            return "STABLE"

    def strength_signal_processor( self, daily_strength, 
                              signal_trend, 
                              expect_price, 
                              open_price, 
                              current_price) -> int:


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
        
        strength_signal = strength_mapping.get(signal_trend, 0)
        
        
        if expect_price != 0:
            A = (current_price - expect_price) / expect_price * 100
        else:
            A = 0
            
        if open_price != 0:
            B = (current_price - open_price) / open_price * 100
        else:
            B = 0
        
        # 변화율을 시그널로 변환하는 함수
        def rate_to_signal(rate):
            if -3 <= rate <= 3:
                return 0
            elif 3 < rate <= 6:
                return 1
            elif rate > 6:
                return 2
            elif -6 <= rate < -3:
                return -1
            else:  # rate < -6
                return -2
        
        # A, B를 각각 시그널로 변환
        signal_A = rate_to_signal(A)
        signal_B = rate_to_signal(B)
        
        # Price_signal = Int((A+B)/2)
        price_signal = int((signal_A + signal_B) / 2)
        
        # 최종 시그널 = strength_signal + price_signal
        final_signal = strength_signal + price_signal
        
        return final_signal

    async def trade_signal_processor( self, stock_code :str, 
                                      current_price :int, 
                                      stock_qty: dict, 
                                      analysis : dict) -> dict:
        try:
            # None 체크 강화
            if not analysis:
                return {'action': 'NEUTRAL', 'quantity': 0}
                
            last_step = self.BC.get_last_step(stock_code)
            baseline_info = self.BC.get_price_info(stock_code, last_step) or {}
            
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
            
            open_price = baseline_info.get('open_price', 0)
            decision_price = baseline_info.get('decision_price', 0)
            quantity = baseline_info.get('quantity', 0)
            
            tracking_data = await self.PT.get_tracking_data(stock_code) 
            last_trade_type = tracking_data.get('trade_type')
            trade_price = tracking_data.get('trade_price', 0)
            
            available_stock_qty = stock_qty.get(stock_code, 0)
            stock_to_sell = available_stock_qty if last_step <= 1 else max(1, int(available_stock_qty * 0.2))
            
            trade_strength = self.strength_signal_processor(daily_strength, signal_trend, decision_price, open_price, current_price)
            
            current_by_trade = self.safe_percentage_change( current_price, trade_price)
            current_by_open = self.safe_percentage_change( current_price, open_price)
            
            now_kst = datetime.now(ZoneInfo("Asia/Seoul"))

            if now_kst.time() < time(9, 10) :
                return {'action': 'NEUTRAL', 'quantity': 0}
              
            if trade_strength >= 1:  # 매수 신호
              
                if now_kst.time() > time(14, 30) and current_by_open >= 3.0:
                    return {'action': 'NEUTRAL', 'quantity': 0}

                if last_step >= 3:
                    return {'action': 'NEUTRAL', 'quantity': 0}
                
                if last_trade_type == 'BUY':
                    return {'action': 'BUY', 
                            'quantity': int(quantity * 0.2) if last_step == 0 else quantity }
                  
                elif last_trade_type == 'SELL':
                    
                    if current_by_trade >= 3.0:
                        return {'action': 'BUY', 'quantity': quantity}
                      
                    else:
                        return {'action': 'NEUTRAL', 'quantity': 0}
                      
                else:
                    return {'action': 'BUY', 'quantity': quantity}
                    
            elif trade_strength <= -1:  # 매도 신호
              
                if stock_to_sell >= 1:
                    return {'action': 'SELL', 'quantity': stock_to_sell}
                  
                else:
                    return {'action': 'NEUTRAL', 'quantity': 0}
                    
            else:  # 중립 신호 (trade_strength == 0)
                if last_trade_type == 'BUY':
                  
                    if current_by_trade <= -3.0:
                        return {'action': 'SELL', 'quantity': stock_to_sell}
                      
                return {'action': 'NEUTRAL', 'quantity': 0}  # 수정: quantity를 0으로
                
        except Exception as e:
            logger.error(f"[{stock_code}] decide_signal 오류: {e}")
            return {'action': 'NEUTRAL', 'quantity': 0}
    
    async def trading_executor( self, stock_code:str, 
                                current_price : int,
                                stock_qty: dict, 
                                analysis:dict) : 
      
        strength_signal = await self.trade_signal_processor(  stock_code,
                                                              current_price,
                                                              stock_qty,
                                                              analysis  )
        
        action = strength_signal.get('action')
        quantity = strength_signal.get('quantity')
        
        last_step = self.BC.get_last_step(stock_code)
        baseline_info = self.BC.get_baseline_info(stock_code,last_step)
        last_update_time = baseline_info.get('updated_at')
        last_update_time = last_update_time if last_update_time is not None else 0
        gap_time = time.time() - last_update_time

        if action == 'BUY' and gap_time > 1800 : # 30 분 이상 경과 후 
            result = await self.kiwoom_module.order_stock_buy(
                    dmst_stex_tp = "KRX",  # 한국거래소
                    stk_cd   =  stock_code,
                    ord_qty  =  str(quantity),
                    ord_uv   =  "",   # 시장가는 빈 문자열
                    trde_tp  =  "3",  # 시장가 주문
                    cond_uv  =  "" )
            
            if result and result.get('return_code') == 0:
                logger.info(f"✅ [{stock_code}] 매수 주문 성공: {quantity}주")
                return True
              
            else:
                logger.error(f"❌ [{stock_code}] 매수 주문 실패: {result}")
                return False
              
        elif action == 'SELL' and gap_time > 600 : 
            result = await self.kiwoom_module.order_stock_sell(
                dmst_stex_tp="KRX",  # 한국거래소
                stk_cd   =  stock_code,
                ord_qty  =  str(quantity),
                ord_uv   =  "",   # 시장가는 빈 문자열
                trde_tp  =  "3",  # 시장가 주문
                cond_uv  =  ""
            )
            
            if result and result.get('return_code') == 0:
                logger.info(f"✅ [{stock_code}] 매도 주문 성공: {quantity}주")
                return True
            else:
                logger.error(f"❌ [{stock_code}] 매도 주문 실패: {result}")
                return False
        else : return False