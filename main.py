import asyncio
import datetime
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# -----------------------
# 1. 로그 초기화
# -----------------------
log_path = f"logs/new_trading_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
os.makedirs(os.path.dirname(log_path), exist_ok=True)

# 기존 핸들러 제거 후 다시 설정
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(log_path, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

logger.info("🚀 FastAPI 프로젝트 로깅 초기화 완료")
logger.info(f"📄 로그 파일 경로: {log_path}")

# -----------------------
# 2. 모듈 import 및 DI
# -----------------------
from container.token_container import Token_Container
from container.kiwoom_container import Kiwoom_Container
from container.realtime_container import RealTime_Container
from container.socket_container import Socket_Container
from container.redis_container import Redis_Container
from container.processor_container import Processor_Container
from module.socket_broadcast_module import WebSocketBroadcast
from api.routes import api_router
from config import settings
from utils.log_hander import configure_logging

configure_logging()

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
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=settings.DEBUG)


# import asyncio
# import datetime
# import logging
# import os
# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from contextlib import asynccontextmanager


# # ==============================
# # 2️⃣ 로그 파일 생성
# # ==============================
# log_path = f"logs/new_trading_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
# os.makedirs(os.path.dirname(log_path), exist_ok=True)

# # ==============================
# # 3️⃣ 루트 로거 설정 (기존 핸들러 제거)
# # ==============================
# for handler in logging.root.handlers[:]:
#     logging.root.removeHandler(handler)

# logger = logging.getLogger()      # root logger 사용
# logger.setLevel(logging.INFO)     # INFO 이상 로그 기록

# # # 📌 파일 핸들러
# file_handler = logging.FileHandler(log_path, encoding='utf-8')
# file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
# logger.addHandler(file_handler)

# # # 📌 콘솔 핸들러
# console_handler = logging.StreamHandler()
# console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
# logger.addHandler(console_handler)

# # ==============================
# # 4️⃣ SQLAlchemy engine WARNING 수준만 허용
# # ==============================

# # ==============================
# # 5️⃣ 프로젝트 모듈 Import
# # ==============================
# from container.token_container import Token_Container
# from container.kiwoom_container import Kiwoom_Container
# from container.realtime_container import RealTime_Container
# from container.socket_container import Socket_Container
# from container.redis_container import Redis_Container
# from container.processor_container import Processor_Container 
# from module.socket_broadcast_module import WebSocketBroadcast
# from api.routes import api_router
# from config import settings
# from utils.log_hander import configure_logging

# # ==============================
# # 6️⃣ 커스텀 로깅 적용 (configure_logging)
# # ==============================
# configure_logging()

# # configure_logging()에서 핸들러를 추가했을 수 있으므로


# logger.info("🚀 FastAPI 프로젝트 로깅 초기화 완료")
# logger.info(f"📄 로그 파일 경로: {log_path}")


# token_container = Token_Container()
# redis_container = Redis_Container()

# token_container.wire(modules=["module.kiwoom_module","module.socket_module"])  
# redis_container.wire(modules=["module.socket_module"])   

# kiwoom_container = Kiwoom_Container(token_module =token_container.token_module)
# socket_container = Socket_Container(redis_db  = redis_container.redis_db,
#                                     token_module =token_container.token_module)

# realtime_container = RealTime_Container(socket_module = socket_container.socket_module)
# processor_container = Processor_Container( redis_db=redis_container.redis_db,
#                                           socket_module = socket_container.socket_module,
#                                           realtime_module = realtime_container.realtime_module)

# kiwoom_container.wire(modules=["api.chart","module.processor_module"])
# socket_container.wire(modules=["api.realtime","module.realtime_module"])
# realtime_container.wire(modules=["api.realtime"])

# background_tasks = []

# @asynccontextmanager
# async def lifespan(app: FastAPI,):
#     global background_tasks

#     # DB 모듈 인스턴스 생성
#     redis_db = redis_container.redis_db()
#     # token_module = token_container.token_module()
    
#     # 먼저 DB 초기화
#     await redis_db.initialize()
    

#     # 초기화된 DB에 의존하는 모듈 생성
#     socket_module = socket_container.socket_module()
#     kiwoom_module = kiwoom_container.kiwoom_module()
#     realtime_module = realtime_container.realtime_module()
#     processor_module = processor_container.processor_module()
#     bridge_module = WebSocketBroadcast(redis_db)
    
    
#     await socket_module.initialize()
#     await socket_module.connect()
#     await kiwoom_module.initialize()
#     await realtime_module.initialize()
#     await processor_module.initialize() 
#     await bridge_module.initialize()
    

#     # 메시지 수신 루프를 백그라운드에서 실행
#     processor_task1 = asyncio.create_task(socket_module.pub_messages())
#     processor_task2 = asyncio.create_task(processor_module.receive_messages())
#     bridge_task     = asyncio.create_task(bridge_module.start_bridge())
#     time_task       = asyncio.create_task(processor_module.time_handler())
    
#     background_tasks.append(processor_task1)
#     background_tasks.append(processor_task2)
#     background_tasks.append(bridge_task)
#     background_tasks.append(time_task)

#     # 조건검색 요청
#     # await realtime_module.get_condition_list()
#     # await processor_module.short_trading_handler()


  
#     yield # 실행 종료 구분
    
#     # 모듈 정리는 초기화의 역순으로 진행
#     logging.info("🛑 애플리케이션 종료 시작")
    
#     # 1. 백그라운드 태스크 취소
#     for task in background_tasks:
#         task.cancel()
    
#     try:
#         # 짧은 타임아웃으로 작업 취소 대기
#         await asyncio.wait(background_tasks, timeout=5.0)
#         logging.info("🛑 백그라운드 태스크 취소 완료")
#     except asyncio.CancelledError:
#         logging.info("🛑 백그라운드 태스크가 취소되었습니다")
    
#     # 2. 모듈 종료 (초기화의 역순)

#     await processor_module.shutdown()
#     logging.info("🛑 processor_module 종료 완료")
    
#     await realtime_module.shutdown()
#     logging.info("🛑 realtime_module 종료 완료")
    
#     await kiwoom_module.shutdown()
#     logging.info("🛑 kiwoom_module 종료 완료")
    
#     await socket_module.shutdown()
#     logging.info("🛑 socket_module 종료 완료")
    
    
#     await redis_db.close()
#     logging.info("🛑 Redis 연결 종료 완료")
    
# # FastAPI 앱 인스턴스 생성 (lifespan 적용)
# app = FastAPI(
#     title=settings.APP_NAME,
#     description="키움 API를 활용한 트레이딩 서비스",
#     version=settings.APP_VERSION,
#     debug=settings.DEBUG,
#     lifespan=lifespan
# )

# # FastAPI 연결
# app.kiwoom = kiwoom_container 
# app.socket = socket_container   
# app.realtime = realtime_container   

# # CORS 미들웨어 설정
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # API 라우터 등록
# app.include_router(api_router, prefix="/api")

# # 상태 확인 엔드포인트
# @app.get("/")
# async def root():
#     """API 상태 확인"""
#     return {
#         "status": "online",
#         "connected_to_kiwoom": True,
#         "app_name": settings.APP_NAME,
#         "version": settings.APP_VERSION,
#         "database_connected": True
#     }

# # 서버 실행 코드
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=settings.DEBUG)
