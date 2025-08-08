# container/processor_container.py
from dependency_injector import containers, providers
from module.processor_module import ProcessorModule

class Processor_Container(containers.DeclarativeContainer):
    # Redis 컨테이너에 대한 의존성
    redis_db = providers.Dependency()
    socket_module = providers.Dependency()
    realtime_module = providers.Dependency()
    
    # ProcessorModule 제공
    processor_module = providers.Singleton(
        ProcessorModule,
        redis_db = redis_db,
        socket_module = socket_module,
        realtime_module =realtime_module,
    )