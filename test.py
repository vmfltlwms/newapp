import pandas as pd
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dependency_injector.wiring import inject, Provide
from container.redis_container import Redis_Container
from db.redis_db import RedisDB

logger = logging.getLogger(__name__)

class SimplifiedPriceDataAggregator:
    """단순화된 가격 데이터 집계 시스템"""
    
    @inject
    def __init__(self, redis_db: RedisDB = Provide[Redis_Container.redis_db]):
        self.redis_db = redis_db
        self.REDIS_KEY_PREFIX = "PD"
        self.EXPIRE_TIME = 60 * 30  # 30분
        
        # 최소 데이터 요구사항
        self.MIN_DATA = {
            "1min": 3,
            "5min": 15, 
            "10min": 30
        }
        
    def _get_redis_key(self, stock_code: str, time_key: str) -> str:
        """Redis 키 생성 - redis:PD:005930:09:31"""
        return f"redis:{self.REDIS_KEY_PREFIX}:{stock_code}:{time_key}"
    
    async def get_price_dataframe(self, stock_code: str) -> pd.DataFrame:
        """11분간 데이터를 DataFrame으로 조회"""
        
        from redis_util.stock_analysis import StockDataAnalyzer
        analyzer = StockDataAnalyzer()
        
        # 11분 = 660초
        raw_data = await analyzer.get_recent_0b_data(stock_code, 660)
        
        if not raw_data:
            return pd.DataFrame()
        
        # DataFrame 생성
        df = pd.DataFrame(raw_data)
        
        # execution_time을 datetime으로 변환하고 인덱스로 설정
        df['execution_time'] = pd.to_datetime(df['execution_time'], unit='s')
        df.set_index('execution_time', inplace=True)
        df.sort_index(inplace=True)
        
        return df
    
    def find_completed_minutes(self, df: pd.DataFrame) -> List[datetime]:
        """완성된 분 찾기 - 빈 분 포함"""
        if df.empty:
            return []
        df = df.sort_index()
        start = df.index[0].floor('1min')
        end = df.index[-1].floor('1min')
        all_minutes = pd.date_range(start=start, end=end, freq='1min').to_list()
        completed_minutes = all_minutes[:-1] if len(all_minutes) > 1 else []
        
        logger.debug(f"완료된 분: {[m.strftime('%H:%M') for m in completed_minutes]}")
        
        return completed_minutes
    
    def calculate_strength(self, volume_list: List[int]) -> float:
        """체결강도 계산"""
        
        buy_volume = sum(v for v in volume_list if v > 0)
        sell_volume = sum(abs(v) for v in volume_list if v < 0)
        
        if buy_volume == 0:
            return 50.0
        if sell_volume == 0:
            return 150.0
        
        return round(buy_volume / sell_volume, 2)
    
    def calculate_1min_data(self, df: pd.DataFrame, minute_time: datetime) -> Dict:
        """특정 분의 1분 데이터 계산"""
        
        # 해당 분 데이터 추출 (00:00:00 ~ 00:00:59)
        start_time = minute_time
        end_time = minute_time + timedelta(minutes=1)
        
        minute_df = df[(df.index >= start_time) & (df.index < end_time)]
        
        if len(minute_df) < self.MIN_DATA["1min"]:
            return {"status": "insufficient_data", "count": len(minute_df)}
        
        prices = minute_df['current_price']
        volumes = minute_df['volume']
        
        return {
            "timeframe": "1min",
            "ohlc": {
                "open": prices.iloc[0],
                "high": prices.max(),
                "low": prices.min(),
                "close": prices.iloc[-1],
                "avg": round(prices.mean(), 2)
            },
            "strength": self.calculate_strength(volumes.tolist()),
            "volume": volumes.abs().sum(),
            "data_count": len(minute_df),
            "status": "completed"
        }
    
    def calculate_5min_data(self, df: pd.DataFrame, current_minute: datetime) -> Dict:
        """현재 분 기준 최근 5분 데이터 계산"""
        
        # 5분 전부터 현재 분까지
        start_time = current_minute - timedelta(minutes=4)  # 4분 전
        end_time = current_minute + timedelta(minutes=1)    # 현재 분 + 1분
        
        recent_5min_df = df[(df.index >= start_time) & (df.index < end_time)]
        
        if len(recent_5min_df) < self.MIN_DATA["5min"]:
            return {"status": "insufficient_data", "count": len(recent_5min_df)}
        
        prices = recent_5min_df['current_price']
        volumes = recent_5min_df['volume']
        
        return {
            "timeframe": "5min",
            "avg_price": round(prices.mean(), 2),
            "strength": self.calculate_strength(volumes.tolist()),
            "volume": volumes.abs().sum(),
            "data_count": len(recent_5min_df),
            "status": "completed"
        }
    
    def calculate_10min_data(self, df: pd.DataFrame, current_minute: datetime) -> Dict:
        """현재 분 기준 최근 10분 데이터 계산"""
        
        # 10분 전부터 현재 분까지
        start_time = current_minute - timedelta(minutes=9)  # 9분 전
        end_time = current_minute + timedelta(minutes=1)    # 현재 분 + 1분
        
        recent_10min_df = df[(df.index >= start_time) & (df.index < end_time)]
        
        if len(recent_10min_df) < self.MIN_DATA["10min"]:
            return {"status": "insufficient_data", "count": len(recent_10min_df)}
        
        prices = recent_10min_df['current_price']
        volumes = recent_10min_df['volume']
        
        return {
            "timeframe": "10min",
            "avg_price": round(prices.mean(), 2),
            "strength": self.calculate_strength(volumes.tolist()),
            "volume": volumes.abs().sum(),
            "data_count": len(recent_10min_df),
            "status": "completed"
        }
    
    async def calculate_data(self, stock_code: str) -> bool:
        """메인 계산 함수 - 30초마다 호출"""
        
        try:
            # 1. 11분간 데이터 조회
            df = await self.get_price_dataframe(stock_code)
            
            if len(df) < 10:
                logger.warning(f"[{stock_code}] 데이터 부족: {len(df)}개")
                return False
            
            # 2. 완료된 분들 찾기
            completed_minutes = self.find_completed_minutes(df)
            
            if not completed_minutes:
                logger.debug(f"[{stock_code}] 완료된 분 없음")
                return True
            
            # 3. 각 완료된 분에 대해 계산 및 저장
            for minute_time in completed_minutes:
                time_key = minute_time.strftime('%H:%M')
                redis_key = self._get_redis_key(stock_code, time_key)
                
                # 이미 저장된 데이터가 있는지 확인
                existing_data = await self.redis_db.get(redis_key)
                if existing_data:
                    logger.debug(f"[{stock_code}] {time_key} 이미 처리됨")
                    continue
                
                # 1분, 5분, 10분 데이터 계산
                data_1min = self.calculate_1min_data(df, minute_time)
                data_5min = self.calculate_5min_data(df, minute_time)
                data_10min = self.calculate_10min_data(df, minute_time)
                
                # 결과 합치기
                result = {
                    "stock_code": stock_code,
                    "time_key": time_key,
                    "timestamp": minute_time.isoformat(),
                    "1min": data_1min,
                    "5min": data_5min,
                    "10min": data_10min,
                    "created_at": datetime.now().isoformat()
                }
                
                # Redis에 저장
                await self.redis_db.setex(
                    redis_key,
                    self.EXPIRE_TIME,
                    json.dumps(result, ensure_ascii=False)
                )
                
                logger.info(f"✅ [{stock_code}] {time_key} 데이터 저장 완료")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ [{stock_code}] 계산 실패: {e}")
            return False
    
    async def get_latest_data(self, stock_code: str) -> Optional[Dict]:
        """최신 데이터 조회 (매매 로직용)"""
        
        try:
            # 최근 10분간의 키들 생성
            now = datetime.now()
            time_keys = []
            
            for i in range(10):
                past_time = now - timedelta(minutes=i)
                time_key = past_time.strftime('%H:%M')
                time_keys.append(time_key)
            
            # Redis에서 최신 데이터 찾기
            for time_key in time_keys:
                redis_key = self._get_redis_key(stock_code, time_key)
                data = await self.redis_db.get(redis_key)
                
                if data:
                    return json.loads(data)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ [{stock_code}] 최신 데이터 조회 실패: {e}")
            return None
    
    async def get_indicators_for_trading(self, stock_code: str) -> Optional[Dict]:
        """매매용 지표 조회"""
        
        latest_data = await self.get_latest_data(stock_code)
        if not latest_data:
            return None
        
        # 1분 OHLC 데이터 안전 추출
        ohlc_1min = latest_data["1min"].get("ohlc", {}) if latest_data["1min"]["status"] == "completed" else {}
        
        return {
            "stock_code": stock_code,
            "time_key": latest_data["time_key"],
            "1min_strength": latest_data["1min"].get("strength", 100),
            "5min_strength": latest_data["5min"].get("strength", 100),
            "10min_strength": latest_data["10min"].get("strength", 100),
            "1min_open": ohlc_1min.get("open"),
            "1min_high": ohlc_1min.get("high"),
            "1min_low": ohlc_1min.get("low"),
            "1min_close": ohlc_1min.get("close"),
            "1min_avg": ohlc_1min.get("avg"),
            "5min_avg": latest_data["5min"].get("avg_price") if latest_data["5min"]["status"] == "completed" else None,
            "10min_avg": latest_data["10min"].get("avg_price") if latest_data["10min"]["status"] == "completed" else None,
            "data_quality": {
                "1min": latest_data["1min"]["status"],
                "5min": latest_data["5min"]["status"], 
                "10min": latest_data["10min"]["status"]
            }
        }
    
    async def batch_process_stocks(self, stock_codes: List[str]) -> Tuple[int, int]:
        """종목 일괄 처리"""
        
        success_count = 0
        total_count = len(stock_codes)
        
        logger.info(f"📊 {total_count}개 종목 처리 시작")
        start_time = time.time()
        
        for stock_code in stock_codes:
            try:
                success = await self.calculate_data(stock_code)
                if success:
                    success_count += 1
                    
            except Exception as e:
                logger.error(f"❌ [{stock_code}] 처리 오류: {e}")
        
        elapsed_time = time.time() - start_time
        logger.info(f"📊 처리 완료 - 성공: {success_count}/{total_count}, "
                   f"소요시간: {elapsed_time:.2f}초")
        
        return success_count, total_count