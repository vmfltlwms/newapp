# container/postgres_container.py
from dependency_injector import containers, providers
from db.postgres_db import PostgresDB

class Postgres_Container(containers.DeclarativeContainer):
    """Redis 의존성 컨테이너"""
    
    # Redis 모듈을 싱글톤으로 제공
    postgres_db = providers.Singleton(PostgresDB)
    
    # Redis 클라이언트를 제공하는 프로바이더
    postgres_client = providers.Callable(
        lambda module: module.get_connection(), 
        module=postgres_db
    )
