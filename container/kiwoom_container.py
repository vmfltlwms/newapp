from dependency_injector import containers, providers

from module.kiwoom_module import KiwoomModule

class Kiwoom_Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    token_module = providers.Dependency() 

    kiwoom_module = providers.Singleton(
      KiwoomModule,
      token_module = token_module
      )