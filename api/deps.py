# -*- coding: utf-8 -*-
"""
===================================
API 의존성 주입 모듈
===================================

역할:
1. DB Session 의존성 제공
2. 설정 의존성 제공
3. 서비스 계층 의존성 제공
"""

from typing import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from src.storage import DatabaseManager
from src.config import get_config, Config
from src.services.system_config_service import SystemConfigService
from src.services.runtime_scheduler import RuntimeSchedulerService
from src.services.agent_chat_session_service import AgentChatSessionService


def get_db() -> Generator[Session, None, None]:
    """
    DB Session 의존성 가져오기
    
    FastAPI 의존성 주입을 써서 요청이 끝나면 Session 을 자동으로 닫음
    
    Yields:
        Session: SQLAlchemy Session 객체
        
    Example:
        @router.get("/items")
        async def get_items(db: Session = Depends(get_db)):
            ...
    """
    db_manager = DatabaseManager.get_instance()
    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()


def get_config_dep() -> Config:
    """
    설정 의존성 가져오기
    
    Returns:
        Config: 설정 싱글턴 객체
    """
    return get_config()


def get_database_manager() -> DatabaseManager:
    """
    DB 관리자 의존성 가져오기
    
    Returns:
        DatabaseManager: DB 관리자 싱글턴 객체
    """
    return DatabaseManager.get_instance()


def get_agent_chat_session_service() -> AgentChatSessionService:
    """Build an Agent Chat session service for the current database manager."""
    return AgentChatSessionService(DatabaseManager.get_instance())


def get_system_config_service(request: Request) -> SystemConfigService:
    """Get app-lifecycle shared SystemConfigService instance."""
    service = getattr(request.app.state, "system_config_service", None)
    if service is None:
        service = SystemConfigService()
        request.app.state.system_config_service = service
    return service


def get_runtime_scheduler_service(request: Request) -> RuntimeSchedulerService:
    """Get app-lifecycle shared RuntimeSchedulerService instance."""
    service = getattr(request.app.state, "runtime_scheduler_service", None)
    if service is None:
        service = RuntimeSchedulerService()
        request.app.state.runtime_scheduler_service = service
    return service
