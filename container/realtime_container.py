from dependency_injector import containers, providers
from module.realtime_module import RealtimeModule

class RealTime_Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    socket_module = providers.Dependency()

    realtime_module = providers.Singleton(
      RealtimeModule,
      socket_module = socket_module
      )