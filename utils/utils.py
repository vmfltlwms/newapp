import logging
from typing import Dict, Optional, Tuple
from datetime import datetime


logger = logging.getLogger(__name__)

async def calculate_resistance_support(ask_bid_data: Dict[str, str]) -> Tuple[float, float]:
    """
    매도저항선과 매수지지선 계산
    
    각 호가 수량의 평균을 계산하고, 평균을 초과하는 첫 호가를 지지선/저항선으로 설정
    
    Args:
        ask_bid_data: 주식호가(0D) 데이터
        
    Returns:
        (매도저항선, 매수지지선) - 계산 불가시 0.0 반환
    """
    try:
        # 1. 매도호가 데이터 추출 (1~10 호가)
        sell_prices = []
        sell_volumes = []
        
        for i in range(1, 11):
            price_key = f"{i+40}"  # 41~50: 매도호가1~10
            volume_key = f"{i+60}"  # 61~70: 매도호가수량1~10
            
            price_str = ask_bid_data.get(price_key, "0")
            volume_str = ask_bid_data.get(volume_key, "0")
            
            try:
                price = float(price_str)
                volume = int(volume_str)
                
                if price > 0:  # 호가가 있으면 추가 (수량이 0이어도 포함)
                    sell_prices.append(price)
                    sell_volumes.append(volume)
            except (ValueError, TypeError):
                continue
        
        # 2. 매수호가 데이터 추출 (1~10 호가)
        buy_prices = []
        buy_volumes = []
        
        for i in range(1, 11):
            price_key = f"{i+50}"  # 51~60: 매수호가1~10
            volume_key = f"{i+70}"  # 71~80: 매수호가수량1~10
            
            price_str = ask_bid_data.get(price_key, "0")
            volume_str = ask_bid_data.get(volume_key, "0")
            
            try:
                price = float(price_str)
                volume = int(volume_str)
                
                if price > 0:  # 호가가 있으면 추가 (수량이 0이어도 포함)
                    buy_prices.append(price)
                    buy_volumes.append(volume)
            except (ValueError, TypeError):
                continue
        
        # 3. 매도저항선 계산 (평균 초과하는 첫 매도호가)
        sell_resistance = 0.0  # 기본값 0.0
        if sell_volumes:
            # 매도호가 수량 평균 계산
            avg_sell_volume = sum(sell_volumes) / len(sell_volumes)
            
            # 평균을 초과하는 첫 매도호가 찾기
            # 매도호가는 저가부터 고가 순으로 정렬 (인덱스 0이 최저가)
            for i, volume in enumerate(sell_volumes):
                if volume > avg_sell_volume:
                    sell_resistance = sell_prices[i]
                    break
            
            # 평균을 초과하는 매도호가가 없으면 가장 높은 매도호가를 저항선으로 설정
            if sell_resistance == 0.0 and sell_prices:
                sell_resistance = sell_prices[-1]
        
        # 4. 매수지지선 계산 (평균 초과하는 첫 매수호가)
        buy_support = 0.0  # 기본값 0.0
        if buy_volumes:
            # 매수호가 수량 평균 계산
            avg_buy_volume = sum(buy_volumes) / len(buy_volumes)
            
            # 평균을 초과하는 첫 매수호가 찾기
            # 매수호가는 고가부터 저가 순으로 정렬 (인덱스 0이 최고가)
            for i, volume in enumerate(buy_volumes):
                if volume > avg_buy_volume:
                    buy_support = buy_prices[i]
                    break
            
            # 평균을 초과하는 매수호가가 없으면 가장 낮은 매수호가를 지지선으로 설정
            if buy_support == 0.0 and buy_prices:
                buy_support = buy_prices[-1]
        
        logger.debug(f"지지선: {buy_support}, 저항선: {sell_resistance}")
        
        return sell_resistance, buy_support
        
    except Exception as e:
        logger.error(f"Error calculating resistance/support: {e}")
        return 0.0, 0.0  # 오류 시 기본값 반환
    
async def calculate_buy_sell_ratio(self, buy_total: int, sell_total: int) -> Optional[float]:
        """
        매수/매도 비율 계산
        
        Args:
            buy_total: 매수호가총잔량
            sell_total: 매도호가총잔량
            
        Returns:
            매수/매도 비율 (%)
        """
        if sell_total <= 0:
            return 100.0  # 매도 잔량이 없으면 100%로 처리
            
        return (buy_total / sell_total) * 100.0
    
def convert_to_timestamp(time_str: str) -> datetime:
    """
    'HH:MM:SS:ms' 또는 'HHMMSS' 형태를 datetime 객체로 변환
    """
    try:
        # HHMMSS 형식인 경우
        if len(time_str) == 6 and time_str.isdigit():
            hour = int(time_str[:2])
            minute = int(time_str[2:4])
            second = int(time_str[4:6])
            
            today = datetime.now().date()
            return datetime(
                year=today.year, 
                month=today.month, 
                day=today.day,
                hour=hour, 
                minute=minute, 
                second=second
            )
        
        # HH:MM:SS:ms 형식인 경우
        elif ":" in time_str:
            parts = time_str.split(":")
            if len(parts) >= 3:
                hour = int(parts[0])
                minute = int(parts[1])
                second = int(parts[2])
                
                today = datetime.now().date()
                return datetime(
                    year=today.year, 
                    month=today.month, 
                    day=today.day,
                    hour=hour, 
                    minute=minute, 
                    second=second
                )
        
        # 변환 실패 시 현재 시간 반환
        return datetime.now()
    except Exception as e:
        logger.warning(f"Time conversion error: {e}")
        return datetime.now()    