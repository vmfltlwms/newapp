import pandas as pd
import numpy as np
import json
import asyncio
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

class StockPricePredictor:
    """
    주식 패턴을 이용한 내일 시작가 예측 시스템
    - 오늘 주식이 2% 이상 상승한 경우를 대상으로 함
    - 어제와 오늘의 패턴을 비교하여 내일 시작가를 예측
    """
    
    def __init__(self, redis_db=None):
        self.predictions = []
        self.redis_db = redis_db
    
    def parse_price(self, price_str) -> float:
        """가격 문자열을 float로 변환"""
        if isinstance(price_str, (int, float)):
            return float(price_str)
        if isinstance(price_str, str):
            # 쉼표 제거 후 float 변환
            return float(price_str.replace(',', '')) if price_str else 0.0
        return 0.0
    
    def calculate_change_rate(self, open_price: float, close_price: float) -> float:
        """주식의 변화율 계산 (시작가 대비 종가)"""
        if open_price == 0:
            return 0.0
        return ((close_price - open_price) / open_price) * 100
    
    def is_rising_stock(self, today_open: float, today_close: float) -> bool:
        """오늘 주식이 2% 이상 상승했는지 확인"""
        change_rate = self.calculate_change_rate(today_open, today_close)
        return change_rate >= 2.0
    
    def extract_stock_data(self, raw_data: Dict) -> Dict:
        """원본 데이터에서 필요한 정보 추출"""
        return {
            'stk_cd': raw_data.get('stk_cd', ''),
            'date': raw_data.get('dt', ''),
            'open': self.parse_price(raw_data.get('open_pric', 0)),
            'close': self.parse_price(raw_data.get('cur_prc', 0)),
            'high': self.parse_price(raw_data.get('high_pric', 0)),
            'low': self.parse_price(raw_data.get('low_pric', 0)),
            'volume': self.parse_price(raw_data.get('trde_qty', 0)),
            'trade_amount': self.parse_price(raw_data.get('trde_prica', 0))
        }
    
    def predict_tomorrow_open(self, yesterday_data: Dict, today_data: Dict) -> float:

        # 데이터 추출
        y_data = self.extract_stock_data(yesterday_data) if 'stk_cd' in yesterday_data else yesterday_data
        t_data = self.extract_stock_data(today_data) if 'stk_cd' in today_data else today_data
        
        y_open = y_data['open']     # 어제 시작가
        y_close = y_data['close']   # 어제 종가
        t_open = t_data['open']     # 오늘 시작가
        t_close = t_data['close']   # 오늘 종가
        
        # 오늘 주식이 2% 이상 상승했는지 확인
        if not self.is_rising_stock(t_open, t_close):
            raise ValueError(f"오늘 주식이 2% 이상 상승하지 않았습니다. (상승률: {self.calculate_change_rate(t_open, t_close):.2f}%)")
        
        # 어제 주식이 상승했는지 하락했는지 판단
        yesterday_rising = y_close > y_open
        
        if yesterday_rising:
            # 어제 주식이 상승했을 때
            return self._predict_after_rising_day(y_open, y_close, t_open, t_close)
        else:
            # 어제 주식이 하락했을 때
            return self._predict_after_falling_day(y_open, y_close, t_open, t_close)
    
    def _predict_after_rising_day(self, y_open: float, y_close: float, 
                                 t_open: float, t_close: float) -> float:
        """어제 상승 후 패턴 분석"""
        
        # 1. 오늘 시작가가 어제 종가보다 높을 때
        if t_open > y_close:
            return (t_open + t_close) / 2
        
        # 2. 오늘 시작가가 어제 시작가와 종가 사이에 있고 오늘 종가가 어제 종가보다 클 때
        elif y_open <= t_open <= y_close and t_close > y_close:
            return y_close
        
        # 3. 오늘 시작가와 종가가 어제 시작가 종가 사이에 있을 때
        elif (y_open <= t_open <= y_close) and (y_open <= t_close <= y_close):
            return (t_open + t_close) / 2
        
        # 4. 오늘 시작가가 어제 시작가보다 낮고 오늘 종가가 어제 종가보다 높을 때
        elif t_open < y_open and t_close > y_close:
            return y_close
        
        # 5. 오늘 시작가가 어제 시작가보다 낮고 오늘 종가가 어제 시작가와 종가 사이에 있을 때
        elif t_open < y_open and (y_open <= t_close <= y_close):
            return t_close
        
        # 6. 오늘 종가가 어제 시작가보다 낮을 때
        elif t_close < y_open:
            return y_open
        
        # 기본값 (예외 상황)
        else:
            return (t_open + t_close) / 2
    
    def _predict_after_falling_day(self, y_open: float, y_close: float, 
                                  t_open: float, t_close: float) -> float:
        """어제 하락 후 패턴 분석"""
        
        # 1. 오늘 시작가가 어제 종가보다 높을 때
        if t_open > y_close:
            return t_close
        
        # 2. 오늘 시작가가 어제 시작가와 종가 사이에 있고 오늘 종가가 어제 종가보다 클 때
        elif y_close <= t_open <= y_open and t_close > y_close:
            return y_open
        
        # 3. 오늘 시작가와 종가가 어제 시작가 종가 사이에 있을 때
        elif (y_close <= t_open <= y_open) and (y_close <= t_close <= y_open):
            return t_close
        
        # 4. 오늘 시작가가 어제 시작가보다 낮고 오늘 종가가 어제 종가보다 높을 때
        elif t_open < y_open and t_close > y_close:
            return y_open
        
        # 5. 오늘 시작가가 어제 시작가보다 낮고 오늘 종가가 어제 시작가와 종가 사이에 있을 때
        elif t_open < y_open and (y_close <= t_close <= y_open):
            return t_close
        
        # 6. 오늘 종가가 어제 시작가보다 낮을 때
        elif t_close < y_open:
            return y_close
        
        # 기본값 (예외 상황)
        else:
            return t_close
    
    def process_stock_data_list(self, stock_data_list: List[Dict]) -> Dict[str, List[Dict]]:
        """
        주식 데이터 리스트를 종목별로 정리
        
        Args:
            stock_data_list: 원본 데이터 리스트
            
        Returns:
            종목별로 정리된 데이터 딕셔너리
        """
        stock_groups = {}
        
        for data in stock_data_list:
            stk_cd = data.get('stk_cd', '')
            if stk_cd not in stock_groups:
                stock_groups[stk_cd] = []
            stock_groups[stk_cd].append(data)
        
        # 각 종목별로 날짜순 정렬
        for stk_cd in stock_groups:
            stock_groups[stk_cd].sort(key=lambda x: x.get('dt', ''))
        
        return stock_groups
    
    def batch_predict_from_raw_data(self, stock_data_list: List[Dict]) -> List[Dict]:
        """
        원본 데이터 리스트에서 일괄 예측
        
        Args:
            stock_data_list: 원본 주식 데이터 리스트
        
        Returns:
            predictions: 예측 결과 리스트
        """
        results = []
        
        # 종목별로 데이터 그룹화
        stock_groups = self.process_stock_data_list(stock_data_list)
        
        for stk_cd, data_list in stock_groups.items():
            if len(data_list) < 2:
                print(f"종목 {stk_cd}: 데이터가 부족합니다. (최소 2일 필요)")
                continue
            
            # 최근 2일 데이터 사용 (어제, 오늘)
            yesterday_raw = data_list[-2]
            today_raw = data_list[-1]
            
            try:
                yesterday_data = self.extract_stock_data(yesterday_raw)
                today_data = self.extract_stock_data(today_raw)
                
                predicted_open = self.predict_tomorrow_open(yesterday_raw, today_raw)
                
                change_rate = self.calculate_change_rate(
                    today_data['open'], 
                    today_data['close']
                )
                
                results.append({
                    'stk_cd': stk_cd,
                    'yesterday_date': yesterday_data['date'],
                    'yesterday_open': yesterday_data['open'],
                    'yesterday_close': yesterday_data['close'],
                    'today_date': today_data['date'],
                    'today_open': today_data['open'],
                    'today_close': today_data['close'],
                    'today_change_rate': round(change_rate, 2),
                    'predicted_tomorrow_open': round(predicted_open, 2),
                    'today_volume': today_data['volume'],
                    'today_trade_amount': today_data['trade_amount']
                })
                
            except ValueError as e:
                print(f"종목 {stk_cd}: {e}")
                continue
            except Exception as e:
                print(f"종목 {stk_cd}: 예측 중 오류 발생 - {e}")
                continue
        
        return results
    
    def print_predictions(self, predictions: List[Dict]):
        """예측 결과 출력"""
        print("=" * 100)
        print("주식 가격 예측 결과")
        print("=" * 100)
        
        for pred in predictions:
            print(f"\n종목코드: {pred['stk_cd']}")
            print(f"어제 ({pred['yesterday_date']}): 시작가 {pred['yesterday_open']:,.0f}원, 종가 {pred['yesterday_close']:,.0f}원")
            print(f"오늘 ({pred['today_date']}): 시작가 {pred['today_open']:,.0f}원, 종가 {pred['today_close']:,.0f}원 (+{pred['today_change_rate']}%)")
            print(f"오늘 거래량: {pred['today_volume']:,.0f}주, 거래대금: {pred['today_trade_amount']:,.0f}원")
            print(f"내일 예상 시작가: {pred['predicted_tomorrow_open']:,.0f}원")
            print("-" * 80)
    
    async def get_daily_chart_from_redis(self, code: str, days: int = 40) -> List[Dict]:
        """
        Redis에서 일봉 차트 데이터 조회
        
        Args:
            code (str): 종목 코드
            days (int): 조회할 일수 (기본값: 40일)
        
        Returns:
            list: 일봉 데이터 리스트 (최신순)
        """
        if not self.redis_db:
            raise ValueError("Redis 연결이 설정되지 않았습니다.")
            
        try:
            redis_key = f"redis:DAILY:{code}"
            
            # 최근 데이터부터 가져오기 (score 역순)
            raw_data = await self.redis_db.zrevrange(redis_key, 0, days - 1)
            
            results = []
            for item in raw_data:
                try:
                    parsed = json.loads(item)
                    if isinstance(parsed, dict):
                        results.append(parsed)
                except json.JSONDecodeError as e:
                    print(f"일봉 데이터 JSON 파싱 실패: {e}, 원본: {item}")
                    continue
            
            print(f"📈 Redis에서 일봉 데이터 조회 - 종목: {code}, 조회된 데이터: {len(results)}개")
            return results
            
        except Exception as e:
            print(f"Redis 일봉 데이터 조회 오류 - 종목: {code}, 오류: {str(e)}")
            return []
    
    async def predict_single_stock_from_redis(self, code: str) -> Optional[Dict]:
        """
        Redis에서 단일 종목 코드로 예측 수행
        
        Args:
            code (str): 종목 코드 (문자열)
            
        Returns:
            dict: 예측 결과 또는 None
        """
        try:
            # Redis에서 최근 2일 데이터 조회
            daily_data = await self.get_daily_chart_from_redis(code, days=2)
            
            if len(daily_data) < 2:
                print(f"종목 {code}: 예측에 필요한 데이터가 부족합니다. (필요: 2일, 보유: {len(daily_data)}일)")
                return None
            
            # 최신순으로 정렬되어 있으므로 [0]이 오늘, [1]이 어제 * 08:00 에 실행함으로 에저와 그제 데이터임! 
            today_data = daily_data[0]
            yesterday_data = daily_data[1]
            
            # 예측 수행
            predicted_open = self.predict_tomorrow_open(yesterday_data, today_data)
            
            # 결과 구성
            today_extracted = self.extract_stock_data(today_data)
            yesterday_extracted = self.extract_stock_data(yesterday_data)
            
            change_rate = self.calculate_change_rate(
                today_extracted['open'], 
                today_extracted['close']
            )
            
            result = {
                'stk_cd': code,
                'yesterday_date': yesterday_extracted['date'],
                'yesterday_open': yesterday_extracted['open'],
                'yesterday_close': yesterday_extracted['close'],
                'today_date': today_extracted['date'],
                'today_open': today_extracted['open'],
                'today_close': today_extracted['close'],
                'today_change_rate': round(change_rate, 2),
                'predicted_tomorrow_open': round(predicted_open, 2),
                'today_volume': today_extracted['volume'],
                'today_trade_amount': today_extracted['trade_amount']
            }
            
            return result
            
        except ValueError as e:
            print(f"종목 {code}: {e}")
            return None
        except Exception as e:
            print(f"종목 {code}: 예측 중 오류 발생 - {e}")
            return None

    def predict_single_stock_from_redis_sync(self, code: str) -> Optional[Dict]:
        """
        동기식 단일 종목 예측 (문자열 종목코드 입력)
        - 이벤트 루프가 이미 실행 중일 때는 사용하지 마세요
        
        Args:
            code (str): 종목 코드
            
        Returns:
            dict: 예측 결과 또는 None
        """
        if not self.redis_db:
            raise ValueError("Redis 연결이 설정되지 않았습니다.")
        
        try:
            # 현재 이벤트 루프가 실행 중인지 확인
            loop = asyncio.get_running_loop()
            if loop and loop.is_running():
                raise RuntimeError("이미 실행 중인 이벤트 루프에서는 predict_single_stock_from_redis_sync를 사용할 수 없습니다. "
                                 "대신 await predict_single_stock_from_redis(code)를 사용하세요.")
        except RuntimeError:
            # 실행 중인 루프가 없으면 정상적으로 실행
            pass
        
        return asyncio.run(self.predict_single_stock_from_redis(code))
    async def predict_from_redis(self, code: str) -> Optional[Dict]:
        """
        Redis에서 데이터를 가져와 특정 종목의 내일 시작가 예측
        
        Args:
            code (str): 종목 코드
            
        Returns:
            dict: 예측 결과 또는 None
        """
        return await self.predict_single_stock_from_redis(code)
    
    async def batch_predict_from_redis(self, stock_codes: List[str]) -> List[Dict]:
        """
        Redis에서 여러 종목 데이터를 가져와 일괄 예측
        
        Args:
            stock_codes: 종목 코드 리스트
            
        Returns:
            predictions: 예측 결과 리스트
        """
        results = []
        
        for code in stock_codes:
            try:
                prediction = await self.predict_from_redis(code)
                if prediction:
                    results.append(prediction)
                    
                # API 호출 간격 조절
                await asyncio.sleep(0.1)
                
            except Exception as e:
                print(f"종목 {code}: 예측 처리 중 오류 - {e}")
                continue
        
        return results
    
    async def find_rising_stocks_and_predict(self, stock_codes: List[str], min_change_rate: float = 2.0) -> List[Dict]:
        """
        Redis에서 상승 종목을 찾아 예측 수행
        
        Args:
            stock_codes: 검사할 종목 코드 리스트
            min_change_rate: 최소 상승률 (기본값: 2.0%)
            
        Returns:
            predictions: 조건에 맞는 종목의 예측 결과
        """
        rising_stocks = []
        predictions = []
        
        print(f"📊 상승 종목 검색 및 예측 시작 - 대상 종목: {len(stock_codes)}개")
        
        for code in stock_codes:
            try:
                # 최근 1일 데이터로 상승률 확인
                daily_data = await self.get_daily_chart_from_redis(code, days=1)
                
                if not daily_data:
                    continue
                
                today_data = self.extract_stock_data(daily_data[0])
                change_rate = self.calculate_change_rate(today_data['open'], today_data['close'])
                
                if change_rate >= min_change_rate:
                    rising_stocks.append(code)
                    print(f"📈 상승 종목 발견 - {code}: +{change_rate:.2f}%")
                
                await asyncio.sleep(0.05)  # Redis 부하 방지
                
            except Exception as e:
                print(f"종목 {code} 상승률 확인 오류: {e}")
                continue
        
        print(f"🎯 조건에 맞는 상승 종목: {len(rising_stocks)}개")
        
        # 상승 종목들에 대해 예측 수행
        if rising_stocks:
            predictions = await self.batch_predict_from_redis(rising_stocks)
        
        return predictions
    def save_predictions_to_csv(self, predictions: List[Dict], filename: str = 'stock_predictions.csv'):
        """예측 결과를 CSV 파일로 저장"""
        if predictions:
            df = pd.DataFrame(predictions)
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"예측 결과가 {filename}에 저장되었습니다.")
        else:
            print("저장할 예측 결과가 없습니다.")


