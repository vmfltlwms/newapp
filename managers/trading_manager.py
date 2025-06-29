import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
from db.postgres_db import PostgresDB
from dependency_injector.wiring import inject, Provide
from container.postgres_container import Postgres_Container

logger = logging.getLogger(__name__)

class TradingManager:
    """주식 매매 조건을 관리하는 싱글톤 클래스"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @inject
    def __init__(self, postgres_db:PostgresDB = Provide[Postgres_Container.postgres_db]):
        if not hasattr(self, 'initialized'):
            self.order_dic: Dict = {}
            self.order_file: str = "stock_orders.json"
            self.logger = logging.getLogger(__name__)
            self.postgres_db = postgres_db
            self.initialized = False
    
    async def initialize(self, filename: str = "stock_orders.json") -> None:
        pass
    
      
    async def add_baseline(self) : pass
    async def delete_baseline(self) : pass
    async def update_baseline(self) : pass

# 싱글톤 인스턴스 생성
trading_manager = TradingManager()

