from dependency_injector import containers, providers
from module.realtimegroup_module import RealtimeGroupModule

class RealtimeGroup_container(containers.DeclarativeContainer):
  config = providers.Configuration()
  postgres_db = providers.Dependency() 

  realtime_group_module = providers.Singleton(
    RealtimeGroupModule,
    postgres_db = postgres_db
    )