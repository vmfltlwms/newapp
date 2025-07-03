from asyncio.log import logger
import logging, time, json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dependency_injector.wiring import inject, Provide
from container.redis_container import Redis_Container
from db.redis_db import RedisDB
import pandas as pd



logger = logging.getLogger(__name__)


class StockDataAnalyzer:
    """0B 타입 주식 체결 데이터 분석기"""
    @inject
    def __init__(self, 
                redis_db: RedisDB = Provide[Redis_Container.redis_db]):
        self.redis_db = redis_db
        self.REDIS_KEY_PREFIX = "PD"
        self.EXPIRE_TIME = 60 * 30  # 30분
        # 최소 데이터 요구사항
        self.MIN_DATA = {
            "1min": 3,
            "5min": 15, 
            "10min": 30
        }

    def _get_redis_key(self, stock_code: str, type_code : str, time_key:Optional[str] = None) -> str:

        if time_key :
            return f"redis:{type_code}:{stock_code}:{time_key}"
        else : return f"redis:{type_code}:{stock_code}"
      
      
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

            return results
            
        except Exception as e:
            logger.error(f"Redis에서 데이터 조회 실패 - 종목: {stock_code}, 오류: {e}")
            return []
        
    async def get_price_dataframe(self, stock_code: str) -> pd.DataFrame:
        """11분간 데이터를 DataFrame으로 조회"""
        
        # 11분 = 660초
        raw_data = await self.get_recent_0b_data(stock_code, 660)

        if not raw_data:
            logging.warning(f"No data received for stock_code: {stock_code}")
            return pd.DataFrame()
        
        try:
            # DataFrame 생성
            df = pd.DataFrame(raw_data)
            
            # 필요한 컬럼이 있는지 확인

            required_columns = [ 'current_price', 'volume', 'acc_volume', 
                  'open_price', 'execution_strength', 'buy_ratio']
            
            # execution_time을 datetime으로 변환하고 인덱스로 설정
            df['execution_time'] = pd.to_datetime(df['execution_time'], unit='s')
            df.set_index('execution_time', inplace=True)
            df.sort_index(inplace=True)
            df = df[required_columns]
            
            abs_columns = ['current_price', 'open_price', 'execution_strength', 'buy_ratio']
            for col in abs_columns:
                if col in df.columns:
                    df[col] = df[col].abs()
            
            # 데이터 타입 최적화
            df = df.astype({
                'current_price': 'int32',
                'volume': 'int32', 
                'acc_volume': 'int64',  # 누적거래량은 클 수 있으므로 int64
                'open_price': 'int32',
                'execution_strength': 'float32',
                'buy_ratio': 'float32'
            }, errors='ignore')
      
        
            logging.info(f"Successfully processed {len(df)} records for {stock_code}")
            return df
            
        except Exception as e:
            logging.error(f"Error processing data for {stock_code}: {str(e)}")
            return pd.DataFrame()
    
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
        strength = round(buy_volume / sell_volume, 2) * 100
        strength = max(50,min(200, strength))
        return round(strength, 2)
    
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
                "open": int(prices.iloc[0]),        # int()로 변환
                "high": int(prices.max()),          # int()로 변환
                "low": int(prices.min()),           # int()로 변환
                "close": int(prices.iloc[-1]),      # int()로 변환
                "avg": round(float(prices.mean()), 2)  # float()로 변환
            },
            "strength": self.calculate_strength(volumes.tolist()),
            "volume": int(volumes.abs().sum()),     # int()로 변환
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
            "avg_price": round(float(prices.mean()), 2),  # float()로 변환
            "strength": self.calculate_strength(volumes.tolist()),
            "volume": int(volumes.abs().sum()),           # int()로 변환
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
            "avg_price": round(float(prices.mean()), 2),  # float()로 변환
            "strength": self.calculate_strength(volumes.tolist()),
            "volume": int(volumes.abs().sum()),           # int()로 변환
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
                redis_key = self._get_redis_key(stock_code,self.REDIS_KEY_PREFIX, time_key)
                
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
                logger.info(f"time_key => {time_key}")
                time_keys.append(time_key)
            
            # Redis에서 최신 데이터 찾기
            for time_key in time_keys:
                redis_key = self._get_redis_key(stock_code,self.REDIS_KEY_PREFIX, time_key)
                
                logger.info(f"redis_key  => {redis_key}")
                data = await self.redis_db.get(redis_key)
                logger.info(f"redis_key data => {data}")

                if data:
                    return json.loads(data)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ [{stock_code}] 최신 데이터 조회 실패: {e}")
            return None
    
    async def get_trading_data(self, stock_code: str) -> Optional[Dict]:
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
        
        
        