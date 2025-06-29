# utils/log_handler.py

import logging
import sys

def configure_logging():
    """로깅 설정 - SQLAlchemy 로그 완전 억제"""
    
    # 🔇 SQLAlchemy 로깅 완전 비활성화 (최우선)
    sqlalchemy_loggers = [
        'sqlalchemy',
        'sqlalchemy.engine', 
        'sqlalchemy.engine.Engine',
        'sqlalchemy.pool',
        'sqlalchemy.pool.impl',
        'sqlalchemy.dialects',
        'sqlalchemy.orm',
        'sqlalchemy.orm.mapper',
        'sqlalchemy.orm.strategies'
    ]
    
    for logger_name in sqlalchemy_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.ERROR)  # ERROR 레벨로 설정
        logger.propagate = False  # 상위 로거로 전파 방지
        logger.disabled = True  # 로거 완전 비활성화
    
    # 기본 애플리케이션 로깅은 유지
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 특정 모듈 로그 레벨 조정
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    
    print("✅ 로깅 설정 완료 - SQLAlchemy 로그 완전 비활성화")