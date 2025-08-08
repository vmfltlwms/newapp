import asyncio
import datetime
import logging
import signal
import sys
from typing import Optional, Tuple
import uvicorn

# config import를 지연 로딩으로 변경
try:
    from config import settings
except ImportError:
    # settings가 없는 경우 기본값 사용
    class DefaultSettings:
        DEBUG = False
    settings = DefaultSettings()


class ScheduledServerManager:
    """시간 기반 서버 자동 시작/종료 관리자"""
    
    def __init__(self, 
                 start_time: str = "09:00",
                 end_time: str = "15:30",
                 host: str = "0.0.0.0",
                 port: int = 8080,
                 app_module: str = "main:app",
                 reload: bool = False):
        """
        Args:
            start_time: 시작 시간 (HH:MM 형식)
            end_time: 종료 시간 (HH:MM 형식)  
            host: 서버 호스트
            port: 서버 포트
            app_module: FastAPI 앱 모듈 경로
            reload: 리로드 모드
        """
        self.start_time = self._parse_time(start_time)
        self.end_time = self._parse_time(end_time)
        self.host = host
        self.port = port
        self.app_module = app_module
        self.reload = reload
        self.server: Optional[uvicorn.Server] = None
        self.running = False
        self.logger = logging.getLogger(self.__class__.__name__)  # 클래스별 로거 이름
        
        # 강제 종료 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _parse_time(self, time_str: str) -> datetime.time:
        """시간 문자열을 time 객체로 변환"""
        try:
            hour, minute = map(int, time_str.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("시간 범위 오류")
            return datetime.time(hour, minute)
        except (ValueError, AttributeError) as e:
            raise ValueError(f"잘못된 시간 형식: {time_str}. HH:MM 형식을 사용하세요. (예: 09:00)")
    
    def _signal_handler(self, signum, frame):
        """시그널 핸들러 (Ctrl+C 등)"""
        self.logger.info(f"종료 시그널 수신: {signum}")
        self.running = False
        # sys.exit(0) 제거 - 자연스러운 종료를 위해
    
    def _get_current_time(self) -> datetime.time:
        """현재 시간 반환"""
        return datetime.datetime.now().time()
    
    def _is_within_schedule(self) -> bool:
        """현재 시간이 운영 시간 내인지 확인"""
        current_time = self._get_current_time()
        
        if self.start_time <= self.end_time:
            # 같은 날 내 (예: 09:00 ~ 15:30)
            return self.start_time <= current_time <= self.end_time
        else:
            # 다음 날까지 (예: 23:00 ~ 06:00)
            return current_time >= self.start_time or current_time <= self.end_time
    
    def _time_until_start(self) -> datetime.timedelta:
        """시작 시간까지 남은 시간 계산"""
        now = datetime.datetime.now()
        today_start = datetime.datetime.combine(now.date(), self.start_time)
        
        if now.time() < self.start_time:
            # 오늘의 시작 시간
            return today_start - now
        else:
            # 내일의 시작 시간
            tomorrow_start = today_start + datetime.timedelta(days=1)
            return tomorrow_start - now
    
    def _time_until_end(self) -> datetime.timedelta:
        """종료 시간까지 남은 시간 계산"""
        now = datetime.datetime.now()
        today_end = datetime.datetime.combine(now.date(), self.end_time)
        
        if now.time() < self.end_time:
            # 오늘의 종료 시간
            return today_end - now
        else:
            # 내일의 종료 시간
            tomorrow_end = today_end + datetime.timedelta(days=1)
            return tomorrow_end - now
    
    def _format_timedelta(self, td: datetime.timedelta) -> str:
        """timedelta를 읽기 쉬운 형태로 포맷"""
        total_seconds = int(td.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}시간 {minutes}분"
        elif minutes > 0:
            return f"{minutes}분"
        else:
            return f"{seconds}초"
    
    async def _start_server(self):
        """서버 시작"""
        self.logger.info(f"🚀 서버 시작: {self.host}:{self.port}")
        
        try:
            config = uvicorn.Config(
                app=self.app_module,
                host=self.host,
                port=self.port,
                reload=self.reload,
                log_level="info",
                access_log=True
            )
            self.server = uvicorn.Server(config)
            
            # 서버 실행
            await self.server.serve()
        except Exception as e:
            self.logger.error(f"서버 시작 실패: {e}")
            raise
    
    async def _stop_server(self):
        """서버 중지"""
        if self.server:
            self.logger.info("🛑 서버 중지 중...")
            try:
                self.server.should_exit = True
                # 서버가 정상적으로 종료될 때까지 대기 (최대 5초)
                for _ in range(50):  # 0.1초씩 50번 = 5초
                    if not self.server.started:
                        break
                    await asyncio.sleep(0.1)
                self.logger.info("✅ 서버 중지 완료")
            except Exception as e:
                self.logger.error(f"서버 중지 중 오류: {e}")
    
    async def run_scheduled(self):
        """스케줄에 따라 서버 실행"""
        self.running = True
        self.logger.info(f"📅 스케줄러 시작 - 운영시간: {self.start_time} ~ {self.end_time}")
        
        while self.running:
            try:
                if self._is_within_schedule():
                    self.logger.info("✅ 운영 시간 내 - 서버 시작")
                    
                    # 서버 시작
                    server_task = asyncio.create_task(self._start_server())
                    
                    # 종료 시간까지 대기하면서 주기적으로 체크
                    while self._is_within_schedule() and self.running:
                        await asyncio.sleep(60)  # 1분마다 체크
                    
                    # 운영 시간 종료 - 서버 중지
                    if self.running:
                        self.logger.info("⏰ 운영 시간 종료 - 서버 중지")
                        await self._stop_server()
                        server_task.cancel()
                        
                        try:
                            await server_task
                        except asyncio.CancelledError:
                            self.logger.debug("서버 태스크 취소됨")
                else:
                    # 운영 시간 외 - 시작 시간까지 대기
                    time_until_start = self._time_until_start()
                    formatted_time = self._format_timedelta(time_until_start)
                    self.logger.info(f"⏳ 운영 시간 외 - {formatted_time} 후 서버 시작 예정")
                    
                    # 최대 1시간씩 나누어서 대기 (중간에 종료 가능하도록)
                    wait_seconds = min(time_until_start.total_seconds(), 3600)
                    
                    # 인터럽트 가능한 대기
                    for _ in range(int(wait_seconds)):
                        if not self.running:
                            break
                        await asyncio.sleep(1)
                        
            except Exception as e:
                self.logger.error(f"스케줄러 실행 중 예외 발생: {e}")
                await asyncio.sleep(60)  # 오류 발생 시 1분 후 재시도
    
    def run(self):
        """스케줄러 실행 (동기 버전)"""
        try:
            asyncio.run(self.run_scheduled())
        except KeyboardInterrupt:
            self.logger.info("🔴 사용자에 의해 중단됨")
        except Exception as e:
            self.logger.error(f"스케줄러 실행 중 오류: {e}")
        finally:
            self.logger.info("🏁 스케줄러 종료")


class WeekdayScheduledServerManager(ScheduledServerManager):
    """평일만 운영하는 스케줄러"""
    
    def _is_within_schedule(self) -> bool:
        """평일이면서 운영 시간 내인지 확인"""
        current_weekday = datetime.datetime.now().weekday()  # 0=월요일, 6=일요일
        is_weekday = current_weekday < 5  # 월~금 (0~4)
        
        if not is_weekday:
            # 주말인 경우 다음 평일까지의 시간 계산해서 로그 출력
            if current_weekday == 5:  # 토요일
                self.logger.debug("📅 주말 (토요일) - 월요일까지 대기")
            elif current_weekday == 6:  # 일요일
                self.logger.debug("📅 주말 (일요일) - 월요일까지 대기")
            return False
        
        return super()._is_within_schedule()
    
    def _time_until_start(self) -> datetime.timedelta:
        """다음 평일 운영 시작 시간까지 계산"""
        now = datetime.datetime.now()
        current_weekday = now.weekday()
        
        # 평일인 경우 부모 클래스 로직 사용
        if current_weekday < 5:
            return super()._time_until_start()
        
        # 주말인 경우 다음 월요일까지 계산
        days_until_monday = 7 - current_weekday  # 토요일=1일, 일요일=1일
        next_monday = now + datetime.timedelta(days=days_until_monday)
        next_monday_start = datetime.datetime.combine(
            next_monday.date(), 
            self.start_time
        )
        
        return next_monday_start - now


# 편의 함수들
def create_trading_scheduler(start_time: str = "09:00", 
                           end_time: str = "15:30",
                           weekdays_only: bool = True,
                           host: str = "0.0.0.0",
                           port: int = 8080,
                           reload: bool = None) -> ScheduledServerManager:
    """트레이딩용 스케줄러 생성"""
    if reload is None:
        reload = getattr(settings, 'DEBUG', False)
        
    if weekdays_only:
        return WeekdayScheduledServerManager(
            start_time=start_time,
            end_time=end_time,
            host=host,
            port=port,
            app_module="main:app",
            reload=reload
        )
    else:
        return ScheduledServerManager(
            start_time=start_time,
            end_time=end_time,
            host=host,
            port=port,
            app_module="main:app",
            reload=reload
        )


def create_24h_scheduler(host: str = "0.0.0.0", 
                        port: int = 8080,
                        reload: bool = None) -> ScheduledServerManager:
    """24시간 운영 스케줄러"""
    if reload is None:
        reload = getattr(settings, 'DEBUG', False)
        
    return ScheduledServerManager(
        start_time="00:00",
        end_time="23:59",
        host=host,
        port=port,
        app_module="main:app",
        reload=reload
    )


def create_custom_scheduler(start_time: str,
                          end_time: str,
                          weekdays_only: bool = False,
                          host: str = "0.0.0.0",
                          port: int = 8080) -> ScheduledServerManager:
    """커스텀 스케줄러 생성"""
    return create_trading_scheduler(
        start_time=start_time,
        end_time=end_time,
        weekdays_only=weekdays_only,
        host=host,
        port=port
    )