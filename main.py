import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

import uvicorn

from utils.set_logger import SetLogger

from container.token_container import Token_Container
from container.kiwoom_container import Kiwoom_Container
from container.realtime_container import RealTime_Container
from container.socket_container import Socket_Container
from container.redis_container import Redis_Container
from container.processor_container import Processor_Container
from module.socket_broadcast_module import WebSocketBroadcast
from api.routes import api_router
from config import settings

from utils.scheduler_manager import create_trading_scheduler, ScheduledServerManager

# -----------------------
# 3. DI 컨테이너 초기화
# -----------------------
token_container = Token_Container()
redis_container = Redis_Container()

token_container.wire(modules=["module.kiwoom_module", "module.socket_module"])
redis_container.wire(modules=["module.socket_module"])

kiwoom_container = Kiwoom_Container(token_module=token_container.token_module)
socket_container = Socket_Container(
    redis_db=redis_container.redis_db,
    token_module=token_container.token_module
)

realtime_container = RealTime_Container(socket_module=socket_container.socket_module)
processor_container = Processor_Container(
    redis_db=redis_container.redis_db,
    socket_module=socket_container.socket_module,
    realtime_module=realtime_container.realtime_module
)

kiwoom_container.wire(modules=["api.chart", "module.processor_module"])
socket_container.wire(modules=["api.realtime", "module.realtime_module"])
realtime_container.wire(modules=["api.realtime"])

# -----------------------
# 4. lifespan 정의
# -----------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
  
    logger_setup = SetLogger()
    logger = logger_setup.initialize()
  
    background_tasks = []

    async def safe_run(name: str, coro):
        try:
            logger.info(f"[{name}] started")
            await coro
        except asyncio.CancelledError:
            logger.warning(f"[{name}] cancelled")
            raise
        except Exception as e:
            logger.exception(f"[{name}] crashed: {e}")

    # 모듈 인스턴스 및 초기화
    redis_db = redis_container.redis_db()
    await redis_db.initialize()

    socket_module = socket_container.socket_module()
    kiwoom_module = kiwoom_container.kiwoom_module()
    realtime_module = realtime_container.realtime_module()
    processor_module = processor_container.processor_module()
    bridge_module = WebSocketBroadcast(redis_db)

    await socket_module.initialize()
    await socket_module.connect()
    await kiwoom_module.initialize()
    await realtime_module.initialize()
    await processor_module.initialize()
    await bridge_module.initialize()

    # 백그라운드 태스크 실행
    background_tasks = [
        asyncio.create_task(safe_run("pub_messages", socket_module.pub_messages())),
        asyncio.create_task(safe_run("receive_messages", processor_module.receive_messages())),
        asyncio.create_task(safe_run("start_bridge", bridge_module.start_bridge())),
        asyncio.create_task(safe_run("time_handler", processor_module.time_handler())),
    ]

    logger.info("🚀 백그라운드 태스크 실행 완료")

    try:
        yield  # FastAPI 실행
    finally:
        logger.info("🛑 애플리케이션 종료 시작")

        # 백그라운드 태스크 취소
        for task in background_tasks:
            task.cancel()

        done, pending = await asyncio.wait(background_tasks, timeout=5.0)
        for task in pending:
            logger.warning(f"⏳ 취소되지 않은 작업 존재: {task.get_name()}")

        logger.info("🛑 백그라운드 태스크 취소 완료")

        # 모듈 종료
        for name, shutdown in [
            ("processor_module", processor_module.shutdown),
            ("realtime_module", realtime_module.shutdown),
            ("kiwoom_module", kiwoom_module.shutdown),
            ("socket_module", socket_module.shutdown),
            ("redis_db", redis_db.close),
        ]:
            try:
                await shutdown()
                logger.info(f"🛑 {name} 종료 완료")
            except Exception as e:
                logger.exception(f"{name} 종료 중 오류 발생")

# -----------------------
# 5. FastAPI 앱 생성
# -----------------------
app = FastAPI(
    title=settings.APP_NAME,
    description="키움 API를 활용한 트레이딩 서비스",
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan
)

# 앱에 DI 주입
app.kiwoom = kiwoom_container
app.socket = socket_container
app.realtime = realtime_container

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(api_router, prefix="/api")

# -----------------------
# 6. 상태 확인 라우트
# -----------------------
@app.get("/")
async def root():
    """API 상태 확인"""
    try:
        redis_ok = await redis_container.redis_db().ping()
    except:
        redis_ok = False

    return {
        "status": "online",
        "connected_to_kiwoom": True,  # TODO: 실제 상태 반영
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database_connected": redis_ok
    }

# -----------------------
# 7. 실행 (로컬 전용)
# -----------------------
if __name__ == "__main__":
    scheduler     = create_trading_scheduler(
    start_time    = "08:30",
    end_time      = "16:00",
    weekdays_only = True )
    scheduler.run()

    # uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=settings.DEBUG)
