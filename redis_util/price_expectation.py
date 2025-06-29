import json
import time
import numpy as np
import logging
from typing import Dict, List, Optional
from datetime import datetime
import asyncio
from dependency_injector.wiring import inject, Provide
from container.redis_container import Redis_Container
from db.redis_db import RedisDB

logger = logging.getLogger(__name__)

# 다음날 주식가격 예상 범위 산출 클래스
class PriceExpectation:
    @inject
    def __init__(self, kiwoom_module, redis_db: RedisDB = Provide[Redis_Container.redis_db]):
        self.redis_db = redis_db
        self.kiwoom_module = kiwoom_module
        self.REDIS_KEY_PREFIX = "PE"
        self.EXPIRE_TIME = 60 * 60 * 12  # 12 시간

    def _get_redis_key(self, stock_code: str) -> str:
        """Redis 키 생성 (예측 결과용)"""
        return f"redis:{self.REDIS_KEY_PREFIX}:{stock_code}"

    async def _fetch_daily_chart_data(self, code: str, days: int = 40) -> List[Dict]:
        """키움 API에서 직접 일봉 데이터 조회 및 가공"""
        try:
            # 키움 API에서 일봉 차트 데이터 조회
            res = await self.kiwoom_module.get_daily_chart(code=code)
            
            # return_code 확인
            return_code = res.get('return_code', -1)
            if return_code != 0:
                logger.error(f"일봉 차트 조회 실패 - 종목: {code}, 코드: {return_code}, 메시지: {res.get('return_msg', '')}")
                return []
            
            # 차트 데이터 추출
            chart_data = res.get('stk_dt_pole_chart_qry', [])
            if not chart_data:
                logger.warning(f"일봉 차트 데이터가 없습니다 - 종목: {code}")
                return []
            
            # 최신 N개 데이터만 처리하여 가공된 데이터 반환
            latest_data = chart_data[:days] if len(chart_data) > days else chart_data
            
            processed_data = []
            for daily_data in latest_data:
                try:
                    # 필요한 필드만 추출하여 가공
                    filtered_data = {
                        'stk_cd': code,
                        'cur_prc': daily_data.get('cur_prc', ''),         # 현재가
                        'trde_qty': daily_data.get('trde_qty', ''),       # 거래량
                        'trde_prica': daily_data.get('trde_prica', ''),   # 거래대금
                        'dt': daily_data.get('dt', ''),                   # 일자
                        'open_pric': daily_data.get('open_pric', ''),     # 시가
                        'high_pric': daily_data.get('high_pric', ''),     # 고가
                        'low_pric': daily_data.get('low_pric', ''),       # 저가
                    }
                    
                    # 데이터 유효성 검사
                    date_str = daily_data.get('dt', '')
                    if not date_str or len(date_str) != 8:
                        logger.warning(f"잘못된 일자 형식: {date_str}, 종목: {code}")
                        continue
                    
                    processed_data.append(filtered_data)
                    
                except Exception as e:
                    logger.error(f"개별 일봉 데이터 처리 오류 - 종목: {code}, 데이터: {daily_data}, 오류: {str(e)}")
                    continue
            
            logger.info(f"📊 일봉 데이터 조회 완료 - 종목: {code}, 데이터 개수: {len(processed_data)}")
            return processed_data
            
        except Exception as e:
            logger.error(f"❌ 일봉 차트 데이터 조회 중 오류 - 종목: {code}, 오류: {str(e)}")
            return []

    def _calculate_all_predictions(self, data_list: List[Dict]) -> List[Dict]:
        """모든 예측 방법을 실행하여 결과 리스트 반환"""
        predictions = []
        
        # 1. 변동성 기반 예측
        vol_pred = self._calculate_volatility_based_range(data_list)
        if vol_pred:
            predictions.append(vol_pred)
            logger.debug("변동성 기반 예측 완료")
        
        # 2. 지지/저항선 기반 예측
        sr_pred = self._calculate_support_resistance_range(data_list)
        if sr_pred:
            predictions.append(sr_pred)
            logger.debug("지지/저항선 기반 예측 완료")
        
        # 3. 거래량 조정 예측
        vol_adj_pred = self._calculate_volume_adjusted_range(data_list)
        if vol_adj_pred:
            predictions.append(vol_adj_pred)
            logger.debug("거래량 조정 예측 완료")
        
        # 4. 추세 모멘텀 예측
        trend_pred = self._calculate_trend_momentum_range(data_list)
        if trend_pred:
            predictions.append(trend_pred)
            logger.debug("추세 모멘텀 예측 완료")
        
        return predictions

    # 변동성 기반 가격 범위 예측
    def _calculate_volatility_based_range(self, data_list: List[Dict], days: int = 20) -> Optional[Dict]:
        """변동성 기반 가격 범위 예측"""
        try:
            if len(data_list) < 2:
                return None
            
            # 최근 N일 데이터 추출 (날짜순 정렬)
            recent_data = sorted(data_list, key=lambda x: x.get('dt', ''))[-days:]
            
            # 일일 수익률 계산
            returns = []
            for i in range(1, len(recent_data)):
                try:
                    prev_price = float(recent_data[i-1].get('cur_prc', 0))
                    curr_price = float(recent_data[i].get('cur_prc', 0))
                    
                    if prev_price > 0:
                        daily_return = (curr_price - prev_price) / prev_price
                        returns.append(daily_return)
                except (ValueError, ZeroDivisionError):
                    continue
            
            if not returns:
                return None
            
            # 변동성 계산
            volatility = np.std(returns)
            current_price = float(recent_data[-1].get('cur_prc', 0))
            
            if current_price <= 0:
                return None
            
            # 다음날 예상 범위 (±2σ)
            price_change = current_price * volatility * 2
            
            return {
                'method': 'volatility_based',
                'predicted_low': max(0, current_price - price_change),
                'predicted_high': current_price + price_change,
                'current_price': current_price,
                'volatility': volatility,
                'confidence': 0.95  # 2σ 기준 95% 신뢰구간
            }
            
        except Exception as e:
            logger.error(f"변동성 기반 예측 계산 오류: {str(e)}")
            return None

    # 지지/저항선 기반 가격 범위 예측
    def _calculate_support_resistance_range(self, data_list: List[Dict], days: int = 20) -> Optional[Dict]:
        """지지/저항선 기반 가격 범위 예측"""
        try:
            if len(data_list) < days:
                return None
                
            # 최근 N일 데이터 추출
            recent_data = sorted(data_list, key=lambda x: x.get('dt', ''))[-days:]
            
            highs = []
            lows = []
            
            for data in recent_data:
                try:
                    high = float(data.get('high_pric', 0))
                    low = float(data.get('low_pric', 0))
                    
                    if high > 0 and low > 0:
                        highs.append(high)
                        lows.append(low)
                except ValueError:
                    continue
            
            if not highs or not lows:
                return None
            
            # 지지/저항선 계산
            resistance_level = np.percentile(highs, 80)  # 상위 20% 고점
            support_level = np.percentile(lows, 20)       # 하위 20% 저점
            
            current_price = float(recent_data[-1].get('cur_prc', 0))
            
            if current_price <= 0:
                return None
            
            return {
                'method': 'support_resistance',
                'predicted_low': max(support_level, current_price * 0.9),
                'predicted_high': min(resistance_level, current_price * 1.1),
                'support_level': support_level,
                'resistance_level': resistance_level,
                'current_price': current_price
            }
            
        except Exception as e:
            logger.error(f"지지/저항선 기반 예측 계산 오류: {str(e)}")
            return None

    # 거래량 조정 가격 범위 예측
    def _calculate_volume_adjusted_range(self, data_list: List[Dict], days: int = 10) -> Optional[Dict]:
        try:
            if len(data_list) < days + 1:
                return None
                
            # 최근 N일 데이터 추출
            recent_data = sorted(data_list, key=lambda x: x.get('dt', ''))[-days-1:]
            
            volume_price_changes = []
            volumes = []
            
            for i in range(1, len(recent_data)):
                try:
                    volume = float(recent_data[i].get('trde_qty', 0))
                    prev_price = float(recent_data[i-1].get('cur_prc', 0))
                    curr_price = float(recent_data[i].get('cur_prc', 0))
                    
                    if prev_price > 0 and volume > 0:
                        price_change_rate = abs(curr_price - prev_price) / prev_price
                        volume_price_changes.append(price_change_rate)
                        volumes.append(volume)
                        
                except (ValueError, ZeroDivisionError):
                    continue
            
            if not volume_price_changes or not volumes:
                return None
            
            # 현재 거래량과 평균 거래량 비교
            current_volume = float(recent_data[-1].get('trde_qty', 0))
            avg_volume = np.mean(volumes)
            
            if avg_volume <= 0:
                return None
            
            # 거래량 배수 계산
            volume_factor = min(current_volume / avg_volume, 3.0)  # 최대 3배로 제한
            base_volatility = np.mean(volume_price_changes)
            
            # 거래량 조정 변동성
            adjusted_volatility = base_volatility * volume_factor
            current_price = float(recent_data[-1].get('cur_prc', 0))
            
            if current_price <= 0:
                return None
            
            # 예상 가격 범위
            price_range = current_price * adjusted_volatility
            
            return {
                'method': 'volume_adjusted',
                'predicted_low': max(0, current_price - price_range),
                'predicted_high': current_price + price_range,
                'current_price': current_price,
                'volume_factor': volume_factor,
                'base_volatility': base_volatility,
                'adjusted_volatility': adjusted_volatility
            }
            
        except Exception as e:
            logger.error(f"거래량 조정 예측 계산 오류: {str(e)}")
            return None

    # 추세 모멘텀 기반 가격 범위 예측
    def _calculate_trend_momentum_range(self, data_list: List[Dict], days: int = 5) -> Optional[Dict]:
        """추세 모멘텀 기반 가격 범위 예측"""
        try:
            if len(data_list) < days + 1:
                return None
                
            # 최근 N일 데이터 추출
            recent_data = sorted(data_list, key=lambda x: x.get('dt', ''))[-days-1:]
            
            prices = []
            for data in recent_data:
                try:
                    price = float(data.get('cur_prc', 0))
                    if price > 0:
                        prices.append(price)
                except ValueError:
                    continue
            
            if len(prices) < 2:
                return None
            
            # 추세 계산 (선형 회귀 기울기)
            x = np.arange(len(prices))
            z = np.polyfit(x, prices, 1)
            trend_slope = z[0]  # 기울기
            
            current_price = prices[-1]
            
            # 모멘텀 계산 (최근 3일 평균 변화율)
            momentum_days = min(3, len(prices) - 1)
            momentum_changes = []
            
            for i in range(len(prices) - momentum_days, len(prices)):
                if i > 0:
                    change_rate = (prices[i] - prices[i-1]) / prices[i-1]
                    momentum_changes.append(change_rate)
            
            if not momentum_changes:
                return None
            
            avg_momentum = np.mean(momentum_changes)
            
            # 다음날 예상 가격 (추세 + 모멘텀)
            next_day_base = current_price + trend_slope
            momentum_adjustment = current_price * avg_momentum
            
            # 예상 범위 계산
            volatility = np.std([abs(change) for change in momentum_changes])
            range_size = current_price * volatility
            
            predicted_center = next_day_base + momentum_adjustment
            
            return {
                'method': 'trend_momentum',
                'predicted_low': max(0, predicted_center - range_size),
                'predicted_high': predicted_center + range_size,
                'current_price': current_price,
                'trend_slope': trend_slope,
                'momentum': avg_momentum,
                'predicted_center': predicted_center
            }
            
        except Exception as e:
            logger.error(f"추세 모멘텀 예측 계산 오류: {str(e)}")
            return None

    # 여러 예측 방법의 결과를 종합
    def combine_predictions(self, predictions: List[Dict]) -> Dict:
        """여러 예측 방법의 결과를 종합"""
        try:
            valid_predictions = [p for p in predictions if p and 'predicted_high' in p and 'predicted_low' in p]
            
            if not valid_predictions:
                return {}
            
            # 가중치 설정
            weights = {
                'volatility_based': 0.3,
                'support_resistance': 0.25,
                'volume_adjusted': 0.25,
                'trend_momentum': 0.2
            }
            
            weighted_high = 0
            weighted_low = 0
            total_weight = 0
            
            prediction_details = {}
            
            for pred in valid_predictions:
                method = pred.get('method', 'unknown')
                weight = weights.get(method, 0.1)
                
                weighted_high += pred['predicted_high'] * weight
                weighted_low += pred['predicted_low'] * weight
                total_weight += weight
                
                prediction_details[method] = {
                    'high': pred['predicted_high'],
                    'low': pred['predicted_low'],
                    'weight': weight
                }
            
            if total_weight == 0:
                return {}
            
            # 정규화
            final_high = weighted_high / total_weight
            final_low = weighted_low / total_weight
            
            # 현재가 기준 신뢰도 계산
            current_prices = [p.get('current_price', 0) for p in valid_predictions if p.get('current_price', 0) > 0]
            current_price = np.mean(current_prices) if current_prices else 0
            
            if current_price > 0:
                price_range_pct = ((final_high - final_low) / current_price) * 100
                confidence_score = max(0, min(100, 100 - (price_range_pct * 2)))  # 범위가 클수록 신뢰도 낮음
            else:
                confidence_score = 0
            
            return {
                'final_predicted_high': round(final_high, 2),
                'final_predicted_low': round(final_low, 2),
                'predicted_range_pct': round(price_range_pct, 2) if current_price > 0 else 0,
                'confidence_score': round(confidence_score, 1),
                'current_price': round(current_price, 2),
                'prediction_methods_used': len(valid_predictions),
                'method_details': prediction_details,
                'prediction_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"예측 결과 종합 오류: {str(e)}")
            return {}

    # 예측 결과를 Redis에 저장 (최종 결과만)
    async def save_prediction_to_redis(self, code: str, prediction_data: Dict) -> bool:
        """예측 결과를 Redis에 저장"""
        try:
            redis_key = f"redis:PE:{code}"
            
            # 예측 데이터에 메타정보 추가
            prediction_data.update({
                'stk_cd': code,
                'prediction_time': time.time(),
                'prediction_date': datetime.now().strftime('%Y%m%d'),
                'type': 'PRICE_PREDICTION'
            })
            
            # JSON으로 변환하여 저장
            value = json.dumps(prediction_data, ensure_ascii=False)
            score = int(datetime.now().strftime('%Y%m%d'))  # 오늘 날짜를 score로 사용
            
            await self.redis_db.zadd(redis_key, {value: score})
            
            # 만료 시간 설정 (7일)
            await self.redis_db.expire(redis_key, self.EXPIRE_TIME)
            
            logger.info(f"✅ 예측 결과 Redis 저장 완료 - 종목: {code}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 가격 예측 데이터 저장 오류 - 종목: {code}, 오류: {str(e)}")
            return False

    # 다음날 주식가격 예상 범위 산출 (메인 메서드)
    async def predict_tomorrow_price_range(self, code: str, save_to_redis: bool = True) -> Dict:
        """다음날 주식가격 예상 범위 산출 메인 메서드"""
        try:
            logger.info(f"🚀 가격 예측 시작 - 종목: {code}")
            
            # 1. 키움 API에서 직접 일봉 데이터 조회
            daily_data = await self._fetch_daily_chart_data(code, days=40)
            
            if not daily_data:
                logger.warning(f"일봉 데이터 없음 - 종목: {code}")
                return {
                    'error': 'NO_DATA',
                    'message': f'종목 {code}의 일봉 데이터를 찾을 수 없습니다.'
                }
            
            if len(daily_data) < 5:
                logger.warning(f"데이터 부족 - 종목: {code}, 데이터 개수: {len(daily_data)}")
                return {
                    'error': 'INSUFFICIENT_DATA',
                    'message': f'종목 {code}의 데이터가 부족합니다. (최소 5일 필요)'
                }
            
            # 2. 메모리에서 모든 예측 방법 실행
            predictions = self._calculate_all_predictions(daily_data)
            
            if not predictions:
                logger.error(f"모든 예측 방법 실패 - 종목: {code}")
                return {
                    'error': 'PREDICTION_FAILED',
                    'message': f'종목 {code}의 가격 예측에 실패했습니다.'
                }
            
            # 3. 예측 결과 종합
            final_prediction = self.combine_predictions(predictions)
            if not final_prediction:
                logger.error(f"예측 결과 종합 실패 - 종목: {code}")
                return {
                    'error': 'COMBINE_FAILED',
                    'message': f'종목 {code}의 예측 결과 종합에 실패했습니다.'
                }
            
            # 4. 결과에 종목 코드 및 메타데이터 추가
            final_prediction.update({
                'stock_code': code,
                'data_count': len(daily_data),
                'processing_time': time.time()
            })
            
            # 5. 최종 예측 결과만 Redis에 저장 (옵션)
            if save_to_redis:
                await self.save_prediction_to_redis(code, final_prediction.copy())
            
            logger.info(f"✅ 가격 예측 완료 - 종목: {code}, 신뢰도: {final_prediction.get('confidence_score', 0)}%")
            return final_prediction
            
        except Exception as e:
            logger.error(f"❌ 가격 예측 오류 - 종목: {code}, 오류: {str(e)}")
            return {
                'error': 'UNEXPECTED_ERROR',
                'message': f'종목 {code}의 가격 예측 중 예상치 못한 오류가 발생했습니다.',
                'detail': str(e)
            }

    # Redis에서 저장된 예측 결과 조회
    async def get_prediction_from_redis(self, code: str, days: int = 7) -> List[Dict]:
        """Redis에서 저장된 예측 결과 조회"""
        try:
            redis_key = f"redis:PE:{code}"
            
            # 최근 예측 데이터 조회
            raw_data = await self.redis_db.zrevrange(redis_key, 0, days - 1)
            
            results = []
            for item in raw_data:
                try:
                    parsed = json.loads(item)
                    if isinstance(parsed, dict):
                        results.append(parsed)
                except json.JSONDecodeError as e:
                    logger.error(f"예측 데이터 JSON 파싱 실패: {e}")
                    continue
            
            logger.info(f"📊 Redis에서 예측 데이터 조회 - 종목: {code}, 조회된 데이터: {len(results)}개")
            return results
            
        except Exception as e:
            logger.error(f"Redis 예측 데이터 조회 오류 - 종목: {code}, 오류: {str(e)}")
            return []

    # 여러 종목의 가격 예측을 일괄 처리 (개선된 버전)
    async def batch_predict_multiple_stocks(self, stock_codes: List[str], 
                                          save_to_redis: bool = True, 
                                          max_concurrent: int = 5) -> Dict[str, Dict]:
        """여러 종목의 가격 예측을 일괄 처리"""
        results = {}
        
        logger.info(f"🚀 일괄 가격 예측 시작 - 대상 종목: {len(stock_codes)}개, 동시 처리: {max_concurrent}개")
        start_time = time.time()
        
        # 동시 처리 수 제한을 위한 세마포어
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def predict_single_stock(code: str) -> tuple[str, Dict]:
            async with semaphore:
                try:
                    result = await self.predict_tomorrow_price_range(code, save_to_redis)
                    return code, result
                except Exception as e:
                    logger.error(f"종목 {code} 예측 중 오류: {str(e)}")
                    return code, {
                        'error': 'TASK_FAILED',
                        'message': f'종목 {code} 예측 태스크 실행 실패',
                        'detail': str(e)
                    }
        
        # 모든 종목에 대한 태스크 생성 및 실행
        tasks = [predict_single_stock(code) for code in stock_codes]
        completed_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 결과 정리
        success_count = 0
        error_count = 0
        
        for result in completed_results:
            if isinstance(result, Exception):
                error_count += 1
                logger.error(f"예측 태스크 실행 중 예외 발생: {str(result)}")
                continue
                
            code, prediction_result = result
            results[code] = prediction_result
            
            if 'error' not in prediction_result:
                success_count += 1
            else:
                error_count += 1
        
        elapsed_time = time.time() - start_time
        
        logger.info(f"✅ 일괄 가격 예측 완료 - 성공: {success_count}/{len(stock_codes)}개, "
                   f"실패: {error_count}개, 소요시간: {elapsed_time:.2f}초")
        
        return {
            'predictions': results,
            'summary': {
                'total_stocks': len(stock_codes),
                'success_count': success_count,
                'error_count': error_count,
                'processing_time': round(elapsed_time, 2),
                'success_rate': round((success_count / len(stock_codes)) * 100, 1) if stock_codes else 0
            }
        }