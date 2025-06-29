# container/redis_container.py
from dependency_injector import containers, providers
from db.redis_db import RedisDB

class Redis_Container(containers.DeclarativeContainer):
    """Redis 의존성 컨테이너"""
    
    # Redis 모듈을 싱글톤으로 제공
    redis_db = providers.Singleton(RedisDB)
    
    # Redis 클라이언트를 제공하는 프로바이더
    redis_client = providers.Callable(
        lambda module: module.get_connection(), 
        module = redis_db
    )
