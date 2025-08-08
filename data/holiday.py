import datetime

holidays = {
    datetime.date(2025, 1, 1): "신정",
    datetime.date(2025, 1, 28): "설날연휴",
    datetime.date(2025, 1, 29): "설날",
    datetime.date(2025, 1, 30): "설날연휴",
    datetime.date(2025, 3, 1): "삼일절",
    datetime.date(2025, 3, 3): "삼일절 대체공휴일",  # 삼일절이 토요일이므로 대체공휴일
    datetime.date(2025, 5, 1): "근로자의 날",  # 관공서는 쉬지 않지만 일반 기업은 유급휴일
    datetime.date(2025, 5, 5): "어린이날",  # 어린이날과 부처님오신날 동시 적용
    datetime.date(2025, 5, 6): "대체공휴일",  # 부처님오신날 대체공휴일
    datetime.date(2025, 6, 3): "현충일",
    datetime.date(2025, 8, 15): "광복절",
    datetime.date(2025, 9, 16): "추석연휴",
    datetime.date(2025, 9, 17): "추석",
    datetime.date(2025, 9, 18): "추석연휴",
    datetime.date(2025, 10, 3): "개천절",
    datetime.date(2025, 10, 8): "추석 대체공휴일",  # 추석 첫날(10/5)이 일요일이므로 대체공휴일
    datetime.date(2025, 10, 9): "한글날",
    datetime.date(2025, 12, 25): "크리스마스"
}