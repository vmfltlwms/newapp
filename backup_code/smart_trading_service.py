# smart_trading_strategy.py - 최종 통합 버전

import logging
from enum import Enum
from typing import Dict, Optional, Tuple
import time

logger = logging.getLogger(__name__)

class TradingAction(Enum):
    """매매 액션"""
    BUY_STRONG = "강력매수"      # 즉시 매수
    BUY_WEAK = "약한매수"        # 소량 매수
    HOLD = "보유"               # 관망
    SELL_WEAK = "약한매도"       # 일부 매도
    SELL_STRONG = "강력매도"     # 전량 매도

class TradingSignal:
    """매매 신호 클래스"""
    def __init__(self, action: TradingAction, strength: float, reason: str, 
                 suggested_quantity: int = 0, price_target: int = None):
        self.action = action
        self.strength = strength  # 신호 강도 (0-100)
        self.reason = reason
        self.suggested_quantity = suggested_quantity
        self.price_target = price_target

class SmartTradingStrategy:
    
    def __init__(self, kiwoom_module, baseline_cache,baseline_module):
        self.kiwoom_module = kiwoom_module
        self.BC = baseline_cache
        self.baseline_module = baseline_module
        
        # 매매 설정값들
        self.config = {
            # 가격 구간별 설정
            "oversold_threshold": 0.1,       # 5% 이하면 과매도
            "buy_zone_threshold": 0.3,       # 30% 이하면 매수구간
            "sell_zone_threshold": 0.7,      # 70% 이상이면 매도구간
            "overbought_threshold": 0.9,     # 95% 이상이면 과매수
            
            # 체결강도 임계값 (분당 평균 기준)
            "weak_strength": 80,             # 약한 체결강도
            "normal_strength": 120,          # 보통 체결강도
            "strong_strength": 150,          # 강한 체결강도
            "very_strong_strength": 200,     # 매우 강한 체결강도
            
            # 매매 수량 비율
            "max_position_ratio": 1.0,       # 최대 포지션 비율
            "strong_buy_ratio": 0.5,         # 강력매수시 비율
            "weak_buy_ratio": 0.2,           # 약한매수시 비율
            "weak_sell_ratio": 0.3,          # 약한매도시 비율
            "strong_sell_ratio": 0.8,        # 강력매도시 비율
            
            # 시간 설정 (장운영시간 기준)
            "trading_hours": 390,            # 6.5시간 = 390분
        }

    def generate_trading_signal(self, stock_code: str, 
                                current_price: int, 
                                baseline_open_price: int,
                              baseline_decision_price: int, 
                              baseline_low_price: int,
                              baseline_high_price: int, 
                              baseline_quantity: int,
                              current_strength: float, 
                              analysis_1min_strength: float,
                              analysis_5min_strength: float) -> TradingSignal:
        """매매 신호 생성"""
        try:
            # 1. 가격 위치 분석
            price_analysis = self.calculate_price_position( current_price,
                                                            baseline_open_price, 
                                                            baseline_low_price, 
                                                            baseline_high_price, 
                                                            baseline_decision_price)
            
            if "error" in price_analysis:
                return TradingSignal(TradingAction.HOLD, 0, f"가격 분석 오류: {price_analysis['error']}")
            
            # 2. 체결강도 분석  
            strength_analysis = self.analyze_strength_momentum( current_strength, 
                                                                analysis_1min_strength, 
                                                                analysis_5min_strength )
            
            if "error" in strength_analysis:
                return TradingSignal(TradingAction.HOLD, 0, f"체결강도 분석 오류: {strength_analysis['error']}")
            
            # 3. 매매 신호 결정
            return self._decide_trading_action( stock_code, 
                                                current_price, 
                                                baseline_quantity,
                                                price_analysis, 
                                                strength_analysis )
            
        except Exception as e:
            logger.error(f"매매 신호 생성 오류: {e}")
            return TradingSignal(TradingAction.HOLD, 0, f"오류: {str(e)}")
    
    def calculate_price_position( self, current_price: int,
                                  open_price:int, 
                                  low_price: int, 
                                  high_price: int, 
                                  decision_price: int) -> Dict:
        """현재 가격의 위치 분석"""
        try:
            # 가격 범위 계산
            price_range = high_price - low_price
            if price_range <= 0:
                return {"error": "잘못된 가격 범위"}
            
            # 현재 가격 위치 (0.0 ~ 1.0)
            price_position = (current_price - low_price) / price_range
            price_position = max(0.0, min(1.0, price_position))
            
            # 가격 구간 판정
            if price_position <= self.config["oversold_threshold"]: #0.1
                price_zone = "BUY_STRONG"
            elif price_position <= self.config["buy_zone_threshold"]: #0.3
                price_zone = "BUY_ZONE"
            elif price_position <= self.config["sell_zone_threshold"]:#0.7
                price_zone = "NEUTRAL"
            elif price_position <= self.config["overbought_threshold"]:#0.9
                price_zone = "SELL_ZONE"
            else:
                price_zone = "SELL_STRONG"  
            
            return {
                "price_position": price_position,  # 현재 가격 위치 (0.0 ~ 1.0)
                "price_zone": price_zone,          # BUY_STRONG, BUY_ZONE, NEUTRAL, SELL_ZONE, SELL_STRONG
                "current_to_decision": ((current_price - decision_price) / decision_price) * 100,
                "current_to_low": ((current_price - low_price) / low_price) * 100,
                "high_to_current": ((high_price - current_price) / current_price) * 100,
                "open_to_decision": ((open_price - decision_price) / decision_price) * 100
            }
            
        except Exception as e:
            logger.error(f"가격 위치 계산 오류: {e}")
            return {"error": str(e)}
    
    def analyze_strength_momentum(self, current_strength: float, 
                                  strength_1min: float, 
                                  strength_5min: float) -> Dict:
        """체결강도 모멘텀 분석 - 수정된 버전"""
        try:

            # 체결강도 레벨 판정 함수
            def get_strength_level(strength):
                if strength >= self.config["very_strong_strength"]:
                    return "VERY_STRONG"
                elif strength >= self.config["strong_strength"]:
                    return "STRONG"
                elif strength >= self.config["normal_strength"]:
                    return "NORMAL"
                elif strength >= self.config["weak_strength"]:
                    return "WEAK"
                else:
                    return "VERY_WEAK"  
            
            # 현재 체결강도 레벨 (1분 데이터 기준)
            current_level = get_strength_level(strength_1min)
            
            # 추세 방향 판단 (모두 분당 평균 기준으로 통일)
            def get_trend_direction(short_trend, long_trend, day_trend):
                # 단기와 장기 추세 비교
                short_vs_long = short_trend - long_trend
                long_vs_day = long_trend - day_trend
                
                # 강한 상승: 단기 > 장기 > 하루평균, 차이가 큰 경우
                if short_trend > long_trend > day_trend and short_vs_long > 20:
                    return "STRONG_RISING"
                # 상승: 단기 > 장기 또는 장기 > 하루평균
                elif short_trend > long_trend or (long_trend > day_trend and long_vs_day > 10):
                    return "RISING"
                # 강한 하락: 단기 < 장기 < 하루평균, 차이가 큰 경우  
                elif short_trend < long_trend < day_trend and short_vs_long < -20:
                    return "STRONG_FALLING"
                # 하락: 단기 < 장기 또는 장기 < 하루평균
                elif short_trend < long_trend or (long_trend < day_trend and long_vs_day < -10):
                    return "FALLING"
                # 반등: 단기가 크게 상승했지만 하루평균은 낮은 경우
                elif short_trend > long_trend > day_trend  and short_vs_long > 15:
                    return "RECOVERING"
                # 조정: 단기가 하락했지만 하루평균은 높은 경우
                elif short_trend < long_trend < day_trend and short_vs_long < -15:
                    return "CORRECTING"
                else:
                    return "STABLE"
            
            trend_direction = get_trend_direction(strength_1min, strength_5min, current_strength)
            
            # 체결강도 스코어 계산
            strength_score = min(100, (strength_1min / 200) * 100)
            
            # 모멘텀 스코어 계산 (추세 방향에 따라 가중치 적용)
            momentum_weight = {
                "STRONG_RISING": 1.3,
                "RISING": 1.15,
                "RECOVERING": 1.1,
                "STABLE": 1.0,
                "CORRECTING": 0.9,
                "FALLING": 0.85,
                "STRONG_FALLING": 0.7
            }
            
            # 모멘텀 강도 계산
            momentum_raw = (strength_1min - strength_5min) + (strength_5min - current_strength)
            momentum_weighted = momentum_raw * momentum_weight.get(trend_direction, 1.0)
            momentum_score = min(100, max(0, 50 + momentum_weighted))
            
            return {
                "current_level": current_level,       # 1분간 VERY_STRONG ~ VERY_WEAK
                "trend_direction": trend_direction,   # STRONG_RISING ~ STRONG_FALLING
                "short_trend": strength_1min,         # 1분 strength 강도
                "long_trend": strength_5min,          # 5분 strength 강도
                "day_trend": current_strength,        # day strength 강도
                "strength_score": strength_score,
                "momentum_score": momentum_score,
                "overall_score": (strength_score + momentum_score) / 2,
                "momentum_strength": momentum_weighted,
                "momentum_raw": momentum_raw
            }
            
        except Exception as e:
            logger.error(f"체결강도 분석 오류: {e}")
            return {"error": str(e)}

    def _decide_trading_action(self, stock_code: str, 
                              current_price: int,
                              baseline_quantity: int,
                              price_analysis: Dict,
                              strength_analysis: Dict) -> TradingSignal:
        
        trade_done = False
        result_signal = None
        
        # 가격 분석 데이터 추출
        price_zone = price_analysis["price_zone"]                     # BUY_STRONG, BUY_ZONE, NEUTRAL, SELL_ZONE, SELL_STRONG
        price_position = price_analysis["price_position"]             # 현재 가격 위치 (0.0 ~ 1.0)
        decision_return = price_analysis.get("decision_return", 0)    # 현재가 대비 decision
        distance_to_low = price_analysis.get("distance_to_low", 0)    # 현재가 대비 low
        distance_to_high = price_analysis.get("distance_to_high", 0)  # 현재가 대비 high 
        
        # 체결강도 분석 데이터 추출
        strength_level = strength_analysis["current_level"]      # 1분간 VERY_STRONG ~ VERY_WEAK
        trend_direction = strength_analysis["trend_direction"]   # STRONG_RISING ~ STRONG_FALLING
        day_trend = strength_analysis["day_trend"]
        short_trend = strength_analysis["short_trend"]
        long_trend = strength_analysis["long_trend"]
        
        logger.info(f"{stock_code} : {price_zone},{strength_level},{trend_direction}")
        
        
        # 1. 🎯 최우선 조건: 예측 정확도가 높은 경우 (신뢰구간 내)
        if -1.5 <= decision_return <= 1.5 and trade_done == False:
            
            # 1-1. 강력 매수: 저점 대비 3% 이상 상승 + 상승 추세
            if (distance_to_low > 3 and 
                trend_direction in ["STRONG_RISING", "RISING", "RECOVERING"] and 
                trade_done == False):
                
                result_signal = TradingSignal(
                    TradingAction.BUY_STRONG, 95,
                    f"신뢰구간내 강력매수: 저점+{distance_to_low:.1f}%, {trend_direction}",
                    baseline_quantity, current_price
                )
                trade_done = True
                logger.info(f"🚀 [{stock_code}] 신뢰구간 내 강력매수 신호 생성")
            
            # 1-2. 강력 매도: 고점 근처에서 하락 추세
            elif (distance_to_high < -3 and  # 고점 대비 3% 이상 하락
                  trend_direction in ["STRONG_FALLING", "FALLING", "CORRECTING"] and
                  trade_done == False):
                
                result_signal = TradingSignal(
                    TradingAction.SELL_STRONG, 95,
                    f"신뢰구간내 강력매도: 고점{distance_to_high:.1f}%, {trend_direction}",
                    baseline_quantity, current_price
                )
                trade_done = True
                logger.info(f"📉 [{stock_code}] 신뢰구간 내 강력매도 신호 생성")
        
        # 2. 🚀 일반 강력 매수 조건
        if (price_position <= 0.5 and 
            short_trend >= 200 and 
            trend_direction in ["STRONG_RISING", "RISING", "RECOVERING"] and
            trade_done == False):
            
            result_signal = TradingSignal(
                TradingAction.BUY_STRONG, 90,
                f"강력매수: 하단구간({price_position:.2f}) + 강한체결강도({short_trend})",
                baseline_quantity, current_price
            )
            trade_done = True
            logger.info(f"💪 [{stock_code}] 일반 강력매수 신호 생성")
        
        # 3. 📈 약한 매수 조건
        if (short_trend >= 150 and 
            long_trend >= 150 and
            trend_direction in ["STRONG_RISING"] and
            trade_done == False):
            
            result_signal = TradingSignal(
                TradingAction.BUY_WEAK, 80,
                f"약한매수: 지속적 강세({short_trend}/{long_trend})",
                baseline_quantity, current_price
            )
            trade_done = True
            logger.info(f"📈 [{stock_code}] 약한매수 신호 생성")
        
        # 4. 💰 일반 강력 매도 조건
        if (price_position >= 0.5 and 
            short_trend <= 70 and
            trend_direction in ["STRONG_FALLING", "FALLING", "CORRECTING"] and
            trade_done == False):
            
            result_signal = TradingSignal(
                TradingAction.SELL_STRONG, 90,
                f"강력매도: 상단구간({price_position:.2f}) + 약한체결강도({short_trend})",
                baseline_quantity, current_price
            )
            trade_done = True
            logger.info(f"💥 [{stock_code}] 일반 강력매도 신호 생성")
        
        # 5. 📉 약한 매도 조건
        if (short_trend <= 70 and 
            long_trend <= 70 and
            trend_direction in ["STRONG_FALLING"] and
            trade_done == False):
            
            result_signal = TradingSignal(
                TradingAction.SELL_WEAK, 80,
                f"약한매도: 지속적 약세({short_trend}/{long_trend})",
                baseline_quantity, current_price
            )
            trade_done = True
            logger.info(f"📉 [{stock_code}] 약한매도 신호 생성")
        
        # 6. 🔄 홀드 조건 (아무 조건도 만족하지 않은 경우)
        if trade_done == False:
            result_signal = TradingSignal(
                TradingAction.HOLD, 10,
                f"관망: {price_zone}/{strength_level}/{trend_direction}",
                0, current_price
            )
            trade_done = True
            logger.debug(f"⏸️ [{stock_code}] 홀드 신호 생성")
        
        return result_signal

    
    async def execute_trading_signal(self, stock_code: str, 
                                    signal: TradingSignal, 
                                    qty :int, # 현재 주식 보유량
                                    current_price : int,
                                    analysis: dict,
                                    tracking_data : Optional[Dict] = None,
                                    ) -> bool:
        """매매 신호 실행 - KiwoomModule과 통합"""
        try:
            stock_holding_qty = qty   # qty 현재 주식 보유량 or 0(없다면)
            buy_order  = False
            sell_order = False  
            
            # baselice cache 의 open_price 관리
            last_step = self.BC.get_last_step(stock_code)
            cached_baseline = self.BC.get_baseline_info(stock_code,last_step)
            isfirst = cached_baseline.get("isfirst")
            decision_price = cached_baseline.get("decision_price")
            quantity = cached_baseline.get("quantity")
            low_price = cached_baseline.get("low_price")
            high_price = cached_baseline.get("high_price")
            step = cached_baseline.get("step")
            
            latest_data = analysis.get("latest_data")
            analysis_1min = analysis.get("analysis_1min")
            analysis_5min = analysis.get("analysis_5min")
            
            analysis_data = self.analyze_strength_momentum(latest_data,analysis_1min,analysis_5min)
            trend_direction = analysis_data.het("trend_direction")  
            
            if isfirst == True and last_step == 0 :
                if  1>= (decision_price - current_price) / decision_price >=-1 : 
                    self.BC.update_baseline_cache(stock_code=stock_code,
                                                  step = 0,
                                                  open_price = current_price,
                                                  decision_price = current_price,
                                                  low_price = int(current_price/decision_price*low_price),
                                                  high_price = int(current_price/decision_price*high_price))
                    
                    # baseline database update
                    self.baseline_module.update_by_step(stock_code,
                                                        last_step,
                                                        current_price,
                                                        quantity,
                                                        low_price,
                                                        high_price)
                else :
                    self.BC.update_baseline_cache(stock_code=stock_code,
                                                  step = 0,
                                                  open_price = current_price) 
                isfirst = False

            if signal.suggested_quantity > stock_holding_qty :
                buy_qty = signal.suggested_quantity - stock_holding_qty  # 베이스 라인에 있는 수량 - 현재 보유수량
                
            # 주식 매매에 따른 최고 최저가 관리
            if tracking_data is not None :
                trade_type = tracking_data.get("trade_type")        # 마지막 매매형태 BUY, SELL
                trade_price = tracking_data.get("trade_price")      # 마직막 매매 가격
                highest_price = tracking_data.get("highest_price")  # 주식 매수 이후 최고가
                lowest_price = tracking_data.get("lowest_price")    # 주식 매도 이후 최저가
                trade_time = tracking_data.get("trade_time")        # 주식 체결 시간
                last_updated= tracking_data.get("last_updated")     # 업데이트 시간
                
                if trade_type == "BUY" :
                  if current_price / trade_price * 100 >= 103.0 and \
                      trend_direction in [] : pass
                else : 
                  pass# trade_type == SELL
                
                if current_price / trade_price * 100 >= 103.0 and \
                    highest_price / trade_price * 100 >= 105.0 and \
                    trade_type == "BUY":                            
                    last_base = await self.baseline_module.get_last_baseline(stock_code)  
                    last_step = await self.baseline_module.get_last_step(stock_code)
                    buy_qty = int(last_base.get("quantity")/20) if last_step == 0 else last_base.get("quantity")
                    
                    await self.baseline_module.add_step( stock_code= stock_code, 
                                                        decision_price= current_price,
                                                        quantity= buy_qty,
                                                        low_price=  last_base.get("low_price"), 
                                                        high_price= last_base.get("high_price")) 
                    
                    result = await self.kiwoom_module.order_stock_buy(
                                    dmst_stex_tp="KRX",  # 한국거래소
                                    stk_cd=stock_code,
                                    ord_qty=str(buy_qty),
                                    ord_uv="",  # 시장가는 빈 문자열
                                    trde_tp="3",  # 시장가 주문
                                    cond_uv="" )
                    
                    last_base = await self.baseline_module.get_last_baseline(stock_code)  
                    
                    await self.baseline_module.add_step( stock_code= stock_code, 
                                                        decision_price= current_price,
                                                        quantity= int(last_base.get("quantity")),
                                                        low_price=  last_base.get("low_price"), 
                                                        high_price= last_base.get("high_price")) 
                                
                        
                    if result and result.get('return_code') == 0:
                        logger.info(f"✅ [{stock_code}] 매수 주문 성공: {buy_qty}주")
                        return True
                    else:
                        logger.error(f"❌ [{stock_code}] 매수 주문 실패: {result}")
                        return False
                        
                if lowest_price / trade_price * 100 < 97.0 and \
                    stock_holding_qty > 1 :
                    last_base = await self.baseline_module.get_last_baseline(stock_code)      
                                    # 매도 주문 (시장가 주문)
                    result = await self.kiwoom_module.order_stock_sell(
                        dmst_stex_tp="KRX",  # 한국거래소
                        stk_cd=stock_code,
                        ord_qty=str(stock_holding_qty),
                        ord_uv="",  # 시장가는 빈 문자열
                        trde_tp="3",  # 시장가 주문
                        cond_uv=""
                    )
                    
                    if result and result.get('return_code') == 0:
                        logger.info(f"✅ [{stock_code}] 매도 주문 성공: {stock_holding_qty}주")
                        return True
                    else:
                        logger.error(f"❌ [{stock_code}] 매도 주문 실패: {result}")
                        return False
                        
                


            # 실제 주문 실행
            if signal.action in [TradingAction.BUY_STRONG, TradingAction.BUY_WEAK] and \
                buy_qty >= 1 and buy_order == True   :
                # 매수 주문 (시장가 주문)
                result = await self.kiwoom_module.order_stock_buy(
                    dmst_stex_tp="KRX",  # 한국거래소
                    stk_cd=stock_code,
                    ord_qty=str(buy_qty),
                    ord_uv="",  # 시장가는 빈 문자열
                    trde_tp="3",  # 시장가 주문
                    cond_uv="" )
                
                if result and result.get('return_code') == 0:
                    logger.info(f"✅ [{stock_code}] 매수 주문 성공: {buy_qty}주")
                    return True
                else:
                    logger.error(f"❌ [{stock_code}] 매수 주문 실패: {result}")
                    return False
                
            elif signal.action in [TradingAction.SELL_STRONG, TradingAction.SELL_WEAK] and \
                stock_holding_qty >= 1 and sell_order == True   :
                # 매도 주문 (시장가 주문)
                result = await self.kiwoom_module.order_stock_sell(
                    dmst_stex_tp="KRX",  # 한국거래소
                    stk_cd=stock_code,
                    ord_qty=str(stock_holding_qty),
                    ord_uv="",  # 시장가는 빈 문자열
                    trde_tp="3",  # 시장가 주문
                    cond_uv=""
                )
                
                if result and result.get('return_code') == 0:
                    logger.info(f"✅ [{stock_code}] 매도 주문 성공: {stock_holding_qty}주")
                    return True
                else:
                    logger.error(f"❌ [{stock_code}] 매도 주문 실패: {result}")
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"❌ [{stock_code}] 매매 실행 오류: {str(e)}")
            return False

class TradingIntegration:
    
    def __init__(self, kiwoom_module, baseline_cache,baseline_module):
        self.kiwoom_module = kiwoom_module
        self.BC = baseline_cache
        self.trading_strategy = SmartTradingStrategy(kiwoom_module,baseline_cache, baseline_module)
        
        # 매매 제한 설정
        self.last_trade_time = {}  # 종목별 마지막 매매 시간
        self.min_trade_interval = 600  # 같은 종목 최소 매매 간격 (10분)
    
    # 매매 신호 처리 (type_callback_0B에서 호출) 
    async def process_trading_signals(self, 
                                      stock_code: str, 
                                      analysis: dict, 
                                      qty :int, 
                                      current_price : int,
                                      tracking_data : Optional[Dict] = None):
        try:
            signal = await self.check_trading_opportunity(stock_code, analysis)
            if signal and signal.strength >= 70:
                success = await self.trading_strategy.execute_trading_signal(stock_code, signal,qty ,current_price,analysis,tracking_data)
                if success:
                    self._record_trade(stock_code)

        except Exception as e:
            logger.error(f"[{stock_code}] 매매 신호 처리 오류: {str(e)}")
            
    async def check_trading_opportunity(self, stock_code: str, analysis: dict) -> Optional[TradingSignal]:
        """매매 기회 체크"""
        try:
            # 베이스라인 정보 조회
            last_step = self.BC.get_last_step(stock_code)
            last_step = last_step if last_step is not None else 0
            baseline_cache = self.BC.get_price_info(stock_code, last_step)
            if not baseline_cache:
                logger.debug(f"[{stock_code}] 베이스라인 정보 없음")
                return None
            
            baseline_decision_price = baseline_cache.get("decision_price")
            baseline_quantity = baseline_cache.get("quantity")
            baseline_open_price = baseline_cache.get("open_price")
            baseline_low_price = baseline_cache.get("low_price")
            baseline_high_price = baseline_cache.get("high_price")
            
            # 필수 데이터 검증
            if not all([baseline_decision_price, baseline_quantity, baseline_open_price,
                       baseline_low_price, baseline_high_price]):
                logger.debug(f"[{stock_code}] 베이스라인 데이터 불완전")
                return None
            
            # 현재 시세 정보
            latest = analysis.get('latest_data', {})
            analysis_1min = analysis.get('analysis_1min', {})
            analysis_5min = analysis.get('analysis_5min', {})
            
            current_price = latest.get('current_price')
            current_strength = latest.get('execution_strength', 0)
            analysis_1min_strength = analysis_1min.get('execution_strength', 0)
            analysis_5min_strength = analysis_5min.get('execution_strength', 0)
            
            if not current_price or current_price <= 0:
                logger.debug(f"[{stock_code}] 현재가 정보 없음")
                return None
            

            # 매매 신호 생성
            signal = self.trading_strategy.generate_trading_signal( stock_code, 
                                                                    current_price,
                                                                    baseline_open_price,
                                                                    baseline_decision_price, 
                                                                    baseline_low_price, 
                                                                    baseline_high_price,
                                                                    baseline_quantity, 
                                                                    current_strength, 
                                                                    analysis_1min_strength, 
                                                                    analysis_5min_strength)
            
            return signal
            
        except Exception as e:
            logger.error(f"[{stock_code}] 매매 기회 체크 오류: {str(e)}")
            return None
    
    def _can_trade(self, stock_code: str) -> bool:
        """매매 가능 여부 체크"""
        current_time = time.time()
        # 같은 종목 매매 간격 제한
        last_trade = self.last_trade_time.get(stock_code, 0)
        if current_time - last_trade < self.min_trade_interval:
            remaining = self.min_trade_interval - (current_time - last_trade)
            logger.debug(f"[{stock_code}] 매매 간격 제한: {remaining:.0f}초 남음")
            return False
        
        return True
    
    def _record_trade(self, stock_code: str):
        """매매 기록"""
        self.trade_count_today += 1
        self.last_trade_time[stock_code] = time.time()
        logger.info(f"[{stock_code}] 매매 기록: 오늘 {self.trade_count_today}번째")
    
