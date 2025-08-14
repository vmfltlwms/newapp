import asyncio
import datetime
import logging
import signal
from typing import Optional
from zoneinfo import ZoneInfo
import uvicorn

# 전역 타임존 상수
KST = ZoneInfo("Asia/Seoul")

try:
    from config import settings
except ImportError:
    class DefaultSettings:
        DEBUG = False
    settings = DefaultSettings()


class ScheduledServerManager:
    """시간 기반 서버 자동 시작/종료 (KST 기준)"""

    def __init__( self,
                  start_time: str = "09:00",
                  end_time: str = "15:30",
                  host: str = "0.0.0.0",
                  port: int = 8080,
                  app_module: str = "main:app",
                  reload: bool = False):
        self.start_time = self._parse_time(start_time)
        self.end_time = self._parse_time(end_time)
        self.host = host
        self.port = port
        self.app_module = app_module
        self.reload = reload
        self.server: Optional[uvicorn.Server] = None
        self.running = False
        self.logger = logging.getLogger(self.__class__.__name__)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _now(self) -> datetime.datetime:
        """KST 기준 현재 시간"""
        return datetime.datetime.now(KST)

    def _parse_time(self, time_str: str) -> datetime.time:
        """시간 문자열을 time 객체로 변환"""
        hour, minute = map(int, time_str.split(':'))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"잘못된 시간 범위: {time_str}")
        return datetime.time(hour, minute)

    def _signal_handler(self, signum, frame):
        self.logger.info(f"종료 시그널 수신: {signum}")
        self.running = False

    def _get_current_time(self) -> datetime.time:
        return self._now().time()

    def _is_within_schedule(self) -> bool:
        current_time = self._get_current_time()
        if self.start_time <= self.end_time:
            return self.start_time <= current_time <= self.end_time
        else:
            return current_time >= self.start_time or current_time <= self.end_time

    def _time_until_start(self) -> datetime.timedelta:
        now = self._now()
        today_start = datetime.datetime.combine(now.date(), self.start_time, tzinfo=KST)
        if now.time() < self.start_time:
            return today_start - now
        else:
            return today_start + datetime.timedelta(days=1) - now

    def _time_until_end(self) -> datetime.timedelta:
        now = self._now()
        today_end = datetime.datetime.combine(now.date(), self.end_time, tzinfo=KST)
        if now.time() < self.end_time:
            return today_end - now
        else:
            return today_end + datetime.timedelta(days=1) - now

    def _format_timedelta(self, td: datetime.timedelta) -> str:
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
        self.logger.info(f"🚀 서버 시작: {self.host}:{self.port} (KST)")
        config = uvicorn.Config(
            app=self.app_module,
            host=self.host,
            port=self.port,
            reload=self.reload,
            log_level="info",
            access_log=True
        )
        self.server = uvicorn.Server(config)
        await self.server.serve()

    async def _stop_server(self):
        if self.server:
            self.logger.info("🛑 서버 중지 중...")
            self.server.should_exit = True
            for _ in range(50):
                if not self.server.started:
                    break
                await asyncio.sleep(0.1)
            self.logger.info("✅ 서버 중지 완료")

    async def run_scheduled(self):
        self.running = True
        self.logger.info(f"📅 스케줄러 시작 (KST) - 운영시간: {self.start_time} ~ {self.end_time}")
        while self.running:
            try:
                if self._is_within_schedule():
                    self.logger.info("✅ 운영 시간 내 - 서버 시작")
                    server_task = asyncio.create_task(self._start_server())
                    while self._is_within_schedule() and self.running:
                        await asyncio.sleep(60)
                    if self.running:
                        self.logger.info("⏰ 운영 시간 종료 - 서버 중지")
                        await self._stop_server()
                        server_task.cancel()
                        try:
                            await server_task
                        except asyncio.CancelledError:
                            self.logger.debug("서버 태스크 취소됨")
                else:
                    wait_td = self._time_until_start()
                    self.logger.info(f"⏳ 운영 시간 외 - {self._format_timedelta(wait_td)} 후 서버 시작 예정")
                    wait_seconds = min(wait_td.total_seconds(), 3600)
                    for _ in range(int(wait_seconds)):
                        if not self.running:
                            break
                        await asyncio.sleep(1)
            except Exception as e:
                self.logger.error(f"스케줄러 실행 중 예외 발생: {e}")
                await asyncio.sleep(60)

    def run(self):
        try:
            asyncio.run(self.run_scheduled())
        except KeyboardInterrupt:
            self.logger.info("🔴 사용자에 의해 중단됨")
        finally:
            self.logger.info("🏁 스케줄러 종료")


class WeekdayScheduledServerManager(ScheduledServerManager):
    """평일만 운영하는 스케줄러 (KST 기준)"""
    def _is_within_schedule(self) -> bool:
        current_weekday = self._now().weekday()
        if current_weekday >= 5:
            return False
        return super()._is_within_schedule()

    def _time_until_start(self) -> datetime.timedelta:
        now = self._now()
        if now.weekday() < 5:
            return super()._time_until_start()
        days_until_monday = 7 - now.weekday()
        next_monday = now + datetime.timedelta(days=days_until_monday)
        return datetime.datetime.combine(next_monday.date(), self.start_time, tzinfo=KST) - now


# 생성 함수
def create_trading_scheduler( start_time="09:00", end_time="15:30", weekdays_only=True,
                              host="0.0.0.0", port=8080, reload=None) -> ScheduledServerManager:
    if reload is None:
        reload = getattr(settings, 'DEBUG', False)
    if weekdays_only:
        return WeekdayScheduledServerManager(start_time, end_time, host, port, "main:app", reload)
    return ScheduledServerManager(start_time, end_time, host, port, "main:app", reload)


def create_24h_scheduler(host="0.0.0.0", port=8080, reload=None) -> ScheduledServerManager:
    if reload is None:
        reload = getattr(settings, 'DEBUG', False)
    return ScheduledServerManager("00:00", "23:59", host, port, "main:app", reload)
