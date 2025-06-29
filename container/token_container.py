from dependency_injector import containers, providers

from module.token_module import TokenModule

class Token_Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    token_module = providers.Singleton(TokenModule)
