import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

class OrderConditionManager:
    """주식 매매 조건을 관리하는 싱글톤 클래스"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.order_dic: Dict = {}
            self.order_file: str = "stock_orders.json"
            self.logger = logging.getLogger(__name__)
            self.initialized = False
    
    async def initialize(self, filename: str = "stock_orders.json") -> None:
        """
        비동기 초기화 메서드
        
        Args:
            filename: 불러올 JSON 파일명
        """
        self.order_file = filename
        self._load_orders()
        self.initialized = True
        self.logger.info(f"✅ StockOrderManager 초기화 완료 - 파일: {filename}")
    
    def _load_orders(self) -> None:
        """파일에서 주문 데이터를 불러오기"""
        if os.path.exists(self.order_file):
            try:
                with open(self.order_file, 'r', encoding='utf-8') as f:
                    self.order_dic = json.load(f)
                    self.logger.info(f"📁 '{self.order_file}' 파일에서 데이터를 성공적으로 불러왔습니다.")
                    self.logger.info(f"   - 등록된 주식: {len(self.order_dic)}개")
                    for stock_code in self.order_dic:
                        up_count = len(self.order_dic[stock_code].get('up', []))
                        down_count = len(self.order_dic[stock_code].get('down', []))
                        self.logger.info(f"   - {stock_code}: 상승조건 {up_count}개, 하락조건 {down_count}개")
            except (json.JSONDecodeError, IOError) as e:
                self.logger.error(f"파일 읽기 오류: {e}")
                self.order_dic = {}
        else:
            self.logger.info(f"📝 '{self.order_file}' 파일이 없습니다. 새로운 파일을 생성합니다.")
            self.order_dic = {}
            self._save_orders()
    
    def _save_orders(self) -> bool:
        """현재 order_dic을 파일에 저장"""
        try:
            # 백업 파일 생성
            if os.path.exists(self.order_file):
                backup_name = f"{self.order_file}.backup"
                os.replace(self.order_file, backup_name)
            
            # 디렉토리가 없으면 생성
            Path(self.order_file).parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.order_file, 'w', encoding='utf-8') as f:
                json.dump(self.order_dic, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            self.logger.error(f"파일 저장 오류: {e}")
            return False
    
    def add_stock(self, stock_code: str) -> bool:
        """새로운 주식 코드 추가"""
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
            
        if stock_code not in self.order_dic:
            self.order_dic[stock_code] = {"up": [], "down": []}
            success = self._save_orders()
            if success:
                self.logger.info(f"✅ 주식 '{stock_code}' 추가 완료")
            return success
        else:
            self.logger.info(f"ℹ️ 주식 '{stock_code}'는 이미 존재합니다.")
            return False
    
    def add_condition(self, stock_code: str, direction: str, condition_num: int, price: int, **kwargs) -> bool:
        """
        조건 추가
        
        Args:
            stock_code: 주식 코드
            direction: 'up' 또는 'down'
            condition_num: 조건 번호 (1~7)
            price: 목표 가격
            **kwargs: 추가 조건 (volume, percent 등)
            
        Returns:
            성공 여부
            
        Example:
            add_condition("005930", "up", 1, 75000)  # up1: 75000
            add_condition("005930", "down", 3, 70000, volume=100000)  # down3: 70000, volume 조건 추가
        """
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
            
        # 유효성 검사
        if direction not in ["up", "down"]:
            raise ValueError("direction은 'up' 또는 'down' 이어야 합니다.")
        
        if condition_num not in range(1, 8):
            raise ValueError("condition_num은 1~7 사이의 숫자여야 합니다.")
        
        if price <= 0:
            raise ValueError("price는 0보다 큰 값이어야 합니다.")
        
        # 주식 코드가 없으면 추가
        if stock_code not in self.order_dic:
            self.add_stock(stock_code)
        
        # 조건 키 생성 (예: "up1", "down3")
        condition_key = f"{direction}{condition_num}"
        
        # 기존 조건에서 동일한 키가 있는지 확인
        existing_conditions = self.order_dic[stock_code][direction]
        for i, cond in enumerate(existing_conditions):
            if condition_key in cond:
                # 기존 조건 업데이트
                self.logger.warning(f"'{stock_code}'의 {condition_key} 조건이 이미 존재합니다. 업데이트합니다.")
                existing_conditions[i] = {
                    condition_key: price,
                    'timestamp': datetime.now().isoformat(),
                    **kwargs
                }
                success = self._save_orders()
                if success:
                    self.logger.info(f"✅ '{stock_code}'의 {condition_key} 조건 업데이트 완료: {price}")
                return success
        
        # 새로운 조건 추가
        condition = {
            condition_key: price,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        
        self.order_dic[stock_code][direction].append(condition)
        
        success = self._save_orders()
        if success:
            self.logger.info(f"✅ '{stock_code}'의 {condition_key} 조건 추가 완료: {price}")
        return success
    
    def add_condition_dict(self, stock_code: str, direction: str, condition: Dict) -> bool:
        """
        딕셔너리 형태로 조건 추가 (기존 방식 유지)
        
        Args:
            stock_code: 주식 코드
            direction: 'up' 또는 'down'
            condition: 조건 딕셔너리 (예: {"up1": 75000} 또는 {"down3": 70000, "volume": 100000})
            
        Returns:
            성공 여부
        """
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
            
        if stock_code not in self.order_dic:
            self.add_stock(stock_code)
        
        if direction not in ["up", "down"]:
            raise ValueError("direction은 'up' 또는 'down' 이어야 합니다.")
        
        # 조건 키 유효성 검사
        valid_keys = [f"{direction}{i}" for i in range(1, 8)]
        condition_keys = [k for k in condition.keys() if k.startswith(direction)]
        
        if not condition_keys:
            raise ValueError(f"조건에는 최소한 하나의 {direction} 키가 있어야 합니다. (예: {valid_keys})")
        
        invalid_keys = [k for k in condition_keys if k not in valid_keys]
        if invalid_keys:
            raise ValueError(f"유효하지 않은 조건 키: {invalid_keys}. 유효한 키: {valid_keys}")
        
        # 타임스탬프 추가
        condition['timestamp'] = datetime.now().isoformat()
        self.order_dic[stock_code][direction].append(condition)
        
        success = self._save_orders()
        if success:
            self.logger.info(f"✅ '{stock_code}'의 {direction} 조건 추가 완료: {condition}")
        return success
    
    def update_condition(self, stock_code: str, direction: str, key: str, new_value: Any) -> bool:
        """조건 업데이트"""
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
            
        if stock_code in self.order_dic and direction in self.order_dic[stock_code]:
            updated = False
            for condition in self.order_dic[stock_code][direction]:
                if key in condition:
                    old_value = condition[key]
                    condition[key] = new_value
                    condition['updated'] = datetime.now().isoformat()
                    updated = True
                    self.logger.info(f"✅ '{stock_code}'의 {direction} 조건 업데이트: {key} {old_value} → {new_value}")
                    break
            
            if updated:
                return self._save_orders()
            else:
                self.logger.warning(f"'{stock_code}'의 {direction}에서 '{key}' 조건을 찾을 수 없습니다.")
        else:
            self.logger.warning(f"주식 코드 '{stock_code}' 또는 방향 '{direction}'이 존재하지 않습니다.")
        return False
    
    def get_condition(self, stock_code: str, direction: str, condition_num: int) -> Optional[Dict]:
        """
        특정 조건 조회
        
        Args:
            stock_code: 주식 코드
            direction: 'up' 또는 'down'
            condition_num: 조건 번호 (1~7)
            
        Returns:
            조건 딕셔너리 또는 None
        """
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
            
        if stock_code not in self.order_dic:
            return None
            
        condition_key = f"{direction}{condition_num}"
        conditions = self.order_dic[stock_code][direction]
        
        for cond in conditions:
            if condition_key in cond:
                return cond
        
        return None
    
    def delete_condition_by_num(self, stock_code: str, direction: str, condition_num: int) -> bool:
        """
        조건 번호로 조건 삭제
        
        Args:
            stock_code: 주식 코드
            direction: 'up' 또는 'down'
            condition_num: 조건 번호 (1~7)
            
        Returns:
            성공 여부
        """
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
            
        condition_key = f"{direction}{condition_num}"
        return self.delete_condition(stock_code, direction, condition_key)
    
    def get_available_condition_nums(self, stock_code: str, direction: str) -> List[int]:
        """
        사용 가능한 조건 번호 조회
        
        Args:
            stock_code: 주식 코드
            direction: 'up' 또는 'down'
            
        Returns:
            사용 가능한 조건 번호 리스트 (1~7 중 비어있는 번호)
        """
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
            
        if stock_code not in self.order_dic:
            return list(range(1, 8))  # 1~7 모두 사용 가능
        
        used_nums = []
        conditions = self.order_dic[stock_code][direction]
        
        for cond in conditions:
            for key in cond.keys():
                if key.startswith(direction) and key[len(direction):].isdigit():
                    num = int(key[len(direction):])
                    if 1 <= num <= 7:
                        used_nums.append(num)
        
        return [num for num in range(1, 8) if num not in used_nums]
        """조건 삭제"""
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
            
        if stock_code in self.order_dic and direction in self.order_dic[stock_code]:
            deleted = False
            for i, condition in enumerate(self.order_dic[stock_code][direction]):
                if key in condition:
                    deleted_condition = self.order_dic[stock_code][direction].pop(i)
                    deleted = True
                    self.logger.info(f"✅ '{stock_code}'의 {direction} 조건 삭제: {deleted_condition}")
                    break
            
            if deleted:
                return self._save_orders()
            else:
                self.logger.warning(f"'{stock_code}'의 {direction}에서 '{key}' 조건을 찾을 수 없습니다.")
        else:
            self.logger.warning(f"주식 코드 '{stock_code}' 또는 방향 '{direction}'이 존재하지 않습니다.")
        return False
    
    def delete_stock(self, stock_code: str) -> bool:
        """주식 코드 삭제"""
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
            
        if stock_code in self.order_dic:
            del self.order_dic[stock_code]
            success = self._save_orders()
            if success:
                self.logger.info(f"✅ 주식 '{stock_code}' 삭제 완료")
            return success
        else:
            self.logger.warning(f"주식 코드 '{stock_code}'가 존재하지 않습니다.")
            return False
    
    def get_stock_conditions(self, stock_code: str) -> Optional[Dict]:
        """특정 주식의 조건 조회"""
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
        return self.order_dic.get(stock_code)
    
    def get_all_conditions(self) -> Dict:
        """모든 조건 조회"""
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
        return self.order_dic.copy()
    
    def get_order_dic(self) -> Dict:
        """order_dic 직접 반환 (읽기 전용 권장)"""
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
        return self.order_dic
    
    def print_summary(self) -> None:
        """주문 조건 요약 출력"""
        if not self.initialized:
            raise RuntimeError("StockOrderManager가 초기화되지 않았습니다.")
            
        print("\n" + "="*50)
        print("📊 주식 매매 조건 요약")
        print("="*50)
        
        if not self.order_dic:
            print("등록된 주식이 없습니다.")
            return
        
        for stock_code, conditions in self.order_dic.items():
            print(f"\n🏢 주식 코드: {stock_code}")
            
            # 상승 조건
            print(f"  📈 상승 조건: {len(conditions['up'])}개")
            for i, cond in enumerate(conditions['up'], 1):
                cond_copy = cond.copy()
                cond_copy.pop('timestamp', None)
                cond_copy.pop('updated', None)
                print(f"     {i}. {cond_copy}")
            
            # 하락 조건
            print(f"  📉 하락 조건: {len(conditions['down'])}개")
            for i, cond in enumerate(conditions['down'], 1):
                cond_copy = cond.copy()
                cond_copy.pop('timestamp', None)
                cond_copy.pop('updated', None)
                print(f"     {i}. {cond_copy}")
    
    async def shutdown(self) -> None:
        """종료 시 처리"""
        if self.initialized:
            self._save_orders()
            self.logger.info("🛑 StockOrderManager 종료 완료")
            self.initialized = False


# 싱글톤 인스턴스 생성
stock_order_manager = OrderConditionManager()


# 사용 예제 (별도 파일)
if __name__ == "__main__":
    import asyncio
    
    async def main():
        # 초기화
        await stock_order_manager.initialize()
        
        # 1. 간편한 방식으로 조건 추가
        stock_order_manager.add_stock("005930")
        
        # up1 조건 추가 (75,000원에 매도)
        stock_order_manager.add_condition("005930", "up", 1, 75000)
        
        # down3 조건 추가 (70,000원에 매수, 거래량 조건 포함)
        stock_order_manager.add_condition("005930", "down", 3, 70000, volume=100000)
        
        # 2. 사용 가능한 조건 번호 확인
        available_up = stock_order_manager.get_available_condition_nums("005930", "up")
        print(f"사용 가능한 상승 조건 번호: {available_up}")  # [2, 3, 4, 5, 6, 7]
        
        # 3. 특정 조건 조회
        condition = stock_order_manager.get_condition("005930", "up", 1)
        print(f"up1 조건: {condition}")
        
        # 4. 조건 번호로 삭제
        stock_order_manager.delete_condition_by_num("005930", "down", 3)
        
        # 5. 딕셔너리 방식으로도 사용 가능 (기존 방식)
        stock_order_manager.add_condition_dict("005930", "up", {"up2": 76000, "up3": 77000})
        
        # 요약 출력
        stock_order_manager.print_summary()
        
        # 종료
        await stock_order_manager.shutdown()
    
    asyncio.run(main())

# 싱글톤 인스턴스 생성
order_condition_manager = OrderConditionManager()

