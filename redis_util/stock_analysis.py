from asyncio.log import logger
import logging
import time
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dependency_injector.wiring import inject, Provide
from container.redis_container import Redis_Container
from db.redis_db import RedisDB

logger = logging.getLogger(__name__)


class StockDataAnalyzer:
    """0B 타입 주식 체결 데이터 분석기"""
    @inject
    def __init__(self, 
                redis_db: RedisDB = Provide[Redis_Container.redis_db]):
        self.redis_db = redis_db
        
    def _get_redis_key(self, stock_code: str, type_code: str = "0B") -> str:
        """Redis 키 생성 - socket_module과 동일한 형식"""
        return f"redis:{type_code}:{stock_code}"
        
    def parse_execution_time(self, execution_time_str: str) -> float:
        """체결시간 문자열을 유닉스 타임스탬프로 변환"""
        if not execution_time_str or len(execution_time_str) != 6:
            return time.time()  # 잘못된 형식이면 현재 시간 반환
        
        try:
            # "092323" -> "09:23:23"
            hour = int(execution_time_str[:2])
            minute = int(execution_time_str[2:4])
            second = int(execution_time_str[4:6])
            
            # 오늘 날짜 기준으로 datetime 객체 생성
            now = datetime.now()
            execution_datetime = now.replace(
                hour=hour, 
                minute=minute, 
                second=second, 
                microsecond=0
            )
            
            # 유닉스 타임스탬프로 변환
            return execution_datetime.timestamp()
            
        except (ValueError, IndexError) as e:
            logger.error(f"체결시간 파싱 실패: {execution_time_str}, 오류: {e}")
            return time.time()
      
    def parse_0b_data(self, raw_data: dict) -> dict:
        """Redis에서 가져온 원시 데이터를 파싱"""
        values = raw_data.get('values', {})
        stock_code = raw_data.get('item')
        stock_code = stock_code[1:] if stock_code and stock_code.startswith('A') else stock_code

        execution_time = self.parse_execution_time(values.get('20', ''))
        
        parsed_data = {
            'stock_code': stock_code,
            'timestamp': time.time(),
            'execution_time': execution_time,                # 체결시간
            'current_price': int(values.get('10', '0')),     # 현재가
            'prev_day_diff': int(values.get('11', '0')),     # 전일대비
            'change_rate': float(values.get('12', '0')),     # 등락율
            'sell_price': int(values.get('27', '0')),        # 매도호가
            'buy_price': int(values.get('28', '0')),         # 매수호가
            'volume': int(values.get('15', '0')),            # 거래량 (+매수, -매도)
            'acc_volume': int(values.get('13', '0')),        # 누적거래량
            'acc_amount': int(values.get('14', '0')),        # 누적거래대금
            'open_price': int(values.get('16', '0')),        # 시가
            'high_price': int(values.get('17', '0')),        # 고가
            'low_price': int(values.get('18', '0')),         # 저가
            'execution_strength': float(values.get('228', '0')),  # 체결강도
            'market_cap': float(values.get('311', '0')),     # 시가총액(억)
            'buy_volume': int(values.get('1031', '0')),      # 매수체결량
            'sell_volume': int(values.get('1030', '0')),     # 매도체결량
            'buy_ratio': float(values.get('1032', '0')),     # 매수비율
            'instant_amount': int(values.get('1313', '0')),  # 순간거래대금
            'net_buy_volume': int(values.get('1314', '0')),  # 순매수체결량
            'type': '0B'
        }
        
        return parsed_data
    
    async def get_recent_0b_data(self, stock_code: str, seconds: int = 300) -> List[dict]:
        """Redis에서 최근 N초간의 0B 데이터 조회"""
        redis_key = self._get_redis_key(stock_code, "0B")
        now = time.time()
        since = now - seconds
        
        try:
            # Redis Sorted Set에서 시간 범위별 데이터 조회
            raw_data = await self.redis_db.zrangebyscore(redis_key, min=since, max=now)
            
            if not raw_data:
                logger.info(f"종목 {stock_code}의 최근 {seconds}초 데이터가 없습니다.")
                return []
            
            results = []
            for item in raw_data:
                try:
                    # JSON 파싱
                    raw_item = json.loads(item)
                    
                    # 0B 타입 데이터만 처리
                    if raw_item.get('type') == '0B':
                        parsed_data = self.parse_0b_data(raw_item)
                        results.append(parsed_data)
                        
                except json.JSONDecodeError as e:
                    logger.error(f"0B 데이터 JSON 파싱 실패: {e}")
                    continue
                except Exception as e:
                    logger.error(f"0B 데이터 처리 중 오류: {e}")
                    continue

            # logger.info(f"종목 {stock_code}: {len(results)}개의 0B 데이터 조회됨 (최근 {seconds}초)")
            return results
            
        except Exception as e:
            logger.error(f"Redis에서 데이터 조회 실패 - 종목: {stock_code}, 오류: {e}")
            return []
        
    def calculate_5min_execution_strength(self, data_list: List[dict]) -> float:
        """5분간 체결강도 계산 (가중평균)"""
        if not data_list:
            return 0.0
        
        total_strength = 0.0
        total_volume = 0
        
        for data in data_list:
            volume = abs(data.get('volume', 0))
            strength = data.get('execution_strength', 0)
            
            if volume > 0 and strength > 0:
                total_strength += strength * volume
                total_volume += volume
        
        if total_volume == 0:
            return 0.0
        
        return round(total_strength / total_volume, 2)
    
    def calculate_volume_metrics(self, data_list: List[dict]) -> Tuple[int, int, int]:
        """거래량 지표 계산"""
        if not data_list:
            return 0, 0, 0
        
        total_volume = 0      # 총 거래량
        buy_volume = 0        # 매수 거래량
        sell_volume = 0       # 매도 거래량
        
        for data in data_list:
            volume = data.get('volume', 0)
            total_volume += abs(volume)
            
            if volume > 0:  # 양수면 매수
                buy_volume += volume
            elif volume < 0:  # 음수면 매도
                sell_volume += abs(volume)
        
        return total_volume, buy_volume, sell_volume
    
    def calculate_price_momentum(self, data_list: List[dict]) -> dict:
        """가격 모멘텀 계산"""
        if len(data_list) < 2:
            return {
                "price_change": 0,
                "price_change_rate": 0.0,
                "momentum": "FLAT"
            }
        
        # 최신 데이터와 가장 오래된 데이터 비교
        latest = data_list[-1]
        oldest = data_list[0]
        
        latest_price = latest.get('current_price', 0)
        oldest_price = oldest.get('current_price', 0)
        
        if oldest_price == 0:
            return {
                "price_change": 0,
                "price_change_rate": 0.0,
                "momentum": "FLAT"
            }
        
        price_change = latest_price - oldest_price
        price_change_rate = (price_change / oldest_price) * 100
        
        if price_change > 0:
            momentum = "UP"
        elif price_change < 0:
            momentum = "DOWN"
        else:
            momentum = "FLAT"
        
        return {
            "price_change": price_change,
            "price_change_rate": round(price_change_rate, 2),
            "momentum": momentum
        }
    
    def calculate_additional_metrics(self, data_list: List[dict]) -> dict:
        """추가 지표 계산"""
        if not data_list:
            return {
                "avg_execution_strength": 0.0,
                "max_volume": 0,
                "min_volume": 0,
                "price_volatility": 0.0
            }
        
        # 평균 체결강도
        strengths = [data.get('execution_strength', 0) for data in data_list if data.get('execution_strength', 0) > 0]
        avg_strength = sum(strengths) / len(strengths) if strengths else 0.0
        
        # 거래량 최대/최소
        volumes = [abs(data.get('volume', 0)) for data in data_list]
        max_volume = max(volumes) if volumes else 0
        min_volume = min(volumes) if volumes else 0
        
        # 가격 변동성 (표준편차)
        prices = [data.get('current_price', 0) for data in data_list if data.get('current_price', 0) > 0]
        if len(prices) > 1:
            avg_price = sum(prices) / len(prices)
            variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
            volatility = variance ** 0.5
        else:
            volatility = 0.0
        
        return {
            "avg_execution_strength": round(avg_strength, 2),
            "max_volume": max_volume,
            "min_volume": min_volume,
            "price_volatility": round(volatility, 2)
        }
    
    async def analyze_stock_0b(self, stock_code: str) -> dict:
        """종목의 0B 데이터 종합 분석 - Redis에서 데이터를 읽어와 분석"""
        try:
            # Redis에서 데이터 조회
            data_5min = await self.get_recent_0b_data(stock_code, 300)  # 5분
            data_1min = await self.get_recent_0b_data(stock_code, 60)   # 1분
            
            if not data_5min:
                return {
                    "stock_code": stock_code,
                    "error": "No data available",
                    "timestamp": time.time(),
                    "message": f"종목 {stock_code}의 0B 데이터가 없습니다."
                }
            
            # 최신 데이터
            latest_data = data_5min[-1] if data_5min else {}
            
            # 5분간 지표 계산
            strength_5min = self.calculate_5min_execution_strength(data_5min)
            total_vol_5min, buy_vol_5min, sell_vol_5min = self.calculate_volume_metrics(data_5min)
            momentum_5min = self.calculate_price_momentum(data_5min)
            additional_5min = self.calculate_additional_metrics(data_5min)
            
            # 1분간 지표 계산
            strength_1min = self.calculate_5min_execution_strength(data_1min)
            total_vol_1min, buy_vol_1min, sell_vol_1min = self.calculate_volume_metrics(data_1min)
            momentum_1min = self.calculate_price_momentum(data_1min)
            additional_1min = self.calculate_additional_metrics(data_1min)
            
            # 매수/매도 비율 계산
            buy_ratio_5min = (buy_vol_5min / total_vol_5min * 100) if total_vol_5min > 0 else 0
            sell_ratio_5min = (sell_vol_5min / total_vol_5min * 100) if total_vol_5min > 0 else 0
            
            buy_ratio_1min = (buy_vol_1min / total_vol_1min * 100) if total_vol_1min > 0 else 0
            sell_ratio_1min = (sell_vol_1min / total_vol_1min * 100) if total_vol_1min > 0 else 0
            
            analysis_result = {
                "stock_code": stock_code,
                "timestamp": time.time(),
                "latest_data": {
                    "current_price": latest_data.get('current_price', 0),
                    "execution_time": latest_data.get('execution_time', ''),
                    "execution_strength": latest_data.get('execution_strength', 0),
                    "volume": latest_data.get('volume', 0),
                    "change_rate": latest_data.get('change_rate', 0),
                    "buy_price": latest_data.get('buy_price', 0),
                    "sell_price": latest_data.get('sell_price', 0),
                },
                "analysis_5min": {
                    "execution_strength": strength_5min,
                    "total_volume": total_vol_5min,
                    "buy_volume": buy_vol_5min,
                    "sell_volume": sell_vol_5min,
                    "buy_ratio": round(buy_ratio_5min, 2),
                    "sell_ratio": round(sell_ratio_5min, 2),
                    "momentum": momentum_5min,
                    "additional_metrics": additional_5min,
                    "data_points": len(data_5min)
                },
                "analysis_1min": {
                    "execution_strength": strength_1min,
                    "total_volume": total_vol_1min,
                    "buy_volume": buy_vol_1min,
                    "sell_volume": sell_vol_1min,
                    "buy_ratio": round(buy_ratio_1min, 2),
                    "sell_ratio": round(sell_ratio_1min, 2),
                    "momentum": momentum_1min,
                    "additional_metrics": additional_1min,
                    "data_points": len(data_1min)
                }
            }
            
            # logger.info(f"종목 {stock_code} 분석 완료 - 5분: {len(data_5min)}개, 1분: {len(data_1min)}개 데이터 처리")
            return analysis_result
            
        except Exception as e:
            logger.error(f"종목 {stock_code} 분석 중 오류 발생: {e}")
            return {
                "stock_code": stock_code,
                "error": str(e),
                "timestamp": time.time()
            }

    async def get_multiple_stock_analysis(self, stock_codes: List[str]) -> Dict[str, dict]:
        """여러 종목의 0B 데이터 분석"""
        results = {}
        
        for stock_code in stock_codes:
            try:
                analysis = await self.analyze_stock_0b(stock_code)
                results[stock_code] = analysis
            except Exception as e:
                logger.error(f"종목 {stock_code} 분석 실패: {e}")
                results[stock_code] = {
                    "stock_code": stock_code,
                    "error": str(e),
                    "timestamp": time.time()
                }
        
        return results

    async def get_data_status(self, stock_code: str) -> dict:
        """특정 종목의 데이터 상태 확인"""
        redis_key = self._get_redis_key(stock_code, "0B")
        
        try:
            # 전체 데이터 개수
            total_count = await self.redis_db.zcard(redis_key)
            
            # 최근 5분간 데이터 개수
            now = time.time()
            recent_5min = await self.redis_db.zcount(redis_key, now - 300, now)
            recent_1min = await self.redis_db.zcount(redis_key, now - 60, now)
            
            # 가장 최근 데이터와 가장 오래된 데이터의 시간
            oldest_data = await self.redis_db.zrange(redis_key, 0, 0, withscores=True)
            newest_data = await self.redis_db.zrange(redis_key, -1, -1, withscores=True)
            
            oldest_time = oldest_data[0][1] if oldest_data else None
            newest_time = newest_data[0][1] if newest_data else None
            
            return {
                "stock_code": stock_code,
                "redis_key": redis_key,
                "total_data_points": total_count,
                "recent_5min_points": recent_5min,
                "recent_1min_points": recent_1min,
                "oldest_data_time": oldest_time,
                "newest_data_time": newest_time,
                "data_span_seconds": (newest_time - oldest_time) if (oldest_time and newest_time) else 0,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"종목 {stock_code} 데이터 상태 확인 실패: {e}")
            return {
                "stock_code": stock_code,
                "error": str(e),
                "timestamp": time.time()
            }