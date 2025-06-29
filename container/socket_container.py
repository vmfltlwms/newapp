from dependency_injector import containers, providers
 
from module.socket_module import SocketModule


class Socket_Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    redis_db = providers.Dependency()
    token_module = providers.Dependency() 
    
    socket_module = providers.Singleton(
        SocketModule,
        redis_db  =  redis_db,
        token_module = token_module
        )