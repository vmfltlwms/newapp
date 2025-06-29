from dependency_injector import containers, providers
from module.step_manager_module import StepManagerModule

class Step_Manager_Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    postgres_db = providers.Dependency() 

    step_manager_module = providers.Singleton(
      StepManagerModule,
      postgres_db = postgres_db
      )
  
