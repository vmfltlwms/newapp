import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager


# 🔇 가장 먼저 SQLAlchemy 로깅 완전 비활성화
logging.getLogger("sqlalchemy").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy.pool").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy.dialects").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy.orm").setLevel(logging.ERROR)

# 로거 전파 방지
for logger_name in ["sqlalchemy", "sqlalchemy.engine", "sqlalchemy.pool"]:
    logger = logging.getLogger(logger_name)
    logger.propagate = False

# 기본 로깅 설정 (SQLAlchemy 제외)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from container.token_container import Token_Container
from container.kiwoom_container import Kiwoom_Container
from container.realtime_container import RealTime_Container
from container.socket_container import Socket_Container
from container.redis_container import Redis_Container
from container.postgres_container import Postgres_Container
from container.processor_container import Processor_Container 
from container.baseline_container import Baseline_Container
from container.step_manager_container import Step_Manager_Container
from container.realtime_group_container import RealtimeGroup_container
from module.socket_broadcast_module import WebSocketBroadcast
from api.routes import api_router
from config import settings
from utils.log_hander import configure_logging


# 커스텀 로깅 설정 (SQLAlchemy 제외하고 적용)
configure_logging() 

# 다시 한번 SQLAlchemy 로깅 억제 (configure_logging 이후)
logging.getLogger("sqlalchemy").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)


token_container = Token_Container()
redis_container = Redis_Container()
postgres_container = Postgres_Container()

token_container.wire(modules=["module.kiwoom_module","module.socket_module"])  
redis_container.wire(modules=["module.socket_module"])   
postgres_container.wire(modules=["db.redis_to_postgres"])

kiwoom_container = Kiwoom_Container(token_module =token_container.token_module)
socket_container = Socket_Container(redis_db  = redis_container.redis_db,
                                    token_module =token_container.token_module)

realtime_group_container = RealtimeGroup_container(postgres_db = postgres_container.postgres_db)
realtime_container = RealTime_Container(socket_module = socket_container.socket_module)
baseline_container = Baseline_Container(postgres_db = postgres_container.postgres_db)
step_manager_container = Step_Manager_Container(postgres_db = postgres_container.postgres_db)
processor_container = Processor_Container( redis_db=redis_container.redis_db,
                                          postgres_db = postgres_container.postgres_db,
                                          socket_module = socket_container.socket_module,
                                          realtime_module = realtime_container.realtime_module,
                                          baseline_module = baseline_container.baseline_module,
                                          step_manager_module = step_manager_container.step_manager_module,
                                          realtime_group_module =realtime_group_container.realtime_group_module )

kiwoom_container.wire(modules=["api.chart","module.processor_module"])
socket_container.wire(modules=["api.realtime","module.realtime_module"])
realtime_container.wire(modules=["api.realtime"])
baseline_container.wire(modules=["api.baseline","module.processor_module"])
step_manager_container.wire(modules=["api.baseline","module.processor_module"])
realtime_group_container.wire(modules=["api.realtime_group","module.processor_module" ])

background_tasks = []

@asynccontextmanager
async def lifespan(app: FastAPI,):
    global background_tasks

    # DB 모듈 인스턴스 생성
    redis_db = redis_container.redis_db()
    postgres_db = postgres_container.postgres_db()
    # token_module = token_container.token_module()
    
    # 먼저 DB 초기화
    await redis_db.initialize()
    await postgres_db.initialize()
    

    # 초기화된 DB에 의존하는 모듈 생성
    socket_module = socket_container.socket_module()
    kiwoom_module = kiwoom_container.kiwoom_module()
    realtime_module = realtime_container.realtime_module()
    processor_module = processor_container.processor_module()
    baseline_module = baseline_container.baseline_module()
    step_manager_module = step_manager_container.step_manager_module()
    realtime_group_module = realtime_group_container.realtime_group_module()
    bridge_module = WebSocketBroadcast(redis_db)
    
    # 나머지 모듈 초기화
    await socket_module.initialize()
    await socket_module.connect()
    await kiwoom_module.initialize()
    await realtime_module.initialize()
    await processor_module.initialize() 
    # await baseline_module.initialize()
    await step_manager_module.initialize()
    await realtime_group_module.initialize()
    await bridge_module.initialize()
    

    # 메시지 수신 루프를 백그라운드에서 실행
    processor_task1 = asyncio.create_task(socket_module.pub_messages())
    processor_task2 = asyncio.create_task(processor_module.receive_messages())
    bridge_task = asyncio.create_task(bridge_module.start_bridge())
    background_tasks.append(processor_task1)
    background_tasks.append(processor_task2)
    background_tasks.append(bridge_task)

    # 조건검색 요청
    await realtime_module.get_condition_list()
    await processor_module.short_trading_handler()

  
    yield # 실행 종료 구분
    
    # 모듈 정리는 초기화의 역순으로 진행
    logging.info("🛑 애플리케이션 종료 시작")
    
    # 1. 백그라운드 태스크 취소
    for task in background_tasks:
        task.cancel()
    
    try:
        # 짧은 타임아웃으로 작업 취소 대기
        await asyncio.wait(background_tasks, timeout=5.0)
        logging.info("🛑 백그라운드 태스크 취소 완료")
    except asyncio.CancelledError:
        logging.info("🛑 백그라운드 태스크가 취소되었습니다")
    
    # 2. 모듈 종료 (초기화의 역순)
    await baseline_module.shutdown()
    logging.info("🛑 baseline_module 종료 완료")

    await processor_module.shutdown()
    logging.info("🛑 processor_module 종료 완료")
    
    await realtime_module.shutdown()
    logging.info("🛑 realtime_module 종료 완료")
    
    await kiwoom_module.shutdown()
    logging.info("🛑 kiwoom_module 종료 완료")
    
    await socket_module.shutdown()
    logging.info("🛑 socket_module 종료 완료")
    
    # 3. DB 연결 종료
    await postgres_db.close_db()
    logging.info("🛑 postgres 연결 종료 완료")
    
    await redis_db.close()
    logging.info("🛑 Redis 연결 종료 완료")
    
# FastAPI 앱 인스턴스 생성 (lifespan 적용)
app = FastAPI(
    title=settings.APP_NAME,
    description="키움 API를 활용한 트레이딩 서비스",
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan
)

# FastAPI 연결
app.kiwoom = kiwoom_container 
app.socket = socket_container   
app.realtime = realtime_container   
app.baseline = baseline_container
app.realtime_group = realtime_group_container
app.step_manager = step_manager_container  # ✅ 이 줄 추가!

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(api_router, prefix="/api")

# 상태 확인 엔드포인트
@app.get("/")
async def root():
    """API 상태 확인"""
    return {
        "status": "online",
        "connected_to_kiwoom": True,
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database_connected": True
    }

# 서버 실행 코드
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=settings.DEBUG)
