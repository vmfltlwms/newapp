# crud/baseline_cache_service.py (개선된 버전)
from asyncio.log import logger
from container.baseline_container import Baseline_Container
from module.baseline_module import BaselineModule
from dependency_injector.wiring import inject, Provide
from dependency_injector.wiring import inject, Provide
from db.postgres_db import PostgresDB
from container.postgres_container import Postgres_Container
from typing import Optional, Dict, Any
import time

@inject
class BaselineCache():
    def __init__(self,
                 postgres_db: PostgresDB = Provide[Postgres_Container.postgres_db]) : 
        self.postgres_db = postgres_db
        self.baseline_module = BaselineModule(self.postgres_db)
        self.baseline = []
        self.baseline_dict = {}
        
    async def initialize_baseline_cache(self):
        """베이스라인 데이터를 메모리에 캐시"""
        try:
            # 모든 베이스라인 데이터 조회
            self.baseline = await self.baseline_module.get_all_baseline()
            
            # 빠른 조회를 위한 딕셔너리 생성
            for baseline in self.baseline:
                stock_code = baseline.stock_code
                step = baseline.step
                
                # stock_code별로 그룹화
                if stock_code not in self.baseline_dict:
                    self.baseline_dict[stock_code] = {}

                self.baseline_dict[stock_code][step] = {
                    'id': baseline.id,
                    'isfirst': True,                    # 기본값: True (첫 번째 접근)
                    'open_price': 0,                    # 기본값: 0 (아직 시가 미설정)
                    'decision_price': baseline.decision_price,
                    'quantity': baseline.quantity,
                    'low_price': baseline.low_price,
                    'high_price': baseline.high_price,
                    'step': baseline.step,
                    'created_at': baseline.created_at.timestamp(),
                    'updated_at': 0 #baseline.updated_at.timestamp()
                }
            
            logger.info(f"✅ 베이스라인 캐시 초기화 완료: {len(self.baseline)}개 항목")
            
        except Exception as e:
            logger.error(f"❌ 베이스라인 캐시 초기화 실패: {str(e)}")
            self.baseline = []
            self.baseline_dict = {}

    # 기존 메서드들 유지...
    def get_decision_price_v1(self, stock_code: str, step: int = 0) -> int:
        """방법 1: 리스트에서 직접 검색"""
        if not self.baseline:
            return None
            
        for baseline in self.baseline:
            if baseline.stock_code == stock_code and baseline.step == step:
                return baseline.decision_price
        
        return None

    def get_decision_price_v2(self, stock_code: str, step: int = 0) -> int:
        """방법 2: 딕셔너리 캐시에서 조회 (권장)"""
        if stock_code in self.baseline_dict and step in self.baseline_dict[stock_code]:
            return self.baseline_dict[stock_code][step]['decision_price']
        return None

    def get_baseline_info(self, stock_code: str, step: int = 0) -> dict:
        """방법 3: 해당 종목의 전체 베이스라인 정보 조회"""
        if stock_code in self.baseline_dict and step in self.baseline_dict[stock_code]:
            baseline_info = self.baseline_dict[stock_code][step].copy()  # 복사본 생성
            
            # 🔧 추가: updated_at이 datetime 객체인 경우 timestamp로 변환
            updated_at = baseline_info.get('updated_at')
            if hasattr(updated_at, 'timestamp'):
                baseline_info['updated_at'] = updated_at.timestamp()
            
            return baseline_info
        return None

    def get_all_steps_for_stock(self, stock_code: str) -> dict:
        """방법 4: 특정 종목의 모든 step 정보 조회"""
        return self.baseline_dict.get(stock_code, {})

    def get_latest_decision_price(self, stock_code: str) -> int:
        """방법 5: 해당 종목의 최신(최고 step) decision_price 조회"""
        if stock_code not in self.baseline_dict:
            return None
            
        steps = self.baseline_dict[stock_code]
        if not steps:
            return None
            
        # 최고 step 찾기
        max_step = max(steps.keys())
        return steps[max_step]['decision_price']

    def get_multiple_decision_prices(self, stock_codes: list, step: int = 0) -> dict:
        """방법 6: 여러 종목의 decision_price 한번에 조회"""
        result = {}
        for stock_code in stock_codes:
            price = self.get_decision_price_v2(stock_code, step)
            if price is not None:
                result[stock_code] = price
        return result

    def get_last_step(self, stock_code: str) -> int:
        """
        특정 종목의 마지막(최고) step 번호 조회
        
        Args:
            stock_code (str): 종목코드
            
        Returns:
            int: 마지막 step 번호, 종목이 없으면 -1 반환
        """
        try:
            if stock_code not in self.baseline_dict:
                logger.debug(f"⚠️ 종목 {stock_code}의 베이스라인 정보가 없습니다.")
                return -1
                
            steps = self.baseline_dict[stock_code]
            if not steps:
                logger.debug(f"⚠️ 종목 {stock_code}의 step 정보가 비어있습니다.")
                return -1
                
            # 최고 step 찾기
            max_step = max(steps.keys())
            logger.debug(f"📊 [{stock_code}] 마지막 step: {max_step}")
            
            return max_step
            
        except Exception as e:
            logger.error(f"❌ 마지막 step 조회 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return -1

    # 🆕 향상된 get_price_info 메서드 (isfirst, open_price 업데이트 기능 추가)
    def get_price_info(self, stock_code: str, step: int = 0) -> Dict[str, Any]:

        try:
            # 기본 정보 조회
            baseline_info = self.get_baseline_info(stock_code, step)
            if not baseline_info:
                logger.warning(f"⚠️ 종목 {stock_code} (step: {step})의 베이스라인 정보가 없습니다.")
                return None
            
            
            # 반환할 정보 구성
            result = {
                'stock_code': stock_code,
                'step': baseline_info['step'],
                'isfirst': baseline_info['isfirst'],
                'open_price': baseline_info['open_price'],
                'decision_price': baseline_info['decision_price'],
                'low_price': baseline_info['low_price'],
                'high_price': baseline_info['high_price'],
                'quantity': baseline_info['quantity'],
                'price_range': baseline_info['high_price'] - baseline_info['low_price'] if baseline_info['high_price'] and baseline_info['low_price'] else None,
                'created_at': baseline_info.get('created_at'),
                'updated_at': baseline_info.get('updated_at'),
            }
            
            logger.debug(f"📊 [{stock_code}] 가격 정보 조회 완료 - isfirst: {result['isfirst']}, open_price: {result['open_price']}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 가격 정보 조회 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None
    
    def update_baseline_cache(self, stock_code: str, step: int, 
                              isfirst: Optional[bool] = None, 
                              open_price: Optional[int] = None,
                              decision_price :Optional[int] = None ,
                              quantity : Optional[int] = None,
                              low_price : Optional[int] = None,
                              high_price : Optional[int] = None,
                              ):

        try:
            if stock_code not in self.baseline_dict or step not in self.baseline_dict[stock_code]:
                logger.warning(f"⚠️ 업데이트할 베이스라인 정보가 없습니다 - 종목: {stock_code}, step: {step}")
                return False
            
            # 기존 정보 가져오기
            baseline_info = self.baseline_dict[stock_code][step]
            

            if isfirst is not None:
                baseline_info['isfirst'] = isfirst
            
            if open_price is not None:
                baseline_info['open_price'] = open_price
            
            if decision_price is not None:
                baseline_info['decision_price'] = open_price        
                
            if quantity is not None:
                baseline_info['quantity'] = open_price
                
            if low_price is not None:
                baseline_info['low_price'] = open_price
                
            if high_price is not None:
                baseline_info['high_price'] = open_price                
            # 업데이트 시간 갱신

            baseline_info['updated_at'] = time.time()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 베이스라인 캐시 업데이트 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return False
    
    def get_price_analysis(self, baseline_info: Dict) -> Dict:
        """
        가격 분석 정보 생성 (내부 메서드)
        
        Args:
            baseline_info (Dict): 베이스라인 정보
            
        Returns:
            Dict: 분석 정보
        """
        try:
            decision_price = baseline_info['decision_price']
            low_price = baseline_info['low_price']
            high_price = baseline_info['high_price']
            open_price = baseline_info['open_price']
            
            analysis = {
                'price_range_width': high_price - low_price if high_price and low_price else 0,
                'price_range_ratio': round(((high_price - low_price) / decision_price * 100), 2) if decision_price and high_price and low_price else 0,
                'decision_vs_low_gap': round(((decision_price - low_price) / low_price * 100), 2) if decision_price and low_price else 0,
                'decision_vs_high_gap': round(((high_price - decision_price) / decision_price * 100), 2) if decision_price and high_price else 0
            }
            
            # 시가가 설정된 경우 추가 분석
            if open_price and open_price > 0:
                analysis.update({
                    'open_vs_decision': round(((open_price - decision_price) / decision_price * 100), 2),
                    'open_vs_low': round(((open_price - low_price) / low_price * 100), 2) if low_price else 0,
                    'open_vs_high': round(((high_price - open_price) / open_price * 100), 2) if high_price else 0,
                    'open_position_in_range': round(((open_price - low_price) / (high_price - low_price)), 3) if high_price and low_price and (high_price != low_price) else 0.5
                })
            else:
                analysis.update({
                    'open_vs_decision': None,
                    'open_vs_low': None,
                    'open_vs_high': None,
                    'open_position_in_range': None
                })
            
            return analysis
            
        except Exception as e:
            logger.error(f"❌ 가격 분석 생성 실패: {str(e)}")
            return {}

    # 🆕 편의 메서드들 추가
    def set_open_price(self, stock_code: str, open_price: int, step: int = 0) -> bool:
        """
        시가 설정 (편의 메서드)
        
        Args:
            stock_code (str): 종목코드
            open_price (int): 시가
            step (int): 베이스라인 단계
            
        Returns:
            bool: 성공 여부
        """
        return self.update_baseline_cache(stock_code, step, None, open_price)
    
    def set_isfirst(self, stock_code: str, isfirst: bool, step: int = 0) -> bool:
        """
        첫 번째 접근 플래그 설정 (편의 메서드)
        
        Args:
            stock_code (str): 종목코드
            isfirst (bool): 첫 번째 접근 여부
            step (int): 베이스라인 단계
            
        Returns:
            bool: 성공 여부
        """
        return self.update_baseline_cache(stock_code, step, isfirst, None)
    
    def mark_as_accessed(self, stock_code: str, open_price: int, step: int = 0) -> Dict:
        """
        종목을 접근됨으로 표시하고 시가 설정 (편의 메서드)
        
        Args:
            stock_code (str): 종목코드
            open_price (int): 시가
            step (int): 베이스라인 단계
            
        Returns:
            Dict: 업데이트된 가격 정보
        """
        return self.get_price_info(stock_code, step, isfirst=False, open_price=open_price)
    
    def get_open_price_status(self, stock_code: str, step: int = 0) -> Dict:
        try:
            baseline_info = self.get_baseline_info(stock_code, step)
            if not baseline_info:
                return {'exists': False}
            
            open_price = baseline_info['open_price']
            isfirst = baseline_info['isfirst']
            
            return {
                'exists': True,
                'stock_code': stock_code,
                'step': step,
                'isfirst': isfirst,
                'open_price': open_price,
                'is_open_price_set': open_price is not None and open_price > 0,
                'status': 'first_access' if isfirst else 'already_accessed',
                'needs_open_price': isfirst and (open_price is None or open_price <= 0)
            }
            
        except Exception as e:
            logger.error(f"❌ 시가 상태 확인 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return {'exists': False, 'error': str(e)}

    def get_isfirst(self, stock_code: str, step: int = 0) -> bool: 
        baseline_info = self.get_baseline_info(stock_code, step)
        if baseline_info is not None : 
            return baseline_info.get('isfirst')
        else : return False


    # 베이스라인 캐시 업데이트 메서드들
    async def refresh_baseline_cache(self):
        """베이스라인 캐시 새로고침"""
        await self.initialize_baseline_cache()

    def add_to_cache(self, baseline):
        """새 베이스라인을 캐시에 추가"""
        if not hasattr(self, 'baseline') or self.baseline is None:
            self.baseline = []
        if not hasattr(self, 'baseline_dict') or self.baseline_dict is None:
            self.baseline_dict = {}
            
        # 리스트에 추가
        self.baseline.append(baseline)
        
        # 딕셔너리에 추가
        stock_code = baseline.stock_code
        step = baseline.step
        
        if stock_code not in self.baseline_dict:
            self.baseline_dict[stock_code] = {}
            
        self.baseline_dict[stock_code][step] = {
            'id': baseline.id,
            'isfirst': True,  # 새로 추가되는 경우 기본값
            'open_price': 0,  # 새로 추가되는 경우 기본값
            'decision_price': baseline.decision_price,
            'quantity': baseline.quantity,
            'low_price': baseline.low_price,
            'high_price': baseline.high_price,
            'step': baseline.step,
            'created_at': baseline.created_at,
            'updated_at': baseline.updated_at
        }

    def remove_from_cache(self, stock_code: str, step: int = None):
        """캐시에서 베이스라인 제거"""
        # 리스트에서 제거
        if self.baseline:
            self.baseline = [b for b in self.baseline 
                           if not (b.stock_code == stock_code and (step is None or b.step == step))]
        
        # 딕셔너리에서 제거
        if stock_code in self.baseline_dict:
            if step is None:
                # 해당 종목의 모든 step 제거
                del self.baseline_dict[stock_code]
            elif step in self.baseline_dict[stock_code]:
                # 특정 step만 제거
                del self.baseline_dict[stock_code][step]
                # 빈 딕셔너리면 종목 전체 제거
                if not self.baseline_dict[stock_code]:
                    del self.baseline_dict[stock_code]
                    
    def add_baseline_cache(self, stock_code: str, baseline_info: dict) -> bool:
        """
        새로운 베이스라인을 캐시에 추가하는 메서드
        
        Args:
            stock_code (str): 종목코드
            baseline_info (dict): 베이스라인 정보 딕셔너리
                {
                    'decision_price': int,      # 결정가 (필수)
                    'quantity': int,            # 수량 (필수)
                    'low_price': int,           # 저가 (필수)
                    'high_price': int,          # 고가 (필수)
                    'step': int,                # 단계 (선택, 기본값: 자동계산)
                    'isfirst': bool,            # 첫 접근 여부 (선택, 기본값: True)
                    'open_price': int,          # 시가 (선택, 기본값: 0)
                    'id': int,                  # ID (선택)
                    'created_at': datetime,     # 생성시간 (선택)
                    'updated_at': datetime      # 수정시간 (선택)
                }
        
        Returns:
            bool: 추가 성공 여부
        """
        try:
            # 필수 파라미터 검증
            if not stock_code:
                logger.error("❌ stock_code는 필수 파라미터입니다.")
                return False
            
            required_fields = ['decision_price', 'quantity', 'low_price', 'high_price']
            for field in required_fields:
                if field not in baseline_info:
                    logger.error(f"❌ {field}는 필수 파라미터입니다.")
                    return False
                if baseline_info[field] is None:
                    logger.error(f"❌ {field} 값이 None입니다.")
                    return False
            
            # step이 없으면 자동으로 다음 step 계산
            if 'step' not in baseline_info or baseline_info['step'] is None:
                current_last_step = self.get_last_step(stock_code)
                step = current_last_step + 1 if current_last_step >= 0 else 0
            else:
                step = baseline_info['step']
            
            # 기존 데이터 중복 검사
            if stock_code in self.baseline_dict and step in self.baseline_dict[stock_code]:
                logger.warning(f"⚠️ 이미 존재하는 베이스라인입니다 - 종목: {stock_code}, step: {step}")
                return False
            
            # 캐시 초기화 확인
            if not hasattr(self, 'baseline') or self.baseline is None:
                self.baseline = []
            if not hasattr(self, 'baseline_dict') or self.baseline_dict is None:
                self.baseline_dict = {}
            
            # 현재 시간 생성 (created_at, updated_at이 없는 경우)
            from datetime import datetime
            current_time = datetime.now()
            
            # Mock Baseline 객체 생성 (기존 add_to_cache와 호환성 유지)
            class MockBaseline:
                def __init__(self, data_dict):
                    self.id = data_dict.get('id')
                    self.stock_code = stock_code
                    self.decision_price = data_dict['decision_price']
                    self.quantity = data_dict['quantity']
                    self.low_price = data_dict['low_price']
                    self.high_price = data_dict['high_price']
                    self.step = step
                    self.created_at = data_dict.get('created_at', current_time)
                    self.updated_at = data_dict.get('updated_at', current_time)
            
            # Mock 객체 생성
            mock_baseline = MockBaseline(baseline_info)
            
            # 리스트에 추가 (기존 baseline 리스트에)
            self.baseline.append(mock_baseline)
            
            # 딕셔너리에 추가
            if stock_code not in self.baseline_dict:
                self.baseline_dict[stock_code] = {}
                
            self.baseline_dict[stock_code][step] = {
                'id': baseline_info.get('id'),
                'isfirst': baseline_info.get('isfirst', True),
                'open_price': baseline_info.get('open_price', 0),
                'decision_price': baseline_info['decision_price'],
                'quantity': baseline_info['quantity'],
                'low_price': baseline_info['low_price'],
                'high_price': baseline_info['high_price'],
                'step': step,
                'created_at': baseline_info.get('created_at', current_time),
                'updated_at': baseline_info.get('updated_at', current_time)
            }
            
            logger.info(f"✅ 베이스라인 캐시 추가 성공 - 종목: {stock_code}, step: {step}, "
                      f"결정가: {baseline_info['decision_price']:,}원, 수량: {baseline_info['quantity']}주")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 베이스라인 캐시 추가 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return False