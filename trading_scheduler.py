#!/usr/bin/env python3
# trading_scheduler_simple.py

import datetime
import requests
import subprocess
import logging
import sys
import os
from pathlib import Path

class TradingScheduler:
    def __init__(self):
        # 현재 디렉토리 기준으로 설정
        current_dir = Path(__file__).parent
        
        # 프로그램 설정 (필요에 따라 수정)
        self.program_path = str(current_dir / "main.py")
        self.program_name = "main.py"
        
        # 로그 설정
        self.log_dir = current_dir / "logs"
        self.log_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / "trading_schedule.log"
        
        self.setup_logging()
        
        # 2025년 한국 공휴일
        self.holidays_2025 = {
            datetime.date(2025, 1, 1): "신정",
            datetime.date(2025, 1, 28): "설날연휴",
            datetime.date(2025, 1, 29): "설날",
            datetime.date(2025, 1, 30): "설날연휴",
            datetime.date(2025, 3, 1): "삼일절",
            datetime.date(2025, 5, 5): "어린이날",
            datetime.date(2025, 5, 6): "대체공휴일",
            datetime.date(2025, 6, 3): "현충일",
            datetime.date(2025, 8, 15): "광복절",
            datetime.date(2025, 9, 16): "추석연휴",
            datetime.date(2025, 9, 17): "추석",
            datetime.date(2025, 9, 18): "추석연휴",
            datetime.date(2025, 10, 3): "개천절",
            datetime.date(2025, 10, 9): "한글날",
            datetime.date(2025, 12, 25): "크리스마스"
        }
        
        # 시작 시 설정 정보 출력
        self.print_config()
    
    def print_config(self):
        print(f"Trading Scheduler Configuration:")
        print(f"  Program Path: {self.program_path}")
        print(f"  Program Name: {self.program_name}")
        print(f"  Log File: {self.log_file}")
        print(f"  Program Exists: {Path(self.program_path).exists()}")
        print()
    
    def setup_logging(self):
        """로깅 설정"""
        logging.basicConfig(
            filename=self.log_file,
            level=logging.INFO,
            format='%(asctime)s - %(message)s',
            filemode='a'
        )
        
        logging.info(f"Trading scheduler initialized. Program: {self.program_path}")
    
    def is_trading_day(self, date=None):
        if date is None:
            date = datetime.date.today()
        
        # 주말 체크
        if date.weekday() >= 5:  # 토요일(5), 일요일(6)
            logging.info(f"Weekend - Not a trading day: {date}")
            return False
        
        # 공휴일 체크
        if date in self.holidays_2025:
            holiday_name = self.holidays_2025[date]
            logging.info(f"Holiday ({holiday_name}) - Not a trading day: {date}")
            return False
        
        # API를 통한 임시휴장 확인 (선택사항)
        if self.check_temporary_closure(date):
            logging.info(f"Temporary closure - Not a trading day: {date}")
            return False
        
        logging.info(f"Trading day confirmed: {date}")
        return True
    
    def check_temporary_closure(self, date):
        """KRX API 또는 증권사 API를 통해 임시휴장 확인"""
        try:
            # 실제 구현시에는 적절한 API 엔드포인트 사용
            # response = requests.get(f"https://api.krx.co.kr/trading-calendar/{date}")
            # return not response.json().get('is_trading_day', True)
            return False
        except Exception as e:
            logging.warning(f"Failed to check temporary closure: {e}")
            return False
    
    def is_program_running(self):
        try:
            result = subprocess.run(['pgrep', '-f', self.program_name], 
                                  capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logging.error(f"Failed to check if program is running: {e}")
            return False
    
    def start_program(self):
        if not self.is_trading_day():
            logging.info("Not starting program - Not a trading day")
            print("Today is not a trading day. Program not started.")
            return False
        
        # 프로그램 파일 존재 여부 확인
        if not Path(self.program_path).exists():
            error_msg = f"Program file not found: {self.program_path}"
            logging.error(error_msg)
            print(error_msg)
            return False
        
        if not self.is_program_running():
            try:
                # Python 스크립트인 경우
                if self.program_path.endswith('.py'):
                    cmd = ['python3', self.program_path]
                else:
                    cmd = [self.program_path]
                
                subprocess.Popen(cmd, 
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL,
                               cwd=Path(self.program_path).parent)
                
                logging.info(f"Trading program started: {self.program_path}")
                print(f"Trading program started successfully: {self.program_path}")
                return True
            except Exception as e:
                logging.error(f"Failed to start program: {e}")
                print(f"Failed to start program: {e}")
                return False
        else:
            logging.info("Program already running")
            print("Program is already running")
            return True
    
    def stop_program(self):
        if self.is_program_running():
            try:
                subprocess.run(['pkill', '-f', self.program_name])
                logging.info(f"Trading program stopped: {self.program_name}")
                print(f"Trading program stopped successfully: {self.program_name}")
                return True
            except Exception as e:
                logging.error(f"Failed to stop program: {e}")
                print(f"Failed to stop program: {e}")
                return False
        else:
            logging.info("Program not running")
            print("Program is not running")
            return True
    
    def status(self):
        """현재 상태 출력"""
        today = datetime.date.today()
        is_trading = self.is_trading_day()
        is_running = self.is_program_running()
        
        print(f"Date: {today} ({today.strftime('%A')})")
        print(f"Trading Day: {'Yes' if is_trading else 'No'}")
        print(f"Program Running: {'Yes' if is_running else 'No'}")
        
        if today in self.holidays_2025:
            print(f"Holiday: {self.holidays_2025[today]}")

if __name__ == "__main__":
    scheduler = TradingScheduler()
    
    if len(sys.argv) != 2:
        print("Usage: python3 trading_scheduler_simple.py {start|stop|check|status}")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "start":
        scheduler.start_program()
    elif command == "stop":
        scheduler.stop_program()
    elif command == "check":
        if scheduler.is_trading_day():
            print("Today is a trading day")
        else:
            print("Today is not a trading day")
    elif command == "status":
        scheduler.status()
    else:
        print("Invalid command")
        sys.exit(1)