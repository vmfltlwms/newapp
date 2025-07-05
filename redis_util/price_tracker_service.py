# services/price_tracker_service.py (성능 최적화)
import json
import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass
from dependency_injector.wiring import inject, Provide
from container.redis_container import Redis_Container
from db.redis_db import RedisDB

logger = logging.getLogger(__name__)

@dataclass
class PriceTrackingData:
    """가격 추적 데이터 클래스"""
    stock_code    : str     # 주식코드
    isfirst       : bool    # 처음 실행여부
    isafternoon   : bool    # 오후 처음 실행여부
    current_price : int     # 현재가 (성능 최적화를 위해 추가)
    highest_price : int     # 최고가
    lowest_price  : int     # 최저가
    trade_price   : int     # 매매 체결가
    period_type   : bool    # 기간 타입(False : 단기, True : 장기)
    trade_time    : float   # 매매 체결 시간
    last_updated  : float   # 마지막 업데이트 시간
    qty_to_sell   : int     # 매도 할 수 있는 주식 수 
    qty_to_buy    : int     # 매수 할 수 있는 주식 수
    trade_type    : str     # BUY, SELL, HOLD

class PriceTracker:
    """성능 최적화된 주식 가격 추적 서비스"""
    
    def __init__(self,
                 redis_db: RedisDB = Provide[Redis_Container.redis_db]):
        self.redis_db = redis_db
        self.REDIS_KEY_PREFIX = "PT"
        self.EXPIRE_TIME = 60 * 60 * 8  # 8시간
        self.UPDATE_THRESHOLD = 5  # 5초 이내 중복 업데이트 방지
    
    def _get_redis_key(self, stock_code: str) -> str:
        """Redis 키 생성"""
        return f"redis:{self.REDIS_KEY_PREFIX}:{stock_code}"
    
    def _to_hash_data(self, tracking_data: PriceTrackingData) -> Dict[str, str]:
        """PriceTrackingData를 Redis Hash 형식으로 변환"""
        return {
            "stock_code": tracking_data.stock_code,
            "isfirst": str(tracking_data.isfirst),
            "current_price": str(tracking_data.current_price),  # 추가
            "highest_price": str(tracking_data.highest_price),
            "lowest_price": str(tracking_data.lowest_price),
            "trade_price": str(tracking_data.trade_price),
            "period_type": str(tracking_data.period_type),
            "trade_time": str(tracking_data.trade_time),
            "last_updated": str(tracking_data.last_updated),
            "qty_to_sell": str(tracking_data.qty_to_sell),
            "qty_to_buy": str(tracking_data.qty_to_buy),
            "trade_type": tracking_data.trade_type
        }
    
    def _from_hash_data(self, hash_data: Dict[str, str]) -> Dict:
        """Redis Hash 데이터를 파이썬 딕셔너리로 변환"""
        if not hash_data:
            return {}
        
        return {
            "stock_code": hash_data.get("stock_code", ""),
            "isfirst": hash_data.get("isfirst", "True").lower() == "true",
            "current_price": int(hash_data.get("current_price", "0")),  # 추가
            "highest_price": int(hash_data.get("highest_price", "0")),
            "lowest_price": int(hash_data.get("lowest_price", "0")),
            "trade_price": int(hash_data.get("trade_price", "0")),
            "period_type": hash_data.get("period_type", "False").lower() == "true",
            "trade_time": float(hash_data.get("trade_time", "0")),
            "last_updated": float(hash_data.get("last_updated", "0")),
            "qty_to_sell": int(hash_data.get("qty_to_sell", "0")),
            "qty_to_buy": int(hash_data.get("qty_to_buy", "0")),
            "trade_type": hash_data.get("trade_type", "HOLD")
        }
    
    async def initialize_tracking(self, 
                                  stock_code    : str, 
                                  current_price : Optional[int] = 0,     
                                  trade_price   : Optional[int] = 0, 
                                  period_type   : Optional[bool] = False, 
                                  isfirst       : Optional[bool] = False,
                                  isafternoon   : Optional[bool] = True,
                                  qty_to_sell   : Optional[int] = 0,
                                  qty_to_buy    : Optional[int] = 0,
                                  trade_type    : Optional[str] = "HOLD") -> bool:
        """새로운 가격 추적 시작"""
        update_price = trade_price if trade_price != 0 else current_price
        
        try:
            current_timestamp = time.time()
            
            tracking_data = PriceTrackingData(
                stock_code    = stock_code,
                isfirst       = isfirst,
                isafternoon   = isafternoon,
                current_price = current_price,
                highest_price = update_price,
                lowest_price  = update_price,
                trade_price   = trade_price,
                period_type   = period_type,
                trade_time    = current_timestamp,
                last_updated  = current_timestamp,
                qty_to_sell   = qty_to_sell,
                qty_to_buy    = qty_to_buy,
                trade_type    = trade_type
            )
            
            redis_key = self._get_redis_key(stock_code)
            hash_data = self._to_hash_data(tracking_data)
            
            # Redis Hash에 일괄 저장
            await self.redis_db.hset(redis_key, mapping=hash_data)
            await self.redis_db.expire(redis_key, self.EXPIRE_TIME)
            
            # logger.info(f"🎯 가격 추적 초기화 - 종목: {stock_code}, 체결가: {current_price}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 가격 추적 초기화 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return False
    
    async def update_tracking_data(self, 
                                  stock_code: str,
                                  current_price: Optional[int] = None,
                                  trade_price: Optional[int] = None,
                                  qty_to_sell: Optional[int] = None,
                                  qty_to_buy: Optional[int] = None,
                                  period_type: Optional[bool] = None,
                                  trade_type: Optional[str] = None,
                                  isfirst: Optional[bool] = None,
                                  isafternoon: Optional[bool] = None,
                                  reset_extremes: bool = False,
                                  force_update: bool = False) -> Optional[Dict]:
 
        try:
            redis_key = self._get_redis_key(stock_code)

            
            # 기존 데이터 존재 확인
            if not await self.redis_db.exists(redis_key):
                logger.debug(f"종목 {stock_code}의 가격 추적 데이터가 없습니다.")
                return None
            
            
            update_fields = {}
            updated = False
            current_time = time.time()
            
            # 강제로 최고가 최저가 업데이트
            if current_price is not None and  force_update:
                update_fields["highest_price"] = str(current_price)
                update_fields["lowest_price"] = str(current_price)
                updated = True
                logger.info(f"🔄 최고가/최저가 초기화 - 종목: {stock_code}, 가격: {trade_price}")
                
            # 거래가 업데이트 (새로운 거래 발생)
            if trade_price is not None:
                update_fields["trade_price"] = str(trade_price)
                update_fields["trade_time"] = str(current_time)
                updated = True
                logger.info(f"💰 거래가 업데이트 - 종목: {stock_code}, 가격: {trade_price}")
                
                # 새 거래시 최고가/최저가 초기화
                if reset_extremes:
                    update_fields["highest_price"] = str(trade_price)
                    update_fields["lowest_price"] = str(trade_price)
                    logger.info(f"🔄 최고가/최저가 초기화 - 종목: {stock_code}, 가격: {trade_price}")
            
            # 현재가 및 최고가/최저가 업데이트 (최적화된 방식)
            if current_price is not None:
                update_fields["current_price"] = str(current_price)
                updated = True
                
                # 한 번에 최고가/최저가 조회
                pipe = self.redis_db.pipeline()
                pipe.hget(redis_key, "highest_price")
                pipe.hget(redis_key, "lowest_price")
                results = await pipe.execute()
                
                highest_price_str, lowest_price_str = results
                
                if highest_price_str and lowest_price_str:
                    highest_price = int(highest_price_str)
                    lowest_price = int(lowest_price_str)
                    
                    # 최고가 갱신
                    if current_price > highest_price:
                        update_fields["highest_price"] = str(current_price)

                    # 최저가 갱신
                    if current_price < lowest_price:
                        update_fields["lowest_price"] = str(current_price)

              
            # 나머지 필드들 업데이트
            if qty_to_sell is not None:
                update_fields["qty_to_sell"] = str(qty_to_sell)
                updated = True
            
            if qty_to_buy is not None:
                update_fields["qty_to_buy"] = str(qty_to_buy)
                updated = True
            
            if trade_type is not None:
                update_fields["trade_type"] = trade_type
                updated = True
            
            if period_type is not None:
                update_fields["period_type"] = str(period_type)
                updated = True
            
            if isfirst is not None:
                update_fields["isfirst"] = str(isfirst)
                updated = True
                
            if isafternoon is not None:
                update_fields["isafternoon"] = str(isafternoon)
                updated = True            
                
            if updated:
                update_fields["last_updated"] = str(current_time)
                await self.redis_db.hset(redis_key, mapping=update_fields)
                await self.redis_db.expire(redis_key, self.EXPIRE_TIME)
                logger.debug(f"✅ 업데이트 완료 - 종목: {stock_code}")
            
            # 업데이트된 전체 데이터 반환
            return await self.get_tracking_data(stock_code)
            
        except Exception as e:
            logger.error(f"❌ 업데이트 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None
    
    async def get_price_info(self, stock_code: str) -> Optional[Dict]:
        """빠른 가격 정보 조회 (필요한 필드만)"""
        try:
            redis_key = self._get_redis_key(stock_code)
            
            # Pipeline으로 필요한 필드만 조회
            pipe = self.redis_db.pipeline()
            pipe.hget(redis_key, "current_price")
            pipe.hget(redis_key, "highest_price")
            pipe.hget(redis_key, "lowest_price")
            pipe.hget(redis_key, "trade_price")
            pipe.hget(redis_key, "trade_type")
            results = await pipe.execute()
            
            current_price_str, highest_price_str, lowest_price_str, trade_price_str, trade_type = results
            
            if not all([current_price_str, highest_price_str, lowest_price_str, trade_price_str]):
                return None
            
            current_price = int(current_price_str)
            highest_price = int(highest_price_str)
            lowest_price = int(lowest_price_str)
            trade_price = int(trade_price_str)
            
            return {
                "stock_code": stock_code,
                "current_price": current_price,
                "highest_price": highest_price,
                "lowest_price": lowest_price,
                "trade_price": trade_price,
                "trade_type": trade_type,
                "change_from_trade": round(((current_price - trade_price) / trade_price) * 100, 2) if trade_price > 0 else 0,
                "highest_gain": round(((highest_price - trade_price) / trade_price) * 100, 2) if trade_price > 0 else 0,
                "lowest_loss": round(((lowest_price - trade_price) / trade_price) * 100, 2) if trade_price > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"❌ 빠른 가격 정보 조회 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None
    
    async def get_tracking_data(self, stock_code: str) -> Optional[Dict]:
        """전체 추적 데이터 조회"""
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
        """
        첫 실행 여부 확인
        
        Args:
            stock_code: 종목코드
            
        Returns:
            bool: 첫 실행 여부 또는 None (데이터가 없는 경우)
        """
        try:
            redis_key = self._get_redis_key(stock_code)
            
            # isfirst 필드만 조회 (성능 최적화)
            isfirst_str = await self.redis_db.hget(redis_key, "isfirst")
            
            if isfirst_str is None:
                logger.debug(f"종목 {stock_code}의 추적 데이터가 존재하지 않습니다.")
                return None
            
            # 문자열을 boolean으로 변환
            isfirst_value = isfirst_str.lower() == "true"
            
            logger.debug(f"종목 {stock_code}의 첫 실행 여부: {isfirst_value}")
            return isfirst_value
            
        except Exception as e:
            logger.error(f"❌ 첫 실행 여부 확인 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None

    async def isafternoon(self, stock_code: str) -> Optional[bool]:
        """
        첫 실행 여부 확인
        
        Args:
            stock_code: 종목코드
            
        Returns:
            bool: 첫 실행 여부 또는 None (데이터가 없는 경우)
        """
        try:
            redis_key = self._get_redis_key(stock_code)
            
            # isfirst 필드만 조회 (성능 최적화)
            isafternoon_str = await self.redis_db.hget(redis_key, "isafternoon")
            
            if isafternoon_str is None:
                logger.debug(f"종목 {stock_code}의 추적 데이터가 존재하지 않습니다.")
                return None
            
            # 문자열을 boolean으로 변환
            isafternoon_value = isafternoon_str.lower() == "true"
            
            logger.debug(f"종목 {stock_code}의 첫 실행 여부: {isafternoon_value}")
            return isafternoon_value
            
        except Exception as e:
            logger.error(f"❌ 첫 실행 여부 확인 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None

    async def set_isafternoon(self, stock_code: str, isafternoon: bool ) -> Optional[bool]:
        """
        첫 실행 여부 설정
        
        Args:
            stock_code: 종목코드
            isfirst: 설정할 첫 실행 여부
            
        Returns:
            bool: 설정 성공 여부
        """
        try:
            redis_key = self._get_redis_key(stock_code)
            
            # 데이터 존재 확인
            if not await self.redis_db.exists(redis_key):
                logger.debug(f"종목 {stock_code}의 가격 추적 데이터가 없습니다.")
                return False
            
            # isfirst 필드 업데이트
            await self.redis_db.hset(redis_key, "isafternoon", str(isafternoon))
            await self.redis_db.expire(redis_key, self.EXPIRE_TIME)
            
            logger.info(f"✅ 첫 실행 여부 설정 완료 - 종목: {stock_code}, isfirst: {isafternoon}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 첫 실행 여부 설정 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return False
          
    async def set_isfirst(self, stock_code: str, isfirst: bool) -> bool:
        """
        첫 실행 여부 설정
        
        Args:
            stock_code: 종목코드
            isfirst: 설정할 첫 실행 여부
            
        Returns:
            bool: 설정 성공 여부
        """
        try:
            redis_key = self._get_redis_key(stock_code)
            
            # 데이터 존재 확인
            if not await self.redis_db.exists(redis_key):
                logger.debug(f"종목 {stock_code}의 가격 추적 데이터가 없습니다.")
                return False
            
            # isfirst 필드 업데이트
            await self.redis_db.hset(redis_key, "isfirst", str(isfirst))
            await self.redis_db.expire(redis_key, self.EXPIRE_TIME)
            
            logger.info(f"✅ 첫 실행 여부 설정 완료 - 종목: {stock_code}, isfirst: {isfirst}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 첫 실행 여부 설정 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return False