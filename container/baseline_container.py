from dependency_injector import containers, providers
from module.baseline_module import BaselineModule

class Baseline_Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    postgres_db = providers.Dependency() 

    baseline_module = providers.Singleton(
      BaselineModule,
      postgres_db = postgres_db
      )
  
