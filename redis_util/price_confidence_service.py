# services/price_confidence_service.py
import json
import time
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ConfidenceLevel(Enum):
    """신뢰구간 레벨"""
    VERY_HIGH = "매우 높음"     # 90% 이상
    HIGH = "높음"              # 70-90%
    MEDIUM = "보통"            # 30-70%
    LOW = "낮음"               # 10-30%
    VERY_LOW = "매우 낮음"      # 10% 미만

@dataclass
class OpenPriceData:
    """시가 데이터 클래스"""
    stock_code: str
    open_price: int
    baseline_decision_price: int
    baseline_low_price: int
    baseline_high_price: int
    recorded_time: float
    confidence_score: float
    confidence_level: ConfidenceLevel
    position_in_range: float  # 0.0 ~ 1.0

class PriceConfidenceService:
    """시가 기록 및 신뢰구간 분석 서비스"""
    
    def __init__(self, redis_db):
        self.redis_db = redis_db
        self.REDIS_KEY_PREFIX = "open_price"
        self.EXPIRE_TIME = 60 * 60 * 12  # 12시간 (장 마감 후까지)
    
    def _get_redis_key(self, stock_code: str) -> str:
        """Redis 키 생성"""
        return f"{self.REDIS_KEY_PREFIX}:{stock_code}"
    
    async def record_open_price(self, stock_code: str, current_price: int,
                               baseline_decision_price: int, baseline_low_price: int,
                               baseline_high_price: int) -> Optional[OpenPriceData]:
        """
        오늘 첫 번째 가격을 시가로 기록하고 신뢰구간 분석
        
        Args:
            stock_code: 종목코드
            current_price: 현재가 (시가가 될 예정)
            baseline_decision_price: 예측 기준가
            baseline_low_price: 예측 최저가
            baseline_high_price: 예측 최고가
        
        Returns:
            OpenPriceData: 시가 데이터 및 신뢰구간 분석 결과
        """
        try:
            redis_key = self._get_redis_key(stock_code)
            
            # 이미 시가가 기록되어 있는지 확인
            existing_data = await self.redis_db.get(redis_key)
            if existing_data:
                logger.debug(f"종목 {stock_code}의 시가가 이미 기록되어 있습니다.")
                return self._parse_open_price_data(existing_data)
            
            # 신뢰구간 분석 수행
            confidence_analysis = self._analyze_confidence(
                current_price, baseline_decision_price, 
                baseline_low_price, baseline_high_price
            )
            
            # 시가 데이터 생성
            open_price_data = OpenPriceData(
                stock_code=stock_code,
                open_price=current_price,
                baseline_decision_price=baseline_decision_price,
                baseline_low_price=baseline_low_price,
                baseline_high_price=baseline_high_price,
                recorded_time=time.time(),
                confidence_score=confidence_analysis['confidence_score'],
                confidence_level=confidence_analysis['confidence_level'],
                position_in_range=confidence_analysis['position_in_range']
            )
            
            # Redis에 저장
            value = json.dumps(open_price_data.__dict__, ensure_ascii=False, default=str)
            await self.redis_db.set(redis_key, value)
            await self.redis_db.expire(redis_key, self.EXPIRE_TIME)
            
            logger.info(f"🌅 시가 기록 완료 - 종목: {stock_code}, 시가: {current_price}, "
                       f"예측가: {baseline_decision_price}, 신뢰도: {confidence_analysis['confidence_level'].value}")
            
            return open_price_data
            
        except Exception as e:
            logger.error(f"❌ 시가 기록 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None
    
    def _analyze_confidence(self, open_price: int, decision_price: int,
                           low_price: int, high_price: int) -> Dict:
        """
        시가와 예측가의 신뢰구간 분석
        
        Args:
            open_price: 실제 시가
            decision_price: 예측 기준가
            low_price: 예측 최저가
            high_price: 예측 최고가
        
        Returns:
            Dict: 신뢰구간 분석 결과
        """
        try:
            # 예측 범위 계산
            price_range = high_price - low_price
            if price_range <= 0:
                return {
                    'confidence_score': 0,
                    'confidence_level': ConfidenceLevel.VERY_LOW,
                    'position_in_range': 0.5,
                    'error': '잘못된 가격 범위'
                }
            
            # 시가의 예측 범위 내 위치 (0.0 ~ 1.0)
            if open_price <= low_price:
                position_in_range = 0.0
            elif open_price >= high_price:
                position_in_range = 1.0
            else:
                position_in_range = (open_price - low_price) / price_range
            
            # 예측 기준가와 실제 시가의 차이 분석
            price_diff = abs(open_price - decision_price)
            price_diff_ratio = price_diff / decision_price * 100  # 예측가 대비 차이 비율
            
            # 예측 범위 대비 차이 비율
            range_diff_ratio = price_diff / (price_range / 2) * 100  # 범위의 절반 대비 차이
            
            # 신뢰도 스코어 계산 (여러 요소 종합)
            confidence_score = self._calculate_confidence_score(
                price_diff_ratio, range_diff_ratio, position_in_range
            )
            
            # 신뢰도 레벨 결정
            confidence_level = self._get_confidence_level(confidence_score)
            
            return {
                'confidence_score': round(confidence_score, 2),
                'confidence_level': confidence_level,
                'position_in_range': round(position_in_range, 3),
                'price_diff': price_diff,
                'price_diff_ratio': round(price_diff_ratio, 2),
                'range_diff_ratio': round(range_diff_ratio, 2),
                'analysis_details': {
                    'open_vs_decision': round(((open_price - decision_price) / decision_price) * 100, 2),
                    'distance_to_low': round(((open_price - low_price) / low_price) * 100, 2),
                    'distance_to_high': round(((high_price - open_price) / open_price) * 100, 2),
                    'range_width': round((price_range / decision_price) * 100, 2)  # 예측 범위의 폭 (기준가 대비 %)
                }
            }
            
        except Exception as e:
            logger.error(f"신뢰구간 분석 오류: {str(e)}")
            return {
                'confidence_score': 0,
                'confidence_level': ConfidenceLevel.VERY_LOW,
                'position_in_range': 0.5,
                'error': str(e)
            }
    
    def _calculate_confidence_score(self, price_diff_ratio: float, 
                                   range_diff_ratio: float, 
                                   position_in_range: float) -> float:
        """
        신뢰도 스코어 계산 (0 ~ 100)
        
        Args:
            price_diff_ratio: 예측가 대비 차이 비율 (%)
            range_diff_ratio: 예측 범위 대비 차이 비율 (%)
            position_in_range: 예측 범위 내 위치 (0.0 ~ 1.0)
        """
        try:
            # 1. # 예측가 대비 차이 비율
            if price_diff_ratio <= 1:
                accuracy_score = 100
            elif price_diff_ratio <= 3:
                accuracy_score = 90 - (price_diff_ratio - 1) * 10
            elif price_diff_ratio <= 5:
                accuracy_score = 70 - (price_diff_ratio - 3) * 15
            elif price_diff_ratio <= 10:
                accuracy_score = 40 - (price_diff_ratio - 5) * 6
            else:
                accuracy_score = max(0, 10 - (price_diff_ratio - 10) * 0.5)
            
            # 2. 범위 내 위치 점수 (중앙에 가까울수록 높은 점수)
            center_distance = abs(position_in_range - 0.5) * 2  # 0 ~ 1
            position_score = (1 - center_distance) * 100
            
            # 3. 범위 적정성 점수 (범위가 너무 넓거나 좁으면 감점)
            if range_diff_ratio <= 50:
                range_score = 100
            elif range_diff_ratio <= 100:
                range_score = 80
            elif range_diff_ratio <= 200:
                range_score = 60
            else:
                range_score = 40
            
            # 가중 평균으로 최종 점수 계산
            final_score = (accuracy_score * 0.5 + position_score * 0.3 + range_score * 0.2)
            
            return max(0, min(100, final_score))
            
        except Exception as e:
            logger.error(f"신뢰도 스코어 계산 오류: {str(e)}")
            return 0
    
    def _get_confidence_level(self, confidence_score: float) -> ConfidenceLevel:
        """신뢰도 스코어를 레벨로 변환"""
        if confidence_score >= 90:
            return ConfidenceLevel.VERY_HIGH
        elif confidence_score >= 70:
            return ConfidenceLevel.HIGH
        elif confidence_score >= 30:
            return ConfidenceLevel.MEDIUM
        elif confidence_score >= 10:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW
    
    def _parse_open_price_data(self, json_data: str) -> Optional[OpenPriceData]:
        """JSON 데이터를 OpenPriceData 객체로 변환"""
        try:
            data = json.loads(json_data)
            
            # ConfidenceLevel enum 복원
            confidence_level_str = data.get('confidence_level')
            if isinstance(confidence_level_str, str):
                confidence_level = ConfidenceLevel(confidence_level_str)
            else:
                confidence_level = ConfidenceLevel.MEDIUM
            
            return OpenPriceData(
                stock_code=data['stock_code'],
                open_price=data['open_price'],
                baseline_decision_price=data['baseline_decision_price'],
                baseline_low_price=data['baseline_low_price'],
                baseline_high_price=data['baseline_high_price'],
                recorded_time=data['recorded_time'],
                confidence_score=data['confidence_score'],
                confidence_level=confidence_level,
                position_in_range=data['position_in_range']
            )
            
        except Exception as e:
            logger.error(f"시가 데이터 파싱 오류: {str(e)}")
            return None
    
    async def get_open_price_data(self, stock_code: str) -> Optional[OpenPriceData]:
        """
        시가 데이터 조회
        
        Args:
            stock_code: 종목코드
            
        Returns:
            OpenPriceData: 시가 데이터 또는 None
        """
        try:
            redis_key = self._get_redis_key(stock_code)
            data = await self.redis_db.get(redis_key)
            
            if not data:
                return None
            
            return self._parse_open_price_data(data)
            
        except Exception as e:
            logger.error(f"❌ 시가 데이터 조회 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None
    
    async def get_confidence_summary(self, stock_code: str) -> Optional[Dict]:
        """
        신뢰도 요약 정보 조회
        
        Args:
            stock_code: 종목코드
            
        Returns:
            Dict: 신뢰도 요약 정보
        """
        try:
            open_price_data = await self.get_open_price_data(stock_code)
            
            if not open_price_data:
                return None
            
            # 추가 분석 정보 계산
            current_time = time.time()
            elapsed_hours = (current_time - open_price_data.recorded_time) / 3600
            
            summary = {
                'stock_code': stock_code,
                'open_price': open_price_data.open_price,
                'predicted_price': open_price_data.baseline_decision_price,
                'price_range': {
                    'low': open_price_data.baseline_low_price,
                    'high': open_price_data.baseline_high_price,
                    'width': open_price_data.baseline_high_price - open_price_data.baseline_low_price
                },
                'confidence': {
                    'score': open_price_data.confidence_score,
                    'level': open_price_data.confidence_level.value,
                    'position_in_range': open_price_data.position_in_range
                },
                'analysis': {
                    'prediction_accuracy': round(((1 - abs(open_price_data.open_price - open_price_data.baseline_decision_price) / open_price_data.baseline_decision_price) * 100), 2),
                    'price_difference': open_price_data.open_price - open_price_data.baseline_decision_price,
                    'elapsed_hours': round(elapsed_hours, 1)
                },
                'interpretation': self._get_confidence_interpretation(open_price_data)
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ 신뢰도 요약 조회 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None
    
    def _get_confidence_interpretation(self, data: OpenPriceData) -> str:
        """신뢰도 해석 메시지 생성"""
        try:
            level = data.confidence_level
            position = data.position_in_range
            
            # 위치 해석
            if position < 0.2:
                position_desc = "예측 범위 하단"
            elif position < 0.4:
                position_desc = "예측 범위 중하단"
            elif position < 0.6:
                position_desc = "예측 범위 중앙"
            elif position < 0.8:
                position_desc = "예측 범위 중상단"
            else:
                position_desc = "예측 범위 상단"
            
            # 기본 해석 메시지
            base_message = f"시가가 {position_desc}에 위치하여 "
            
            if level == ConfidenceLevel.VERY_HIGH:
                return base_message + "예측이 매우 정확했습니다. 높은 신뢰도로 거래 전략을 수립할 수 있습니다."
            elif level == ConfidenceLevel.HIGH:
                return base_message + "예측이 상당히 정확했습니다. 신뢰할 만한 거래 신호입니다."
            elif level == ConfidenceLevel.MEDIUM:
                return base_message + "예측이 보통 수준입니다. 추가 지표를 참고하여 신중한 거래가 필요합니다."
            elif level == ConfidenceLevel.LOW:
                return base_message + "예측 정확도가 낮습니다. 거래 시 주의가 필요합니다."
            else:
                return base_message + "예측이 부정확했습니다. 거래 전략을 재검토해야 합니다."
                
        except Exception as e:
            return "신뢰도 해석 중 오류가 발생했습니다."
    
    async def get_all_confidence_data(self) -> Dict:
        """
        전체 종목의 신뢰도 데이터 조회
        
        Returns:
            Dict: 전체 신뢰도 데이터 요약
        """
        try:
            pattern = f"{self.REDIS_KEY_PREFIX}:*"
            keys = await self.redis_db.keys(pattern)
            
            if not keys:
                return {'total_count': 0, 'stocks': {}}
            
            all_data = {}
            confidence_stats = {
                'VERY_HIGH': 0,
                'HIGH': 0,
                'MEDIUM': 0,
                'LOW': 0,
                'VERY_LOW': 0
            }
            
            for key in keys:
                stock_code = key.split(":")[-1]
                summary = await self.get_confidence_summary(stock_code)
                
                if summary:
                    all_data[stock_code] = summary
                    level = summary['confidence']['level']
                    confidence_stats[level.replace(' ', '_').upper()] += 1
            
            return {
                'total_count': len(all_data),
                'stocks': all_data,
                'statistics': confidence_stats,
                'average_confidence': round(sum(data['confidence']['score'] for data in all_data.values()) / len(all_data), 2) if all_data else 0
            }
            
        except Exception as e:
            logger.error(f"❌ 전체 신뢰도 데이터 조회 실패: {str(e)}")
            return {'total_count': 0, 'stocks': {}, 'error': str(e)}


# ===== SmartTradingStrategy 클래스에 추가할 메서드 =====

class SmartTradingStrategy:
    # 기존 코드...
    
    def __init__(self, kiwoom_module, redis_db=None):
        self.kiwoom_module = kiwoom_module
        # 기존 config...
        
        # PriceConfidenceService 추가
        if redis_db:
            self.price_confidence_service = PriceConfidenceService(redis_db)
        else:
            self.price_confidence_service = None
    
    async def analyze_open_price_confidence(self, stock_code: str, current_price: int,
                                           baseline_decision_price: int, 
                                           baseline_low_price: int,
                                           baseline_high_price: int) -> Optional[Dict]:
        """
        시가 기록 및 신뢰구간 분석
        
        Args:
            stock_code: 종목코드
            current_price: 현재가 (첫 입력 시 시가가 됨)
            baseline_decision_price: 예측 기준가
            baseline_low_price: 예측 최저가
            baseline_high_price: 예측 최고가
            
        Returns:
            Dict: 신뢰구간 분석 결과
        """
        if not self.price_confidence_service:
            logger.warning("PriceConfidenceService가 초기화되지 않았습니다.")
            return None
        
        try:
            # 시가 기록 및 신뢰구간 분석
            open_price_data = await self.price_confidence_service.record_open_price(
                stock_code, current_price, baseline_decision_price,
                baseline_low_price, baseline_high_price
            )
            
            if not open_price_data:
                return None
            
            # 분석 결과 반환
            result = {
                'stock_code': stock_code,
                'open_price': open_price_data.open_price,
                'baseline_decision_price': open_price_data.baseline_decision_price,
                'confidence_score': open_price_data.confidence_score,
                'confidence_level': open_price_data.confidence_level.value,
                'position_in_range': open_price_data.position_in_range,
                'analysis_summary': f"신뢰도 {open_price_data.confidence_level.value} ({open_price_data.confidence_score:.1f}점)",
                'is_first_record': True  # 첫 기록임을 표시
            }
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 시가 신뢰구간 분석 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None
    
    async def get_existing_confidence_data(self, stock_code: str) -> Optional[Dict]:
        """
        기존 신뢰구간 데이터 조회 (이미 시가가 기록된 경우)
        """
        if not self.price_confidence_service:
            return None
        
        try:
            summary = await self.price_confidence_service.get_confidence_summary(stock_code)
            if summary:
                summary['is_first_record'] = False  # 기존 데이터임을 표시
            return summary
            
        except Exception as e:
            logger.error(f"❌ 기존 신뢰구간 데이터 조회 실패 - 종목: {stock_code}, 오류: {str(e)}")
            return None


# ===== TradingIntegration 클래스 수정 =====

class TradingIntegration:
    
    def __init__(self, kiwoom_module, baseline_cache, redis_db=None):
        self.kiwoom_module = kiwoom_module
        # Redis 연결을 SmartTradingStrategy에 전달
        self.trading_strategy = SmartTradingStrategy(kiwoom_module, redis_db)
        self.BC = baseline_cache
        
        # 기존 코드...
        self.last_trade_time = {}
        self.min_trade_interval = 600
    
    async def process_trading_signals(self, 
                                      stock_code: str, 
                                      analysis: dict, 
                                      qty: int, 
                                      current_price: int,
                                      tracking_data: Optional[Dict] = None):
        """매매 신호 처리 - 시가 신뢰구간 분석 추가"""
        try:
            # 🆕 시가 신뢰구간 분석 (오늘 첫 번째 가격인 경우)
            confidence_data = await self._analyze_price_confidence(stock_code, current_price)
            
            signal = await self.check_trading_opportunity(stock_code, analysis)
            if signal and signal.strength >= 70:
                success = await self.trading_strategy.execute_trading_signal(
                    stock_code, signal, qty, current_price, tracking_data
                )
                if success:
                    self._record_trade(stock_code)

        except Exception as e:
            logger.error(f"[{stock_code}] 매매 신호 처리 오류: {str(e)}")
    
    async def _analyze_price_confidence(self, stock_code: str, current_price: int) -> Optional[Dict]:
        """시가 신뢰구간 분석"""
        try:
            # 베이스라인 정보 조회
            baseline_cache = self.BC.get_price_info(stock_code, 0)
            if not baseline_cache:
                return None
            
            baseline_decision_price = baseline_cache.get("decision_price")
            baseline_low_price = baseline_cache.get("low_price")
            baseline_high_price = baseline_cache.get("high_price")
            
            if not all([baseline_decision_price, baseline_low_price, baseline_high_price]):
                return None
            
            # 시가 신뢰구간 분석 수행
            confidence_data = await self.trading_strategy.analyze_open_price_confidence(
                stock_code, current_price, baseline_decision_price,
                baseline_low_price, baseline_high_price
            )
            
            # 결과 로깅
            if confidence_data:
                if confidence_data.get('is_first_record'):
                    logger.info(f"🌅 [{stock_code}] 시가 분석 완료 - {confidence_data['analysis_summary']}")
                else:
                    logger.debug(f"📊 [{stock_code}] 기존 신뢰구간 데이터 확인됨")
            
            return confidence_data
            
        except Exception as e:
            logger.error(f"❌ [{stock_code}] 시가 신뢰구간 분석 오류: {str(e)}")
            return None
    
    # 기존 메서드들은 그대로 유지...