import datetime
import logging
import os
from typing import Optional


class SetLogger:
    """로깅 시스템 초기화 및 관리 클래스"""
    
    def __init__( self, 
                  log_dir: str = "logs",
                  file_prefix: str = "new_trading",
                  file_level: int = logging.INFO,
                  console_level: int = logging.DEBUG,
                  logger_level: int = logging.DEBUG):
        """
        Args:
            log_dir: 로그 파일이 저장될 디렉토리
            file_prefix: 로그 파일명 접두사
            file_level: 파일 핸들러 로그 레벨
            console_level: 콘솔 핸들러 로그 레벨
            logger_level: 전체 로거 레벨
        """
        self.log_dir = log_dir
        self.file_prefix = file_prefix
        self.file_level = file_level
        self.console_level = console_level
        self.logger_level = logger_level
        self.log_path: Optional[str] = None
        self.logger: Optional[logging.Logger] = None
        
    def initialize(self) -> logging.Logger:
        """로거 초기화"""
        # 로그 파일 경로 생성
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_path = os.path.join(self.log_dir, f"{self.file_prefix}_{timestamp}.log")
        
        # 로그 디렉토리 생성
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 기존 핸들러 제거
        self._remove_existing_handlers()
        
        # 로거 설정
        self.logger = logging.getLogger()
        self.logger.setLevel(self.logger_level)
        
        # 핸들러 추가
        self._add_file_handler()
        self._add_console_handler()
        
        # 초기화 완료 메시지
        self.logger.info("🚀 FastAPI 프로젝트 로깅 초기화 완료")
        self.logger.info(f"📄 로그 파일 경로: {self.log_path}")
        
        return self.logger
    
    def _remove_existing_handlers(self):
        """기존 핸들러 제거"""
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
    
    def _add_file_handler(self):
        """파일 핸들러 추가"""
        file_handler = logging.FileHandler(self.log_path, encoding='utf-8')
        file_handler.setLevel(self.file_level)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        ))
        self.logger.addHandler(file_handler)
    
    def _add_console_handler(self):
        """콘솔 핸들러 추가"""
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.console_level)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        ))
        self.logger.addHandler(console_handler)
    
    def get_logger(self) -> logging.Logger:
        """현재 로거 반환"""
        if self.logger is None:
            raise RuntimeError("로거가 초기화되지 않았습니다. initialize()를 먼저 호출하세요.")
        return self.logger
    
    def get_log_path(self) -> str:
        """로그 파일 경로 반환"""
        if self.log_path is None:
            raise RuntimeError("로거가 초기화되지 않았습니다. initialize()를 먼저 호출하세요.")
        return self.log_path
    
    @classmethod
    def create_default_logger(cls) -> logging.Logger:
        """기본 설정으로 로거 생성 (편의 메서드)"""
        logger_setup = cls()
        return logger_setup.initialize()
    
    @classmethod
    def create_custom_logger(cls, 
                           log_dir: str = "logs",
                           file_prefix: str = "app",
                           file_level: int = logging.INFO,
                           console_level: int = logging.DEBUG) -> logging.Logger:
        """커스텀 설정으로 로거 생성 (편의 메서드)"""
        logger_setup = cls(
            log_dir=log_dir,
            file_prefix=file_prefix,
            file_level=file_level,
            console_level=console_level
        )
        return logger_setup.initialize()