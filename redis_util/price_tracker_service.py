# services/price_tracker_service.py (수정된 버전)
import json
import time
import logging
from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from dependency_injector.wiring import inject, Provide
from container.redis_container import Redis_Container
from db.redis_db import RedisDB

logger = logging.getLogger(__name__)

@dataclass
class PriceTrackingData:
    """가격 추적 데이터 클래스"""
    stock_code: str         # 주식코드
    isfirst: bool          # 처음 실행여부
    current_price: int     # 현재가
    highest_price: int     # 최고가
    lowest_price: int      # 최저가
    trade_price: int       # 매매 체결가
    period_type: bool      # 기간 타입(False: hold, True: trade)
    trade_time: float      # 매매 체결 시간
    last_updated: float    # 마지막 업데이트 시간
    price_to_buy: int      # 매수 결심가격
    price_to_sell: int     # 매도 결심가격
    qty_to_sell: int       # 매도가능 주식 수
    qty_to_buy: int        # 매수가능 주식 수
    trade_type: str        # BUY, SELL, HOLD
    ma20_slope: float      # MA20 기울기
    ma20_avg_slope: float  # MA20 평균 기울기
    ma20: int             # 20일 이동평균선

class PriceTracker:
    """성능 최적화된 주식 가격 추적 서비스"""
    
    def __init__(self, redis_db: RedisDB = Provide[Redis_Container.redis_db]):
        self.redis_db = redis_db
        self.REDIS_KEY_PREFIX = "PT"
        self.EXPIRE_TIME = 60 * 60 * 8  # 8시간
        self.UPDATE_THRESHOLD = 0  # 5초 이내 중복 업데이트 방지
    
    def _get_redis_key(self, stock_code: str) -> str:
        """Redis 키 생성"""
        return f"redis:{self.REDIS_KEY_PREFIX}:{stock_code}"
    
    def _to_hash_data(self, tracking_data: PriceTrackingData) -> Dict[str, str]:
        """PriceTrackingData를 Redis Hash 형식으로 변환"""
        return {
            "stock_code": tracking_data.stock_code,
            "isfirst": str(tracking_data.isfirst),
            "current_price": str(tracking_data.current_price),
            "highest_price": str(tracking_data.highest_price),
            "lowest_price": str(tracking_data.lowest_price),
            "trade_price": str(tracking_data.trade_price),
            "period_type": str(tracking_data.period_type),
            "trade_time": str(tracking_data.trade_time),
            "last_updated": str(tracking_data.last_updated),
            "price_to_buy": str(tracking_data.price_to_buy),
            "price_to_sell": str(tracking_data.price_to_sell),
            "qty_to_sell": str(tracking_data.qty_to_sell),
            "qty_to_buy": str(tracking_data.qty_to_buy),
            "trade_type": tracking_data.trade_type,
            "ma20_slope": str(tracking_data.ma20_slope),
            "ma20_avg_slope": str(tracking_data.ma20_avg_slope),
            "ma20": str(tracking_data.ma20)
        }
    
    def _from_hash_data(self, hash_data: Dict[str, str]) -> Dict[str, Any]:
        """Redis Hash 데이터를 파이썬 딕셔너리로 변환"""
        if not hash_data:
            return {}
        
        try:
            return {
                "stock_code": hash_data.get("stock_code", ""),
                "isfirst": hash_data.get("isfirst", "True").lower() == "true",
                "current_price": int(hash_data.get("current_price", "0")),
                "highest_price": int(hash_data.get("highest_price", "0")),
                "lowest_price": int(hash_data.get("lowest_price", "0")),
                "trade_price": int(hash_data.get("trade_price", "0")),
                "period_type": hash_data.get("period_type", "False").lower() == "true",
                "trade_time": float(hash_data.get("trade_time", "0")),
                "last_updated": float(hash_data.get("last_updated", "0")),
                "price_to_buy": int(hash_data.get("price_to_buy", "0")),
                "price_to_sell": int(hash_data.get("price_to_sell", "0")),
                "qty_to_sell": int(hash_data.get("qty_to_sell", "0")),
                "qty_to_buy": int(hash_data.get("qty_to_buy", "0")),
                "trade_type": hash_data.get("trade_type", "HOLD"),
                "ma20_slope": float(hash_data.get("ma20_slope", "0")),
                "ma20_avg_slope": float(hash_data.get("ma20_avg_slope", "0")),
                "ma20": int(hash_data.get("ma20", "0"))
            }
        except (ValueError, TypeError) as e:
            logger.error(f"❌ 데이터 변환 오류: {str(e)}")
            return {}
    
    def _safe_int_convert(self, value: Any, default: int = 0) -> int:
        """안전한 정수 변환"""
        try:
            return int(value) if value is not None else default
        except (ValueError, TypeError):
            return default
    
    def _safe_float_convert(self, value: Any, default: float = 0.0) -> float:
        """안전한 실수 변환"""
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            return default
    
    async def initialize_tracking(self, 
                                  stock_code: str, 
                                  current_price: Optional[int] = 0,     
                                  trade_price: Optional[int] = 0, 
                                  period_type: Optional[bool] = False, 
                                  isfirst: Optional[bool] = False,
                                  price_to_buy: Optional[int] = 0,
                                  price_to_sell: Optional[int] = 0,
                                  qty_to_sell: Optional[int] = 0,
                                  qty_to_buy: Optional[int] = 0,
                                  trade_type: Optional[str] = "HOLD",
                                  ma20_slope: Optional[float] = 0,
                                  ma20_avg_slope: Optional[float] = 0,
                                  ma20: Optional[int] = 0) -> bool:
        """새로운 가격 추적 시작"""
        
        # 입력값 검증
        if not stock_code:
            logger.error("❌ 종목코드가 없습니다.")
            return False
        
        update_price = trade_price if trade_price != 0 else current_price
        
        try:
            current_timestamp = time.time()
            
            tracking_data = PriceTrackingData(
                stock_code=stock_code,
                isfirst=isfirst or False,
                current_price=current_price or 0,
                highest_price=update_price or 0,
                lowest_price=update_price or 0,
                trade_price=trade_price or 0,
                period_type=period_type or False,
                trade_time=current_timestamp,
                last_updated=current_timestamp,
                price_to_buy=price_to_buy or 0,
                price_to_sell=price_to_sell or 0,
                qty_to_sell=qty_to_sell or 0,
                qty_to_buy=qty_to_buy or 0,
                trade_type=trade_type or "HOLD",
                ma20_slope=ma20_slope or 0,
                ma20_avg_slope=ma20_avg_slope or 0,
                ma20=ma20 or 0
            )
            
            redis_key = self._get_redis_key(stock_code)
            hash_data = self._to_hash_data(tracking_data)
            
            # Pipeline 사용하여 효율적으로 저장
            pipe = self.redis_db.pipeline()
            pipe.hset(redis_key, mapping=hash_data)
            pipe.expire(redis_key, self.EXPIRE_TIME)
            await pipe.execute()
            
            logger.info(f"🎯 가격 추적 초기화 - 종목: {stock_code}, 체결가: {current_price}, MA20_SLOPE: {ma20_slope}, MA20_AVG_SLOPE: {ma20_avg_slope}, MA20: {ma20}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 가격 추적 초기화 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return False
    
    async def update_tracking_data(self, 
                                  stock_code: str,
                                  current_price: Optional[int] = None,
                                  trade_price: Optional[int] = None,
                                  price_to_buy: Optional[int] = None,
                                  price_to_sell: Optional[int] = None,
                                  qty_to_sell: Optional[int] = None,
                                  qty_to_buy: Optional[int] = None,
                                  period_type: Optional[bool] = None,
                                  trade_type: Optional[str] = None,
                                  isfirst: Optional[bool] = None,
                                  ma20_slope: Optional[float] = None,
                                  ma20_avg_slope: Optional[float] = None,
                                  ma20: Optional[int] = None,
                                  reset_extremes: bool = False,
                                  force_update: bool = False) -> Optional[Dict]:
        """가격 추적 데이터 업데이트"""
        
        if not stock_code:
            logger.error("❌ 종목코드가 없습니다.")
            return None
        
        try:
            redis_key = self._get_redis_key(stock_code)
            
            # 기존 데이터 존재 확인
            if not await self.redis_db.exists(redis_key):
                logger.debug(f"종목 {stock_code}의 가격 추적 데이터가 없습니다.")
                return None
            
            update_fields = {}
            current_time = time.time()
            
            # 거래가 업데이트 (새로운 거래 발생)
            if trade_price is not None:
                update_fields["trade_price"] = str(trade_price)
                update_fields["trade_time"] = str(current_time)
                logger.info(f"💰 거래가 업데이트 - 종목: {stock_code}, 가격: {trade_price}")
                
                # 새 거래시 최고가/최저가 초기화
                if reset_extremes:
                    update_fields["highest_price"] = str(trade_price)
                    update_fields["lowest_price"] = str(trade_price)
                    logger.info(f"🔄 최고가/최저가 초기화 - 종목: {stock_code}, 가격: {trade_price}")
            
            # 강제 업데이트 - 최고가/최저가를 현재가로 설정
            if current_price is not None and force_update:
                update_fields["highest_price"] = str(current_price)
                update_fields["lowest_price"] = str(current_price)
                logger.info(f"🔄 강제 최고가/최저가 업데이트 - 종목: {stock_code}, 가격: {current_price}")
            
            # 현재가 및 최고가/최저가 업데이트
            if current_price is not None:
                update_fields["current_price"] = str(current_price)
                
                # 강제 업데이트가 아닌 경우에만 정상적인 최고가/최저가 로직 적용
                if not force_update:
                    # Pipeline으로 현재 최고가/최저가 조회
                    pipe = self.redis_db.pipeline()
                    pipe.hget(redis_key, "highest_price")
                    pipe.hget(redis_key, "lowest_price")
                    results = await pipe.execute()
                    
                    highest_price_str, lowest_price_str = results
                    
                    if highest_price_str and lowest_price_str:
                        highest_price = self._safe_int_convert(highest_price_str)
                        lowest_price = self._safe_int_convert(lowest_price_str)
                        
                        # 최고가 갱신
                        if current_price > highest_price:
                            update_fields["highest_price"] = str(current_price)
                            logger.debug(f"📈 최고가 갱신 - 종목: {stock_code}, {highest_price} -> {current_price}")
                        
                        # 최저가 갱신
                        if current_price < lowest_price:
                            update_fields["lowest_price"] = str(current_price)
                            logger.debug(f"📉 최저가 갱신 - 종목: {stock_code}, {lowest_price} -> {current_price}")
            
            # 나머지 필드들 업데이트
            if price_to_buy is not None:
                update_fields["price_to_buy"] = str(price_to_buy)
            
            if price_to_sell is not None:
                update_fields["price_to_sell"] = str(price_to_sell)
            
            if qty_to_sell is not None:
                update_fields["qty_to_sell"] = str(qty_to_sell)
            
            if qty_to_buy is not None:
                update_fields["qty_to_buy"] = str(qty_to_buy)
            
            if trade_type is not None:
                update_fields["trade_type"] = trade_type
            
            if period_type is not None:
                update_fields["period_type"] = str(period_type)
            
            if isfirst is not None:
                update_fields["isfirst"] = str(isfirst)
            
            # MA 값들 업데이트
            if ma20_slope is not None:
                update_fields["ma20_slope"] = str(ma20_slope)
                logger.debug(f"📊 MA20_SLOPE 업데이트 - 종목: {stock_code}, MA20_SLOPE: {ma20_slope}")
            
            if ma20_avg_slope is not None:
                update_fields["ma20_avg_slope"] = str(ma20_avg_slope)
                logger.debug(f"📊 MA20_AVG_SLOPE 업데이트 - 종목: {stock_code}, MA20_AVG_SLOPE: {ma20_avg_slope}")
            
            if ma20 is not None:
                update_fields["ma20"] = str(ma20)
                logger.debug(f"📊 MA20 업데이트 - 종목: {stock_code}, MA20: {ma20}")
            
            # 업데이트 실행
            if update_fields:
                update_fields["last_updated"] = str(current_time)
                
                # Pipeline으로 효율적 업데이트
                pipe = self.redis_db.pipeline()
                pipe.hset(redis_key, mapping=update_fields)
                pipe.expire(redis_key, self.EXPIRE_TIME)
                await pipe.execute()
                
                logger.debug(f"✅ 업데이트 완료 - 종목: {stock_code}, 필드 수: {len(update_fields)}")
            
            # 업데이트된 전체 데이터 반환
            return await self.get_tracking_data(stock_code)
            
        except Exception as e:
            logger.error(f"❌ 업데이트 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None
    
    async def get_price_info(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """빠른 가격 정보 조회 (필요한 필드만)"""
        if not stock_code:
            return None
            
        try:
            redis_key = self._get_redis_key(stock_code)
            
            # Pipeline으로 필요한 필드만 효율적으로 조회
            pipe = self.redis_db.pipeline()
            pipe.hget(redis_key, "current_price")
            pipe.hget(redis_key, "highest_price")
            pipe.hget(redis_key, "lowest_price")
            pipe.hget(redis_key, "trade_price")
            pipe.hget(redis_key, "price_to_buy")
            pipe.hget(redis_key, "price_to_sell")
            pipe.hget(redis_key, "qty_to_sell")
            pipe.hget(redis_key, "qty_to_buy")
            pipe.hget(redis_key, "trade_type")
            pipe.hget(redis_key, "ma20_slope")
            pipe.hget(redis_key, "ma20_avg_slope")
            pipe.hget(redis_key, "ma20")
            results = await pipe.execute()
            
            # 🔧 수정: 변수명을 올바르게 할당
            (current_price_str, highest_price_str, lowest_price_str, 
             trade_price_str, price_to_buy_str, price_to_sell_str, 
             qty_to_sell_str, qty_to_buy_str, trade_type,
             ma20_slope_str, ma20_avg_slope_str, ma20_str) = results
            
            # 필수 필드 검증
            has_any_data = any([
                current_price_str, highest_price_str, lowest_price_str, 
                trade_price_str, price_to_buy_str, price_to_sell_str,
                qty_to_sell_str, qty_to_buy_str, ma20_slope_str, ma20_avg_slope_str, ma20_str
            ])

            if not has_any_data:
                logger.warning(f"⚠️ {stock_code}: 모든 데이터가 None이거나 빈 값입니다.")
                return None
            
            # 안전한 타입 변환
            current_price = self._safe_int_convert(current_price_str)
            highest_price = self._safe_int_convert(highest_price_str)
            lowest_price = self._safe_int_convert(lowest_price_str)
            trade_price = self._safe_int_convert(trade_price_str)
            price_to_buy = self._safe_int_convert(price_to_buy_str)
            price_to_sell = self._safe_int_convert(price_to_sell_str)
            qty_to_sell = self._safe_int_convert(qty_to_sell_str)
            qty_to_buy = self._safe_int_convert(qty_to_buy_str)
            ma20_slope = self._safe_float_convert(ma20_slope_str)        # 🔧 수정: float 변환 사용
            ma20_avg_slope = self._safe_float_convert(ma20_avg_slope_str)      # 🔧 수정: float 변환 사용
            ma20 = self._safe_int_convert(ma20_str)
            
            # 수익률 계산 (0으로 나누기 방지)
            def calculate_rate(price: int, base_price: int) -> float:
                return round(((price - base_price) / base_price) * 100, 2) if base_price > 0 else 0.0
            
            return {
                "stock_code": stock_code,
                "current_price": current_price,
                "highest_price": highest_price,
                "lowest_price": lowest_price,
                "trade_price": trade_price,
                "price_to_buy": price_to_buy,
                "price_to_sell": price_to_sell,
                "qty_to_sell": qty_to_sell,
                "qty_to_buy": qty_to_buy,
                "trade_type": trade_type or "HOLD",
                "ma20_slope": ma20_slope,
                "ma20_avg_slope": ma20_avg_slope,
                "ma20": ma20,
                "change_from_trade": calculate_rate(current_price, trade_price),
                "highest_gain": calculate_rate(highest_price, trade_price),
                "lowest_loss": calculate_rate(lowest_price, trade_price)
            }
            
        except Exception as e:
            logger.error(f"❌ 빠른 가격 정보 조회 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None
    
    async def get_tracking_data(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """전체 추적 데이터 조회"""
        if not stock_code:
            return {}
            
        try:
            redis_key = self._get_redis_key(stock_code)
            hash_data = await self.redis_db.hgetall(redis_key)
            
            if not hash_data:
                return {}
            
            return self._from_hash_data(hash_data)
            
        except Exception as e:
            logger.error(f"❌ 가격 추적 데이터 조회 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return {}
    
    async def isfirst(self, stock_code: str) -> Optional[bool]:
        """첫 실행 여부 확인"""
        if not stock_code:
            return None
            
        try:
            redis_key = self._get_redis_key(stock_code)
            isfirst_str = await self.redis_db.hget(redis_key, "isfirst")
            
            if isfirst_str is None:
                logger.debug(f"종목 {stock_code}의 추적 데이터가 존재하지 않습니다.")
                return None
            
            isfirst_value = isfirst_str.lower() == "true"
            logger.debug(f"종목 {stock_code}의 첫 실행 여부: {isfirst_value}")
            return isfirst_value
            
        except Exception as e:
            logger.error(f"❌ 첫 실행 여부 확인 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None
    
    async def set_isfirst(self, stock_code: str, isfirst: bool) -> bool:
        """첫 실행 여부 설정"""
        if not stock_code:
            return False
            
        try:
            redis_key = self._get_redis_key(stock_code)
            
            # 데이터 존재 확인
            if not await self.redis_db.exists(redis_key):
                logger.debug(f"종목 {stock_code}의 가격 추적 데이터가 없습니다.")
                return False
            
            # Pipeline으로 효율적 업데이트
            current_time = time.time()
            pipe = self.redis_db.pipeline()
            pipe.hset(redis_key, mapping={
                "isfirst": str(isfirst),
                "last_updated": str(current_time)
            })
            pipe.expire(redis_key, self.EXPIRE_TIME)
            await pipe.execute()
            
            logger.info(f"✅ 첫 실행 여부 설정 완료 - 종목: {stock_code}, isfirst: {isfirst}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 첫 실행 여부 설정 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return False
    
    async def remove_tracking(self, stock_code: str) -> bool:
        """가격 추적 데이터 삭제"""
        if not stock_code:
            return False
            
        try:
            redis_key = self._get_redis_key(stock_code)
            result = await self.redis_db.delete(redis_key)
            
            if result:
                logger.info(f"🗑️ 가격 추적 데이터 삭제 - 종목: {stock_code}")
                return True
            else:
                logger.warning(f"⚠️ 삭제할 가격 추적 데이터 없음 - 종목: {stock_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 가격 추적 데이터 삭제 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return False
          
    async def get_multiple_price_info(self, stock_codes: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """여러 종목의 가격 정보를 한번에 조회 (성능 최적화)"""
        if not stock_codes:
            return {}
        
        try:
            results = {}
            
            # Pipeline으로 모든 종목의 데이터를 한번에 조회
            pipe = self.redis_db.pipeline()
            redis_keys = []
            
            for stock_code in stock_codes:
                redis_key = self._get_redis_key(stock_code)
                redis_keys.append((stock_code, redis_key))
                pipe.hgetall(redis_key)
            
            all_data = await pipe.execute()
            
            # 결과 처리
            for i, (stock_code, _) in enumerate(redis_keys):
                hash_data = all_data[i] if i < len(all_data) else {}
                if hash_data:
                    tracking_data = self._from_hash_data(hash_data)
                    if tracking_data:
                        # get_price_info와 동일한 형식으로 변환
                        trade_price = tracking_data.get("trade_price", 0)
                        current_price = tracking_data.get("current_price", 0)
                        highest_price = tracking_data.get("highest_price", 0)
                        lowest_price = tracking_data.get("lowest_price", 0)
                        
                        def calculate_rate(price: int, base_price: int) -> float:
                            return round(((price - base_price) / base_price) * 100, 2) if base_price > 0 else 0.0
                        
                        results[stock_code] = {
                            "stock_code": stock_code,
                            "current_price": current_price,
                            "highest_price": highest_price,
                            "lowest_price": lowest_price,
                            "trade_price": trade_price,
                            "price_to_buy": tracking_data.get("price_to_buy", 0),
                            "price_to_sell": tracking_data.get("price_to_sell", 0),
                            "qty_to_sell": tracking_data.get("qty_to_sell", 0),
                            "qty_to_buy": tracking_data.get("qty_to_buy", 0),
                            "trade_type": tracking_data.get("trade_type", "HOLD"),
                            "ma20_slope": tracking_data.get("ma20_slope", 0),
                            "ma20_avg_slope": tracking_data.get("ma20_avg_slope", 0),
                            "ma20": tracking_data.get("ma20", 0),
                            "change_from_trade": calculate_rate(current_price, trade_price),
                            "highest_gain": calculate_rate(highest_price, trade_price),
                            "lowest_loss": calculate_rate(lowest_price, trade_price)
                        }
                    else:
                        results[stock_code] = None
                else:
                    results[stock_code] = None
            
            return results
            
        except Exception as e:
            logger.error(f"❌ 다중 가격 정보 조회 실패, 오류: {str(e)}")
            return {stock_code: None for stock_code in stock_codes}
    
    # MA 관련 편의 메서드들
    async def update_ma_values(self, stock_code: str, ma20_slope: float, ma20_avg_slope: float, ma20: int) -> bool:
        """MA 값들을 한번에 업데이트"""
        result = await self.update_tracking_data(
            stock_code=stock_code, 
            ma20_slope=ma20_slope, 
            ma20_avg_slope=ma20_avg_slope, 
            ma20=ma20
        )
        return result is not None
    
    async def get_ma_values(self, stock_code: str) -> Optional[Dict[str, float]]:
        """MA 값들만 조회"""
        try:
            redis_key = self._get_redis_key(stock_code)
            
            # Pipeline으로 MA 값들만 효율적으로 조회
            pipe = self.redis_db.pipeline()
            pipe.hget(redis_key, "ma20_slope")
            pipe.hget(redis_key, "ma20_avg_slope")
            pipe.hget(redis_key, "ma20")
            results = await pipe.execute()
            
            ma20_slope_str, ma20_avg_slope_str, ma20_str = results
            
            # 하나라도 None이면 데이터가 없는 것으로 간주
            if not any([ma20_slope_str, ma20_avg_slope_str, ma20_str]):
                return None
            
            return {
                "ma20_slope": self._safe_float_convert(ma20_slope_str),
                "ma20_avg_slope": self._safe_float_convert(ma20_avg_slope_str),
                "ma20": self._safe_int_convert(ma20_str)
            }
            
        except Exception as e:
            logger.error(f"❌ MA 값 조회 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None
    
    async def update_single_ma(self, stock_code: str, ma_type: str, value: float) -> bool:
        """개별 MA 값 업데이트"""
        if ma_type not in ["ma20_slope", "ma20_avg_slope", "ma20"]:
            logger.error(f"❌ 잘못된 MA 타입: {ma_type}")
            return False
        
        kwargs = {ma_type: value}
        result = await self.update_tracking_data(stock_code=stock_code, **kwargs)
        return result is not None