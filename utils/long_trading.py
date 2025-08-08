# 필요한 개수만큼 자르기 (최신 데이터부터)
from datetime import datetime, timedelta,  time as datetime_time
import logging
import numpy as np
import pandas as pd
from module.kiwoom_module import KiwoomModule

logger = logging.getLogger("LongTradingAnalyzer")

class LongTradingAnalyzer:
    """0B 타입 주식 체결 데이터 분석기"""
    
    def __init__(self, kiwoom_client: KiwoomModule = None):
        """
        Args:
            kiwoom_client: 키움 API 클라이언트 인스턴스
        """
        self.kiwoom_client = kiwoom_client

    async def daily_chart_to_df(
        self, 
        stock_code: str, 
        base_dt: str = "",
        price_type: str = "1"
    ) -> pd.DataFrame:
        """Kiwoom API에서 일봉 데이터를 받아 DataFrame으로 변환 (가공 전)"""

        if not base_dt:
            now = datetime.now()
            nine_am = datetime_time(9, 0)

            if now.time() < nine_am:
                base_dt = (now - timedelta(days=1)).strftime("%Y%m%d")
            else:
                base_dt = now.strftime("%Y%m%d")
        
        response = await self.kiwoom_client.get_daily_chart(
            code=stock_code,
            base_dt=base_dt,
            price_type=price_type,
            cont_yn="N",
            next_key=""
        )

        # API 응답에서 데이터 추출
        chart_data = response.get('stk_dt_pole_chart_qry', [])

        # DataFrame 생성
        return pd.DataFrame(chart_data)   
      
    async def minute_chart_to_df( self,
                                  stock_code: str, 
                                  tic_scope: str = "1", 
                                  price_type: str = "1",
                                  cont_yn: str = "N", 
                                  next_key: str = "") -> pd.DataFrame:
        """Kiwoom API에서 일봉 데이터를 받아 DataFrame으로 변환 (가공 전)"""

        response = await self.kiwoom_client.get_minute_chart( code       = stock_code, 
                                                              tic_scope  = tic_scope, 
                                                              price_type = price_type, 
                                                              cont_yn    = cont_yn, 
                                                              next_key   = next_key)

        # API 응답에서 데이터 추출
        chart_data = response.get('stk_min_pole_chart_qry', [])

        # DataFrame 생성
        return pd.DataFrame(chart_data)  
      
      
    def process_daychart_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """일봉 DataFrame을 가공 (정렬, 컬럼명 변경, 이동평균, 기울기 등 계산)"""

        # 필요한 컬럼만 선택하고 이름 변경
        columns_to_extract = {
            'dt': 'date',       # 일자
            'open_pric': 'open', # 시가 
            'high_pric': 'high', # 고가
            'low_pric': 'low',   # 저가
            'cur_prc': 'close'   # 종가
        }
        df = df[list(columns_to_extract.keys())].rename(columns=columns_to_extract)

        # 모든 숫자 컬럼을 양수로 변환
        numeric_columns = ['open', 'high', 'low', 'close']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').abs()

        # 날짜 변환 및 정렬 (과거 → 최신)
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        df = df.sort_values('date', ascending=True).reset_index(drop=True)

        # 이동평균 계산
        df['ma5'] = df['close'].rolling(window=5, min_periods=1).mean().round().astype(int)
        df['ma10'] = df['close'].rolling(window=10, min_periods=1).mean().round().astype(int)
        df['ma20'] = df['close'].rolling(window=20, min_periods=1).mean().round().astype(int)

        # 기울기 계산
        df['ma5_slope'] = ((df['ma5'] - df['ma5'].shift(1)) / df['ma5'].shift(1) * 100).round(2)
        df['ma10_slope'] = ((df['ma10'] - df['ma10'].shift(1)) / df['ma10'].shift(1) * 100).round(2)
        df['ma20_slope'] = ((df['ma20'] - df['ma20'].shift(1)) / df['ma20'].shift(1) * 100).round(2)

        # 첫 행 slope 0 처리
        df.loc[0, ['ma5_slope', 'ma10_slope', 'ma20_slope']] = 0

        # 시가대비 종가 변화율, high-low 비율, 전일 대비 시가 변화율
        df['open_close'] = ((df['close'] - df['open']) / df['open'] * 100).round(2)
        df['high_low'] = ((df['high'] - df['low']) / df['open'] * 100).round(2)
        df['open_change'] = ((df['open'] - df['open'].shift(1)) / df['open'].shift(1) * 100).round(2)

        # 최신 → 과거순 정렬
        df = df.sort_values('date', ascending=False).reset_index(drop=True)

        return df

    def process_minchart_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """분봉 DataFrame을 가공 (정렬, 컬럼명 변경, 이동평균, 기울기 등 계산)"""
                
        # 분봉 데이터 컬럼 매핑
        columns_to_extract = {
            'cntr_tm': 'time',          # 체결시간
            'open_pric': 'open',        # 시가
            'high_pric': 'high',        # 고가
            'low_pric': 'low',          # 저가
            'cur_prc': 'close'          # 현재가(종가)
        }
        
        # 필요한 컬럼이 존재하는지 확인
        missing_cols = [col for col in columns_to_extract.keys() if col not in df.columns]
        if missing_cols:
            print(f"❌ 누락된 컬럼: {missing_cols}")
            print(f"사용 가능한 컬럼: {df.columns.tolist()}")
            return df
        
        df = df[list(columns_to_extract.keys())].rename(columns=columns_to_extract)
        
        # 모든 숫자 컬럼을 양수로 변환 (음수 값들을 절댓값으로)
        numeric_columns = ['open', 'high', 'low', 'close']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').abs()
        
        # 시간 데이터 처리 - 완전한 datetime으로 변환
        try:
            # YYYYMMDDHHMMSS 형식을 완전한 datetime으로 변환
            df['datetime'] = pd.to_datetime(df['time'], format='%Y%m%d%H%M%S')
            
            # 표시용 시간 컬럼 (HH:MM 형식)
            df['time_display'] = df['datetime'].dt.strftime('%H:%M')
            
            # 원본 time 컬럼을 datetime으로 교체
            df['time'] = df['datetime']
            df = df.drop('datetime', axis=1)  # 중복 컬럼 제거
            
        except Exception as e:
            print(f"❌ 시간 데이터 처리 오류: {str(e)}")
            return df
        
        # 시간순 정렬 (과거 → 최신)
        df = df.sort_values('time', ascending=True).reset_index(drop=True)
        
        # 이동평균 계산
        df['ma5'] = df['close'].rolling(window=5, min_periods=1).mean().round().astype(int)
        df['ma10'] = df['close'].rolling(window=10, min_periods=1).mean().round().astype(int)
        df['ma20'] = df['close'].rolling(window=20, min_periods=1).mean().round().astype(int)
        
        # 기울기 계산 (변화율)
        df['ma5_slope'] = ((df['ma5'] - df['ma5'].shift(1)) / df['ma5'].shift(1) * 1000).round(2)
        df['ma10_slope'] = ((df['ma10'] - df['ma10'].shift(1)) / df['ma10'].shift(1) * 1000).round(2)
        df['ma20_slope'] = ((df['ma20'] - df['ma20'].shift(1)) / df['ma20'].shift(1) * 1000).round(2)
        
        # 첫 행 slope NaN을 0으로 처리
        df.loc[0, ['ma5_slope', 'ma10_slope', 'ma20_slope']] = 0
        
        # 추가 지표 계산
        # df['open_close'] = ((df['close'] - df['open']) / df['open'] * 100).round(2)  # 시가대비 종가 변화율
        df['high_low'] = ((df['high'] - df['low']) / df['open'] * 100).round(2)      # high-low 비율
        # df['open_change'] = ((df['open'] - df['open'].shift(1)) / df['open'].shift(1) * 100).round(2)  # 전 분봉 대비 시가 변화율
        
        # 첫 행 open_change NaN을 0으로 처리
        # df.loc[0, 'open_change'] = 0
        
        # 최신 → 과거순 정렬
        df = df.sort_values('time', ascending=False).reset_index(drop=True)
        
        return df

    def decision_price(self, df: pd.DataFrame) -> tuple[int, int, int]:
        """
        각 이동평균선의 기울기가 0이 되는 가격을 계산
        
        Args:
            df: process_dailychart_df()로 처리된 DataFrame (최신 → 과거순 정렬)
        
        Returns:
            tuple: (ma5_decision_price, ma10_decision_price, ma20_decision_price)
                  각 이동평균선의 기울기가 0이 되는 가격
        """
        
        if df.empty or len(df) < 2:
            return (0, 0, 0)
        
        try:
            # 최신 데이터 (첫 번째 행)
            latest_row = df.iloc[0]
            
            # 현재 MA 값들
            current_ma5 = latest_row['ma5']
            current_ma10 = latest_row['ma10'] 
            current_ma20 = latest_row['ma20']
            
            # 전일 MA 값들 (두 번째 행)
            if len(df) >= 2:
                prev_row = df.iloc[1]
                prev_ma5 = prev_row['ma5']
                prev_ma10 = prev_row['ma10']
                prev_ma20 = prev_row['ma20']
            else:
                # 데이터가 부족한 경우 현재 MA 값을 반환
                return (int(current_ma5), int(current_ma10), int(current_ma20))
            
            # 기울기가 0이 되는 가격 계산
            # slope = (current_ma - prev_ma) / prev_ma * 100 = 0
            # => current_ma = prev_ma
            # 즉, 기울기가 0이 되려면 현재 MA가 전일 MA와 같아야 함
            
            # 하지만 실제로는 "다음날 기울기가 0이 되는 가격"을 원하는 것으로 해석
            # 즉, 내일의 MA가 오늘의 MA와 같아지게 하는 종가를 구하는 것
            
            # MA5의 경우: 5일 평균이므로
            # new_ma5 = (recent_4_days_sum + new_close) / 5 = current_ma5
            # => new_close = current_ma5 * 5 - recent_4_days_sum
            
            # 최근 4일간의 종가 합 (MA5용)
            if len(df) >= 4:
                recent_4_closes_ma5 = df.iloc[0:4]['close'].sum()
                ma5_decision = int(current_ma5 * 5 - recent_4_closes_ma5)
            else:
                ma5_decision = int(current_ma5)
            
            # 최근 9일간의 종가 합 (MA10용)
            if len(df) >= 9:
                recent_9_closes_ma10 = df.iloc[0:9]['close'].sum()
                ma10_decision = int(current_ma10 * 10 - recent_9_closes_ma10)
            else:
                ma10_decision = int(current_ma10)
            
            # 최근 19일간의 종가 합 (MA20용)
            if len(df) >= 19:
                recent_19_closes_ma20 = df.iloc[0:19]['close'].sum()
                ma20_decision = int(current_ma20 * 20 - recent_19_closes_ma20)
            else:
                ma20_decision = int(current_ma20)
            
            # 음수가 나오는 경우 0으로 처리
            ma5_decision = max(0, ma5_decision)
            ma10_decision = max(0, ma10_decision)
            ma20_decision = max(0, ma20_decision)
            
            return (ma5_decision, ma10_decision, ma20_decision)
            
        except Exception as e:
            print(f"❌ decision_price 계산 오류: {str(e)}")
            return (0, 0, 0)
        
    def price_expectation(self, df) -> tuple[int, int, int]:

        if len(df) < 20:
            return (df.iloc[0]['close'],df.iloc[0]['close'],df.iloc[0]['close'])
          
        return (df.iloc[4]['close'],df.iloc[9]['close'],df.iloc[19]['close'])


    def price_pattern(self, df) -> pd.DataFrame:
        """
        종가 기준으로 고점과 저점을 순차적으로 찾아 가격 패턴을 분석하고 DataFrame으로 반환
        """
        if len(df) < 3:
            return pd.DataFrame(columns=['date', 'price', 'type'])
        
        # 과거순으로 정렬 (패턴 분석을 위해)
        df_sorted = df.sort_values('date', ascending=True).reset_index(drop=True)
        
        patterns = []
        start_price = int(df_sorted.iloc[0]['close'])
        start_date = df_sorted.iloc[0]['date'].strftime('%Y-%m-%d')
        
        # 시작점 추가
        patterns.append({
            'date': start_date,
            'price': start_price,
            'type': 'start'
        })
        
        current_trend = None
        extreme_price = start_price
        extreme_date = start_date
        extreme_index = 0
        
        for i in range(1, len(df_sorted)):
            current_price = int(df_sorted.iloc[i]['close'])
            current_date = df_sorted.iloc[i]['date'].strftime('%Y-%m-%d')
            
            if current_trend is None:
                if current_price > start_price:
                    current_trend = 'up'
                    extreme_price = current_price
                    extreme_date = current_date
                    extreme_index = i
                elif current_price < start_price:
                    current_trend = 'down'
                    extreme_price = current_price
                    extreme_date = current_date
                    extreme_index = i
            
            elif current_trend == 'up':
                if current_price > extreme_price:
                    extreme_price = current_price
                    extreme_date = current_date
                    extreme_index = i
                elif current_price < extreme_price * 0.97:
                    patterns.append({
                        'date': extreme_date,
                        'price': extreme_price,
                        'type': 'high'
                    })
                    current_trend = 'down'
                    extreme_price = current_price
                    extreme_date = current_date
                    extreme_index = i
            
            elif current_trend == 'down':
                if current_price < extreme_price:
                    extreme_price = current_price
                    extreme_date = current_date
                    extreme_index = i
                elif current_price > extreme_price * 1.03:
                    patterns.append({
                        'date': extreme_date,
                        'price': extreme_price,
                        'type': 'low'
                    })
                    current_trend = 'up'
                    extreme_price = current_price
                    extreme_date = current_date
                    extreme_index = i
        
        # 마지막 극값 추가
        if current_trend == 'up' and len(patterns) > 0 and extreme_price > patterns[-1]['price']:
            patterns.append({
                'date': extreme_date,
                'price': extreme_price,
                'type': 'high'
            })
        elif current_trend == 'down' and len(patterns) > 0 and extreme_price < patterns[-1]['price']:
            patterns.append({
                'date': extreme_date,
                'price': extreme_price,
                'type': 'low'
            })
        
        # DataFrame으로 변환
        pattern_df = pd.DataFrame(patterns)
        
        # 날짜를 datetime으로 변환하고 최신순으로 정렬
        pattern_df['date'] = pd.to_datetime(pattern_df['date'])
        pattern_df = pattern_df.sort_values('date', ascending=False).reset_index(drop=True)
        
        # 날짜를 다시 문자열로 변환
        pattern_df['date'] = pattern_df['date'].dt.strftime('%Y-%m-%d')
        
        return pattern_df
      
    def get_price_rankings(self, df, periods=20):
        """
        최근 N개 데이터에서 low와 high 값의 순위별 값을 계산하는 함수
        
        Args:
            df: pandas DataFrame (date, volume, open, high, low, close, ... 컬럼 포함)
            periods: 분석할 기간 (기본값: 20)
        
        Returns:
            dict: 순위별 값이 담긴 딕셔너리
        """
        
        # 최근 N개 데이터 선택
        recent_data = df.head(periods)
        
        if len(recent_data) < periods:
            print(f"Warning: 데이터가 {periods}개 미만입니다. 사용 가능한 {len(recent_data)}개 데이터로 계산합니다.")
        
        # low 값들을 낮은 순으로 정렬
        low_values = recent_data['low'].values
        low_sorted = np.sort(low_values)  # 오름차순 정렬 (낮은 값부터)
        
        # high 값들을 높은 순으로 정렬
        high_values = recent_data['high'].values
        high_sorted = np.sort(high_values)[::-1]  # 내림차순 정렬 (높은 값부터)
        
        
        return (high_sorted.tolist(), low_sorted.tolist())
      
    def average_slope(self, df):
        """
        최근 5개의 ma5_slope, 10개의 ma10_slope, 20개의 ma20_slope의 평균을 계산하는 함수
        
        Parameters:
        df (pandas.DataFrame): 주식 데이터가 포함된 데이터프레임
                              (ma5_slope, ma10_slope, ma20_slope 컬럼 필요)
        
        Returns:
        tuple: (avg_ma5_slope, avg_ma10_slope, avg_ma20_slope)
        """
        
        # 데이터가 날짜 순으로 정렬되어 있는지 확인 (최신 데이터가 위쪽에 있음)
        # 만약 인덱스가 날짜 순서와 반대라면, 데이터를 뒤집지 않고 그대로 사용
        
        # 최근 5개의 ma5_slope 평균
        avg_ma5_slope = df['ma5_slope'].head(5).mean().round(2)
        
        # 최근 10개의 ma10_slope 평균
        avg_ma10_slope = df['ma10_slope'].head(10).mean().round(2)
        
        # 최근 20개의 ma20_slope 평균
        avg_ma20_slope = df['ma20_slope'].head(20).mean().round(2)
        
        return {'avg_ma5_slope':avg_ma5_slope,
                'avg_ma10_slope':avg_ma10_slope, 
                'avg_ma20_slope':avg_ma20_slope}

    def ma_cross_analysis(self, df):
        """
        최근 20개 데이터에서 ma5와 ma10의 상태 지속 기간을 분석하는 함수
        
        Parameters:
        df (pandas.DataFrame): 주식 데이터가 포함된 데이터프레임 (ma5, ma10 컬럼 필요)
        
        Returns:
        list: 각 상태의 지속 기간 리스트 (과거부터 현재 순)
              - 양수: ma5 >= ma10 상태의 지속 일수
              - 음수: ma5 < ma10 상태의 지속 일수
              예: [5, -3, 2] = 5일간 ma5>=ma10, 3일간 ma5<ma10, 2일간 ma5>=ma10
        """
        
        # 최근 20개 데이터 추출하고 과거부터 현재 순으로 정렬
        recent_20 = df.head(20).iloc[::-1]
        
        if len(recent_20) < 1:
            return []
        
        # 상태 리스트 생성 (True: ma5 >= ma10, False: ma5 < ma10)
        states = (recent_20['ma5'] >= recent_20['ma10']).tolist()
        
        # 연속된 상태를 그룹화
        result = []
        current_state = states[0]
        count = 1
        
        for i in range(1, len(states)):
            if states[i] == current_state:
                count += 1
            else:
                # 상태 변화 - 이전 그룹을 결과에 추가
                result.append(count if current_state else -count)
                current_state = states[i]
                count = 1
        
        # 마지막 그룹 추가
        result.append(count if current_state else -count)
        
        return result
      
    def count_high_volatility_days(self, df, threshold=3.0, column='open_close'):
        """
        지정된 컬럼의 절대값이 threshold 이상인 날의 개수를 반환
        
        Args:
            df: 주가 데이터프레임
            threshold: 변동성 임계값 (기본값: 3.0%)
            column: 분석할 컬럼명 (기본값: 'open_close')
        
        Returns:
            int: 조건을 만족하는 날의 개수
        """
        return (df[column].abs() >= threshold).sum()

    def count_high_range_days(self, df, threshold=7.0):
        """
        high_low 컬럼의 절대값이 threshold 이상인 날의 개수를 반환
        
        Args:
            df: 주가 데이터프레임 (high_low 컬럼 포함)
            threshold: 고저 변동성 임계값 (기본값: 7.0%)
        
        Returns:
            int: 조건을 만족하는 날의 개수
        """
        return (df['high_low'].abs() >= threshold).sum()

    def analyze_volatility_details(self, df, threshold=3.0, column='open_close'):
        """
        변동성 분석 상세 정보 반환
        
        Args:
            df: 주가 데이터프레임
            threshold: 변동성 임계값
            column: 분석할 컬럼명
            
        Returns:
            dict: 분석 결과 딕셔너리
        """
        high_vol_mask = df[column].abs() >= threshold
        high_vol_count = high_vol_mask.sum()
        total_days = len(df)
        
        result = {
            'high_volatility_days': high_vol_count,
            'total_days': total_days,
            'percentage': (high_vol_count / total_days * 100) if total_days > 0 else 0,
            'high_vol_dates': df[high_vol_mask]['date'].tolist() if 'date' in df.columns else [],
            'high_vol_values': df[high_vol_mask][column].tolist()
        }
        
        return result

    def analyze_range_details(self, df, threshold=7.0):
        """
        고저 변동성 분석 상세 정보 반환
        
        Args:
            df: 주가 데이터프레임
            threshold: 고저 변동성 임계값
            
        Returns:
            dict: 분석 결과 딕셔너리
        """
        return self.analyze_volatility_details(df, threshold, 'high_low')
      
    def calculate_open_close_stats(self, df, column='open_close'):
        """
        주어진 데이터에서 지정된 컬럼의 평균과 표준편차를 계산하는 메서드
        
        Parameters:
        self: 클래스 인스턴스
        df: pandas DataFrame
        column: 분석할 컬럼명 (기본값: 'open_close')
        
        Returns:
        dict: {'mean': 평균값, 'std': 표준편차, 'count': 데이터 개수, 'outlier_count': 이상치 개수}
        """
        
        # DataFrame 유효성 검사
        if not isinstance(df, pd.DataFrame):
            raise ValueError("df는 pandas DataFrame이어야 합니다.")
        
        # 컬럼 존재 여부 확인
        if column not in df.columns:
            raise ValueError(f"DataFrame에 '{column}' 컬럼이 없습니다.")
        
        # 컬럼 데이터 추출 및 NaN 값 제거
        column_values = df[column].dropna()
        
        if len(column_values) == 0:
            raise ValueError(f"유효한 {column} 데이터가 없습니다.")
        
        # 평균과 표준편차 계산
        mean_val = np.mean(column_values)
        abs_mean_val = np.mean(np.abs(column_values))
        std_val = np.std(column_values, ddof=1)  # 표본 표준편차 (N-1로 나눔)
        abs_std_val = np.std(np.abs(column_values), ddof=1)  # 표본 표준편차 (N-1로 나눔)
        
        # abs_mean + abs_std보다 큰 표본의 개수 계산
        threshold = abs_mean_val + abs_std_val
        
        # threshold 기준으로 표본 분리
        abs_values = np.abs(column_values)
        within_threshold_mask = abs_values <= threshold
        beyond_threshold_mask = abs_values > threshold
        
        # threshold 이내의 표본들
        within_threshold_values = column_values[within_threshold_mask]
        within_count = len(within_threshold_values)
        within_mean = np.mean(within_threshold_values) if within_count > 0 else 0
        within_abs_mean = np.mean(np.abs(within_threshold_values)) if within_count > 0 else 0
        
        # threshold 밖의 표본들 (outliers)
        beyond_threshold_values = column_values[beyond_threshold_mask]
        beyond_count = len(beyond_threshold_values)
        beyond_mean = np.mean(beyond_threshold_values) if beyond_count > 0 else 0
        beyond_abs_mean = np.mean(np.abs(beyond_threshold_values)) if beyond_count > 0 else 0
        
        # 절댓값이 10 이상인 표본의 개수
        abs_10_or_more_count = np.sum(np.abs(column_values) >= 10)
        
        return {
            'mean': round(mean_val, 2),
            'abs_mean': round(abs_mean_val, 2),
            'std': round(std_val, 2),
            'abs_std': round(abs_std_val, 2),
            'threshold': round(threshold, 2),
            'within_threshold_count': int(within_count),
            'within_threshold_mean': round(within_mean, 2),
            'within_threshold_abs_mean': round(within_abs_mean, 2),
            'beyond_threshold_count': int(beyond_count),
            'beyond_threshold_mean': round(beyond_mean, 2),
            'beyond_threshold_abs_mean': round(beyond_abs_mean, 2),
            'abs_10_or_more_count': int(abs_10_or_more_count),
            'total_count': len(column_values)
        }
        
    async def dailychart_to_df_old(
        self, 
        stock_code: str, 
        base_dt: str = "",
        price_type: str = "1") :
      
        response = await self.kiwoom_client.get_daily_chart(
            code=stock_code,
            base_dt=base_dt,
            price_type=price_type,
            cont_yn="N",
            next_key=""
        )
        
        # stk_dt_pole_chart_qry 배열에서 데이터 추출
        chart_data = response.get('stk_dt_pole_chart_qry', [])
        
        # DataFrame 생성
        df = pd.DataFrame(chart_data)
        
        # 필요한 컬럼만 선택하고 이름 변경
        columns_to_extract = {
            'dt'        : 'date',       # 일자
            'open_pric' : 'open',       # 시가 
            'high_pric' : 'high',       # 고가
            'low_pric'  : 'low'  ,      # 저가
            'cur_prc'   : 'close'       # 종가
        }
        
        df = df[list(columns_to_extract.keys())].rename(columns=columns_to_extract)
        
        # 모든 숫자 컬럼을 양수로 변환
        numeric_columns = ['open',  'high', 'low', 'close']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').abs()
        
        # 날짜 컬럼을 datetime으로 변환하고 정렬 (최신->과거순)
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        df = df.sort_values('date', ascending=True).reset_index(drop=True)
        
        # 이동평균 계산 (price 기준, 현재부터 과거로)
        df['ma5'] = df['close'].rolling(window=5, min_periods=1).mean().round().astype(int)
        df['ma10'] = df['close'].rolling(window=10, min_periods=1).mean().round().astype(int)
        df['ma20'] = df['close'].rolling(window=20, min_periods=1).mean().round().astype(int)
        
        # 기울기 계산 (1일 1% = 1로 표현)
        # 기울기 = ((현재값 - 전일값) / 전일값) * 100
        df['ma5_slope'] = ((df['ma5'] - df['ma5'].shift(1)) / df['ma5'].shift(1) * 100).round(2)
        df['ma10_slope'] = ((df['ma10'] - df['ma10'].shift(1)) / df['ma10'].shift(1) * 100).round(2)
        df['ma20_slope'] = ((df['ma20'] - df['ma20'].shift(1)) / df['ma20'].shift(1) * 100).round(2)
        
        # 첫 번째 행의 기울기는 0으로 설정 (비교할 전일 데이터가 없음)
        df.loc[0, ['ma5_slope', 'ma10_slope', 'ma20_slope']] = 0
        
        # 시가대비 종가 변화율 계산 (하락율)
        # 변화율 = ((종가 - 시가) / 시가) * 100
        df['open_close'] = ((df['close'] - df['open']) / df['open'] * 100).round(2)
        
        df['high_low'] = ((df['high'] - df['low']) / df['open'] * 100).round(2)
        # 전일 대비 시가변화율(전일시가 대비 금일 시가 변화율)
        # 변화율 =  (금일 시가 - 전일시가) / 전일시가 * 100
        df['open_change'] = ((df['open'] - df['open'].shift(1)) / df['open'].shift(1) * 100).round(2)

        df = df.sort_values('date', ascending=False).reset_index(drop=True)

        return df