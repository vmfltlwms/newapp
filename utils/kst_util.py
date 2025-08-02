from datetime import datetime
from zoneinfo import ZoneInfo

# 전역 시간대 설정
KST = ZoneInfo("Asia/Seoul")


def get_kst_now() -> datetime:
    """KST 기준 현재 시간 (naive - DB 저장용)"""
    return datetime.now(KST).replace(tzinfo=None)

def kst_to_naive(dt: datetime) -> datetime:
    """KST datetime을 naive로 변환 (시간 값 유지)"""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

def timestamp_to_kst(timestamp: float) -> datetime:
    """Unix timestamp를 KST naive datetime으로 변환"""
    return datetime.fromtimestamp(timestamp, tz=KST).replace(tzinfo=None)

def time_string_to_kst(time_str: str) -> datetime:
    """시간 문자열을 KST naive datetime으로 변환"""
    # HHMMSS 또는 HH:MM:SS 형식 처리
    if len(time_str) == 6 and time_str.isdigit():
        hour = int(time_str[:2])
        minute = int(time_str[2:4])
        second = int(time_str[4:6])
    elif ":" in time_str:
        parts = time_str.split(":")
        hour, minute, second = int(parts[0]), int(parts[1]), int(parts[2])
    else:
        return get_kst_now()
      
    today = get_kst_now().date()
    return datetime(today.year, today.month, today.day, hour, minute, second)