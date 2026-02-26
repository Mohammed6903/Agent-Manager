from typing import Annotated
from fastapi import Depends
from .repositories.storage import StorageRepository
from .repositories.filesystem_storage import FileSystemStorage
from .clients.gateway_client import GatewayClient
from .clients.cli_gateway_client import CLIGatewayClient
from .services.agent_service import AgentService
from .services.session_service import SessionService
from .services.chat_service import ChatService

# Singletons for storage and gateway client (can be swapped based on config)
_storage = FileSystemStorage()
_gateway = CLIGatewayClient()
_chat = ChatService()

def get_storage() -> StorageRepository:
    return _storage

def get_gateway() -> GatewayClient:
    return _gateway

def get_agent_service(
    storage: Annotated[StorageRepository, Depends(get_storage)],
    gateway: Annotated[GatewayClient, Depends(get_gateway)]
) -> AgentService:
    return AgentService(storage, gateway)

def get_session_service(
    storage: Annotated[StorageRepository, Depends(get_storage)]
) -> SessionService:
    return SessionService(storage)

def get_chat_service() -> ChatService:
    return _chat
