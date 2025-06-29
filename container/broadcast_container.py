# container/broadcast_container.py
from dependency_injector import containers, providers
from module.broadcast_module import BroadcastModule

class Broadcast_Container(containers.DeclarativeContainer):
    """Redis 의존성 컨테이너"""
    
    # Redis 모듈을 싱글톤으로 제공
    redis_db = providers.Dependency()
    
    # Redis 클라이언트를 제공하는 프로바이더
    broadcast_module = providers.Singleton(
        BroadcastModule,
        redis_db = redis_db
    )
    