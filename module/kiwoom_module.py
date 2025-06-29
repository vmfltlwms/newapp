from datetime import datetime 
from dependency_injector.wiring import inject, Provide
import logging
from container.token_container import Token_Container
from module.token_module import TokenModule
from config import settings
import asyncio
import requests
from typing import Callable, Any, Dict
import time

logger = logging.getLogger(__name__)

class KiwoomModule:
    """키움 API와 통신하는 클라이언트 - 큐 기반 API 호출 제어"""
    
    # 클래스 레벨에서 공유할 큐와 프로세서
    _shared_queue = None
    _processor_task = None
    _is_processor_running = False
    _api_call_interval = 0.3  # API 호출 간격 (초)
    
    @inject
    def __init__(self, 
                token_module: TokenModule = Provide[Token_Container.token_module]):
        self.host = settings.HOST
        self.app_key = settings.KIWOOM_APP_KEY
        self.sec_key = settings.KIWOOM_SECRET_KEY
        self.token = None
        self.token_module = token_module
        self.logger = logging.getLogger(__name__)
        
        # 클래스 레벨 큐 초기화
        if KiwoomModule._shared_queue is None:
            KiwoomModule._shared_queue = asyncio.Queue()
        
        # 프로세서 시작
        if not KiwoomModule._is_processor_running:
            asyncio.create_task(self._start_api_processor())

    @classmethod
    async def _start_api_processor(cls):
        """API 호출 프로세서 시작"""
        if cls._is_processor_running:
            return
            
        cls._is_processor_running = True
        cls._processor_task = asyncio.create_task(cls._api_call_processor())
        logger.info("🚀 Kiwoom API 호출 프로세서 시작")

    @classmethod
    async def _api_call_processor(cls):
        """API 호출을 순차적으로 처리하는 프로세서"""
        while cls._is_processor_running:
            try:
                # 큐에서 API 호출 작업 가져오기 (타임아웃 5초)
                api_call_info = await asyncio.wait_for(
                    cls._shared_queue.get(), timeout=5.0
                )
                
                if api_call_info is None:  # 종료 신호
                    logger.info("🛑 Kiwoom API 프로세서 종료 신호 수신")
                    break
                
                func, args, kwargs, result_future, call_time = api_call_info
                
                # API 호출 실행
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-4]
                logger.debug(f"[{timestamp}] API 호출 시작: {func.__name__}")
                
                try:
                    # 실제 API 호출 실행
                    result = await func(*args, **kwargs)
                    result_future.set_result(result)
                    
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-4]
                    logger.debug(f"[{timestamp}] API 호출 완료: {func.__name__}")
                    
                except Exception as e:
                    result_future.set_exception(e)
                    logger.error(f"API 호출 오류 {func.__name__}: {str(e)}")
                
                # 작업 완료 표시
                cls._shared_queue.task_done()
                
                # 설정된 간격만큼 대기
                await asyncio.sleep(cls._api_call_interval)
                
            except asyncio.TimeoutError:
                # 큐가 비어있으면 계속 대기
                continue
            except Exception as e:
                logger.error(f"API 프로세서 오류: {str(e)}")
                continue

    async def _queue_api_call(self, func: Callable, *args, **kwargs) -> Any:
        """API 호출을 큐에 추가하고 결과를 기다림"""
        # 결과를 받을 Future 객체 생성
        result_future = asyncio.Future()
        call_time = time.time()
        
        # 큐에 API 호출 정보 추가
        await KiwoomModule._shared_queue.put((func, args, kwargs, result_future, call_time))
        
        # 큐 크기 로깅
        queue_size = KiwoomModule._shared_queue.qsize()
        logger.debug(f"API 호출 큐에 추가: {func.__name__} (큐 크기: {queue_size})")
        
        # 결과 기다림
        return await result_future

    @classmethod
    async def shutdown_processor(cls):
        """API 프로세서 종료"""
        if cls._is_processor_running:
            # 종료 신호를 큐에 추가
            await cls._shared_queue.put(None)
            
            # 프로세서 태스크 완료 대기
            if cls._processor_task:
                await cls._processor_task
            
            cls._is_processor_running = False
            logger.info("🛑 Kiwoom API 프로세서 종료 완료")

    @classmethod
    def set_api_interval(cls, interval: float):
        """API 호출 간격 설정"""
        cls._api_call_interval = interval
        logger.info(f"API 호출 간격이 {interval}초로 설정되었습니다")

    @classmethod
    def get_queue_size(cls) -> int:
        """현재 큐 크기 반환"""
        return cls._shared_queue.qsize() if cls._shared_queue else 0

    async def initialize(self):
        """비동기 초기화 메서드: 토큰 요청 재시도 포함"""
        max_retries = 3
        retry_delay = 3  # 초

        for attempt in range(1, max_retries + 1):
            try:
                response_data = self.token_module.get_token_info()

                if response_data.get("return_code") == 0 and "token" in response_data:
                    self.token = response_data["token"]
                    logging.info("✅ kiwoom_module 연결 초기화 완료")
                    return

                # 실패한 경우 로그 출력
                logging.warning(
                    f"❌ 토큰 요청 kiw 실패 (시도 {attempt}): {response_data.get('return_msg', '알 수 없는 오류')}"
                )

            except Exception as e:
                logging.exception(f"❌ 토큰 요청 중 예외 발생 (시도 {attempt}): {e}")

            if attempt < max_retries:
                await asyncio.sleep(retry_delay)

        # 여기까지 왔다는 것은 모든 시도 실패
        logging.error("🚫 kiwoom_module 초기화 실패: 최대 재시도 초과")
        raise RuntimeError("kiwoom_module 초기화 실패: 토큰을 가져오지 못했습니다.")

    async def shutdown(self):
        """키움 모듈 종료 및 리소스 정리"""
        try:
            # 토큰 정리 또는 API 연결 종료 작업
            self.token = None
            logging.info("🛑 키움 모듈 종료 완료")
        except Exception as e:
            logging.error(f"키움 모듈 종료 중 오류 발생: {str(e)}")

    # =================================================================
    # 내부 API 호출 메서드들 (큐를 거치지 않는 실제 구현)
    # =================================================================
    
    async def _get_stock_info_internal(self, code: str) -> dict:
        """내부 주식 정보 조회"""
        url = f"{self.host}/api/dostk/stkinfo"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": "N",
            "next-key": "",
            "api-id": "ka10001"
        }
        
        data = {"stk_cd": code}
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"응답 내용: {response.text}")
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"주식 정보 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_tick_chart_internal(self, code: str, tick_scope: str = "1", 
                                     price_type: str = "1", cont_yn: str = "N", 
                                     next_key: str = "") -> dict:
        """내부 틱차트 조회"""
        url = f"{self.host}/api/dostk/chart"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10079"
        }
        
        data = {
            "stk_cd": code,
            "tic_scope": tick_scope,
            "upd_stkpc_tp": price_type
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"틱차트 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"틱차트 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"틱차트 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_minute_chart_internal(self, code: str, tic_scope: str = "1", 
                                       price_type: str = "1", cont_yn: str = "N", 
                                       next_key: str = "") -> dict:
        """내부 분봉차트 조회"""
        url = f"{self.host}/api/dostk/chart"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10080"
        }
        
        data = {
            "stk_cd": code,
            "tic_scope": tic_scope,
            "upd_stkpc_tp": price_type
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"분봉차트 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"분봉차트 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"분봉차트 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_daily_chart_internal(self, code: str, base_dt: str = "", 
                                      price_type: str = "1", cont_yn: str = "N", 
                                      next_key: str = "") -> dict:
        """내부 일봉차트 조회"""
        url = f"{self.host}/api/dostk/chart"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10081"
        }
        
        current_date = datetime.now()
        if base_dt == '':
            base_dt = current_date.strftime("%Y%m%d")
            
        data = {
            "stk_cd": code,
            "base_dt": base_dt,
            "upd_stkpc_tp": price_type
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"일봉차트 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"일봉차트 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"일봉차트 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_weekly_chart_internal(self, code: str, base_dt: str = "", 
                                       price_type: str = "1", cont_yn: str = "N", 
                                       next_key: str = "") -> dict:
        """내부 주봉차트 조회"""
        url = f"{self.host}/api/dostk/chart"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10082"
        }
        
        current_date = datetime.now()
        if base_dt == '':
            base_dt = current_date.strftime("%Y%m%d")
            
        data = {
            "stk_cd": code,
            "base_dt": base_dt,
            "upd_stkpc_tp": price_type
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"주봉차트 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"주봉차트 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"주봉차트 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_monthly_chart_internal(self, code: str, base_dt: str = "", 
                                        price_type: str = "1", cont_yn: str = "N", 
                                        next_key: str = "") -> dict:
        """내부 월봉차트 조회"""
        url = f"{self.host}/api/dostk/chart"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10083"
        }
        
        current_date = datetime.now()
        if base_dt == '':
            base_dt = current_date.strftime("%Y%m%d")
            
        data = {
            "stk_cd": code,
            "base_dt": base_dt,
            "upd_stkpc_tp": price_type
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"월봉차트 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"월봉차트 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"월봉차트 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_yearly_chart_internal(self, code: str, base_dt: str = "", 
                                       price_type: str = "1", cont_yn: str = "N", 
                                       next_key: str = "") -> dict:
        """내부 년봉차트 조회"""
        url = f"{self.host}/api/dostk/chart"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10094"
        }
        
        current_date = datetime.now()
        if base_dt == '':
            base_dt = current_date.strftime("%Y%m%d")
            
        data = {
            "stk_cd": code,
            "base_dt": base_dt,
            "upd_stkpc_tp": price_type
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"년봉차트 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"년봉차트 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"년봉차트 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    # 주식 주문 관련 내부 메서드들
    async def _order_stock_buy_internal(self, dmst_stex_tp: str, stk_cd: str, 
                                      ord_qty: str, ord_uv: str = "", 
                                      trde_tp: str = "3", cond_uv: str = "",
                                      cont_yn: str = "N", next_key: str = "") -> dict:
        """내부 매수주문"""
        url = f"{self.host}/api/dostk/ordr"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "kt10000"
        }
        
        data = {
            "dmst_stex_tp": dmst_stex_tp,
            "stk_cd": stk_cd,
            "ord_qty": ord_qty,
            "ord_uv": ord_uv,
            "trde_tp": trde_tp,
            "cond_uv": cond_uv
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"주식 매수주문 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"주식 매수주문 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            logger.info(f"주식 매수주문 성공: {stk_cd}, {ord_qty}주, 주문번호: {result.get('ord_no', '알 수 없음')}")
            
            return result
        except Exception as e:
            logger.error(f"주식 매수주문 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _order_stock_sell_internal(self, dmst_stex_tp: str, stk_cd: str, 
                                       ord_qty: str, ord_uv: str = "", 
                                       trde_tp: str = "0", cond_uv: str = "",
                                       cont_yn: str = "N", next_key: str = "") -> dict:
        """내부 매도주문"""
        url = f"{self.host}/api/dostk/ordr"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "kt10001"
        }
        
        data = {
            "dmst_stex_tp": dmst_stex_tp,
            "stk_cd": stk_cd,
            "ord_qty": ord_qty,
            "ord_uv": ord_uv,
            "trde_tp": trde_tp,
            "cond_uv": cond_uv
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"주식 매도주문 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"주식 매도주문 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            logger.info(f"주식 매도주문 성공: {stk_cd}, {ord_qty}주, 주문번호: {result.get('ord_no', '알 수 없음')}")
            
            return result
        except Exception as e:
            logger.error(f"주식 매도주문 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _order_stock_modify_internal(self, dmst_stex_tp: str, orig_ord_no: str, 
                                         stk_cd: str, mdfy_qty: str, mdfy_uv: str, 
                                         mdfy_cond_uv: str = "", cont_yn: str = "N",
                                         next_key: str = "") -> dict:
        """내부 정정주문"""
        url = f"{self.host}/api/dostk/ordr"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "kt10002"
        }
        
        data = {
            "dmst_stex_tp": dmst_stex_tp,
            "orig_ord_no": orig_ord_no,
            "stk_cd": stk_cd,
            "mdfy_qty": mdfy_qty,
            "mdfy_uv": mdfy_uv,
            "mdfy_cond_uv": mdfy_cond_uv
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"주식 정정주문 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"주식 정정주문 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            logger.info(f"주식 정정주문 성공: {stk_cd}, 원주문번호: {orig_ord_no}, 정정수량: {mdfy_qty}, 정정단가: {mdfy_uv}")
            
            return result
        except Exception as e:
            logger.error(f"주식 정정주문 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _order_stock_cancel_internal(self, dmst_stex_tp: str, orig_ord_no: str, 
                                         stk_cd: str, cncl_qty: str,
                                         cont_yn: str = "N", next_key: str = "") -> dict:
        """내부 취소주문"""
        url = f"{self.host}/api/dostk/ordr"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "kt10003"
        }
        
        data = {
            "dmst_stex_tp": dmst_stex_tp,
            "orig_ord_no": orig_ord_no,
            "stk_cd": stk_cd,
            "cncl_qty": cncl_qty
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"주식 취소주문 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"주식 취소주문 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            logger.info(f"주식 취소주문 성공: {stk_cd}, 원주문번호: {orig_ord_no}, 취소수량: {cncl_qty}")
            
            return result
        except Exception as e:
            logger.error(f"주식 취소주문 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    # 계좌 정보 관련 내부 메서드들
    async def _get_deposit_detail_internal(self, query_type: str = "2", 
                                         cont_yn: str = "N", next_key: str = "") -> dict:
        """내부 예수금상세현황 조회"""
        url = f"{self.host}/api/dostk/acnt"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "kt00001"
        }
        
        data = {"qry_tp": query_type}
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"예수금상세현황 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"예수금상세현황 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')

            return result
        except Exception as e:
            logger.error(f"예수금상세현황 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_order_detail_internal(self, order_date: str, query_type: str = "1", 
                                       stock_bond_type: str = "1", sell_buy_type: str = "0", 
                                       stock_code: str = "", from_order_no: str = "", 
                                       market_type: str = "KRX", cont_yn: str = "N", 
                                       next_key: str = "") -> dict:
        """내부 주문체결내역 상세 조회"""
        url = f"{self.host}/api/dostk/acnt"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "kt00007"
        }
        
        current_date = datetime.now()
        if order_date == '':
            order_date = current_date.strftime("%Y%m%d")
        
        data = {
            "ord_dt": order_date,
            "qry_tp": query_type,
            "stk_bond_tp": stock_bond_type,
            "sell_tp": sell_buy_type,
            "stk_cd": stock_code,
            "fr_ord_no": from_order_no,
            "dmst_stex_tp": market_type
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"주문체결내역 상세 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"주문체결내역 상세 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"주문체결내역 상세 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_daily_trading_log_internal(self, base_date: str = "", ottks_tp: str = "1", 
                                            ch_crd_tp: str = "0", cont_yn: str = "N", 
                                            next_key: str = "") -> dict:
        """내부 당일매매일지 조회"""
        url = f"{self.host}/api/dostk/acnt"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10170"
        }
        
        data = {
            "base_dt": base_date,
            "ottks_tp": ottks_tp,
            "ch_crd_tp": ch_crd_tp
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"당일매매일지 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"당일매매일지 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"당일매매일지 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_outstanding_orders_internal(self, all_stk_tp: str = "0", trde_tp: str = "0", 
                                             stk_cd: str = "", stex_tp: str = "0",
                                             cont_yn: str = "N", next_key: str = "") -> dict:
        """내부 미체결 주문 조회"""
        url = f"{self.host}/api/dostk/acnt"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10075"
        }
        
        data = {
            "all_stk_tp": all_stk_tp,
            "trde_tp": trde_tp,
            "stk_cd": stk_cd,
            "stex_tp": stex_tp
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"미체결 주문 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"미체결 주문 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"미체결 주문 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_executed_orders_internal(self, stk_cd: str = "", qry_tp: str = "0", 
                                          sell_tp: str = "0", ord_no: str = "", 
                                          stex_tp: str = "0", cont_yn: str = "N", 
                                          next_key: str = "") -> dict:
        """내부 체결 주문 조회"""
        url = f"{self.host}/api/dostk/acnt"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10076"
        }
        
        data = {
            "stk_cd": stk_cd,
            "qry_tp": qry_tp,
            "sell_tp": sell_tp,
            "ord_no": ord_no,
            "stex_tp": stex_tp
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"체결 주문 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"체결 주문 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"체결 주문 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_daily_item_realized_profit_internal(self, stk_cd: str, strt_dt: str,
                                                      cont_yn: str = "N", next_key: str = "") -> dict:
        """내부 일자별종목별실현손익 조회"""
        url = f"{self.host}/api/dostk/acnt"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10072"
        }
        
        data = {
            "stk_cd": stk_cd,
            "strt_dt": strt_dt
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"일자별종목별실현손익 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"일자별종목별실현손익 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"일자별종목별실현손익 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_daily_realized_profit_internal(self, strt_dt: str, end_dt: str,
                                                cont_yn: str = "N", next_key: str = "") -> dict:
        """내부 일자별실현손익 조회"""
        url = f"{self.host}/api/dostk/acnt"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10074"
        }
        
        data = {
            "strt_dt": strt_dt,
            "end_dt": end_dt
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"일자별 실현손익 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"일자별 실현손익 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"일자별 실현손익 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_account_return_internal(self, stex_tp: str = "0",
                                         cont_yn: str = "N", next_key: str = "") -> dict:
        """내부 계좌수익률 조회"""
        url = f"{self.host}/api/dostk/acnt"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10085"
        }
        
        data = {"stex_tp": stex_tp}
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"계좌수익률 조회 응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"계좌수익률 조회 응답 내용: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            headers_dict = dict(response.headers)
            result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
            result['next_key'] = headers_dict.get('next-key', '')
            
            return result
        except Exception as e:
            logger.error(f"계좌수익률 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    async def _get_account_info_internal(self, query_type: str = "1", exchange_type: str = "K", 
                                       cont_yn: str = "N", next_key: str = "") -> dict:
        """내부 계좌 정보 조회"""
        url = f"{self.host}/api/dostk/acnt"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "kt00018"
        }
        
        data = {
            "qry_tp": query_type,
            "dmst_stex_tp": exchange_type
        }
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=data)
            )
            
            logger.debug(f"응답 코드: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"응답 내용: {response.text}")
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"계좌 정보 조회 오류: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"에러 응답 내용: {e.response.text}")
            raise

    # =================================================================
    # 공개 API 메서드들 (큐를 통해 호출되는 메서드들)
    # =================================================================
    
    # 주식 정보 조회
    async def get_stock_info(self, code: str) -> dict:
        """주식 기본 정보 조회"""
        return await self._queue_api_call(self._get_stock_info_internal, code)

    # 차트 조회
    async def get_tick_chart(self, code: str, tick_scope: str = "1", 
                           price_type: str = "1", cont_yn: str = "N", 
                           next_key: str = "") -> dict:
        """틱차트 조회"""
        return await self._queue_api_call(
            self._get_tick_chart_internal,
            code, tick_scope, price_type, cont_yn, next_key
        )

    async def get_minute_chart(self, code: str, tic_scope: str = "1", 
                             price_type: str = "1", cont_yn: str = "N", 
                             next_key: str = "") -> dict:
        """분봉차트 조회"""
        return await self._queue_api_call(
            self._get_minute_chart_internal,
            code, tic_scope, price_type, cont_yn, next_key
        )

    async def get_daily_chart(self, code: str, base_dt: str = "", 
                            price_type: str = "1", cont_yn: str = "N", 
                            next_key: str = "") -> dict:
        """일봉차트 조회"""
        return await self._queue_api_call(
            self._get_daily_chart_internal,
            code, base_dt, price_type, cont_yn, next_key
        )

    async def get_weekly_chart(self, code: str, base_dt: str = "", 
                             price_type: str = "1", cont_yn: str = "N", 
                             next_key: str = "") -> dict:
        """주봉차트 조회"""
        return await self._queue_api_call(
            self._get_weekly_chart_internal,
            code, base_dt, price_type, cont_yn, next_key
        )

    async def get_monthly_chart(self, code: str, base_dt: str = "", 
                              price_type: str = "1", cont_yn: str = "N", 
                              next_key: str = "") -> dict:
        """월봉차트 조회"""
        return await self._queue_api_call(
            self._get_monthly_chart_internal,
            code, base_dt, price_type, cont_yn, next_key
        )

    async def get_yearly_chart(self, code: str, base_dt: str = "", 
                             price_type: str = "1", cont_yn: str = "N", 
                             next_key: str = "") -> dict:
        """년봉차트 조회"""
        return await self._queue_api_call(
            self._get_yearly_chart_internal,
            code, base_dt, price_type, cont_yn, next_key
        )

    # 주식 주문
    async def order_stock_buy(self, dmst_stex_tp: str, stk_cd: str, 
                            ord_qty: str, ord_uv: str = "", 
                            trde_tp: str = "3", cond_uv: str = "",
                            cont_yn: str = "N", next_key: str = "") -> dict:
        """주식 매수주문"""
        return await self._queue_api_call(
            self._order_stock_buy_internal,
            dmst_stex_tp, stk_cd, ord_qty, ord_uv, trde_tp, cond_uv, cont_yn, next_key
        )

    async def order_stock_sell(self, dmst_stex_tp: str, stk_cd: str, 
                             ord_qty: str, ord_uv: str = "", 
                             trde_tp: str = "0", cond_uv: str = "",
                             cont_yn: str = "N", next_key: str = "") -> dict:
        """주식 매도주문"""
        return await self._queue_api_call(
            self._order_stock_sell_internal,
            dmst_stex_tp, stk_cd, ord_qty, ord_uv, trde_tp, cond_uv, cont_yn, next_key
        )

    async def order_stock_modify(self, dmst_stex_tp: str, orig_ord_no: str, 
                               stk_cd: str, mdfy_qty: str, mdfy_uv: str, 
                               mdfy_cond_uv: str = "", cont_yn: str = "N",
                               next_key: str = "") -> dict:
        """주식 정정주문"""
        return await self._queue_api_call(
            self._order_stock_modify_internal,
            dmst_stex_tp, orig_ord_no, stk_cd, mdfy_qty, mdfy_uv, mdfy_cond_uv, cont_yn, next_key
        )

    async def order_stock_cancel(self, dmst_stex_tp: str, orig_ord_no: str, 
                               stk_cd: str, cncl_qty: str,
                               cont_yn: str = "N", next_key: str = "") -> dict:
        """주식 취소주문"""
        return await self._queue_api_call(
            self._order_stock_cancel_internal,
            dmst_stex_tp, orig_ord_no, stk_cd, cncl_qty, cont_yn, next_key
        )

    # 계좌 정보
    async def get_deposit_detail(self, query_type: str = "2", 
                               cont_yn: str = "N", next_key: str = "") -> dict:
        """예수금상세현황 조회"""
        return await self._queue_api_call(
            self._get_deposit_detail_internal,
            query_type, cont_yn, next_key
        )

    async def get_order_detail(self, order_date: str, query_type: str = "1", 
                             stock_bond_type: str = "1", sell_buy_type: str = "0", 
                             stock_code: str = "", from_order_no: str = "", 
                             market_type: str = "KRX", cont_yn: str = "N", 
                             next_key: str = "") -> dict:
        """계좌별주문체결내역상세 조회"""
        return await self._queue_api_call(
            self._get_order_detail_internal,
            order_date, query_type, stock_bond_type, sell_buy_type, 
            stock_code, from_order_no, market_type, cont_yn, next_key
        )

    async def get_daily_trading_log(self, base_date: str = "", ottks_tp: str = "1", 
                                  ch_crd_tp: str = "0", cont_yn: str = "N", 
                                  next_key: str = "") -> dict:
        """당일매매일지 조회"""
        return await self._queue_api_call(
            self._get_daily_trading_log_internal,
            base_date, ottks_tp, ch_crd_tp, cont_yn, next_key
        )

    async def get_outstanding_orders(self, all_stk_tp: str = "0", trde_tp: str = "0", 
                                   stk_cd: str = "", stex_tp: str = "0",
                                   cont_yn: str = "N", next_key: str = "") -> dict:
        """미체결 주문 조회"""
        return await self._queue_api_call(
            self._get_outstanding_orders_internal,
            all_stk_tp, trde_tp, stk_cd, stex_tp, cont_yn, next_key
        )

    async def get_executed_orders(self, stk_cd: str = "", qry_tp: str = "0", 
                                sell_tp: str = "0", ord_no: str = "", 
                                stex_tp: str = "0", cont_yn: str = "N", 
                                next_key: str = "") -> dict:
        """체결 주문 조회"""
        return await self._queue_api_call(
            self._get_executed_orders_internal,
            stk_cd, qry_tp, sell_tp, ord_no, stex_tp, cont_yn, next_key
        )

    async def get_daily_item_realized_profit(self, stk_cd: str, strt_dt: str,
                                           cont_yn: str = "N", next_key: str = "") -> dict:
        """일자별종목별실현손익 조회"""
        return await self._queue_api_call(
            self._get_daily_item_realized_profit_internal,
            stk_cd, strt_dt, cont_yn, next_key
        )

    async def get_daily_realized_profit(self, strt_dt: str, end_dt: str,
                                      cont_yn: str = "N", next_key: str = "") -> dict:
        """일자별실현손익 조회"""
        return await self._queue_api_call(
            self._get_daily_realized_profit_internal,
            strt_dt, end_dt, cont_yn, next_key
        )

    async def get_account_return(self, stex_tp: str = "0",
                               cont_yn: str = "N", next_key: str = "") -> dict:
        """계좌수익률 조회"""
        return await self._queue_api_call(
            self._get_account_return_internal,
            stex_tp, cont_yn, next_key
        )

    async def get_account_info(self, query_type: str = "1", exchange_type: str = "K", 
                             cont_yn: str = "N", next_key: str = "") -> dict:
        """계좌 정보 조회"""
        return await self._queue_api_call(
            self._get_account_info_internal,
            query_type, exchange_type, cont_yn, next_key
        )