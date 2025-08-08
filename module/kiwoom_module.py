from datetime import datetime
from zoneinfo import ZoneInfo 
from dependency_injector.wiring import inject, Provide
import logging
from container.token_container import Token_Container
from module.token_module import TokenModule
from config import settings
import asyncio
import requests
from typing import Callable, Any, Dict
import time

logger = logging.getLogger("KiwoomModule")

class KiwoomModule:
    """키움 API와 통신하는 클라이언트 - 큐 기반 API 호출 제어"""
    
    api_call_interval: float = 0.3      # ✅ 클래스 전체 공유
    last_api_call_time: float = 0.0     # ✅ 클래스 전체 공유
    interval_lock = asyncio.Lock()      # ✅ 클래스 전체 공유
    
    # 설정값들을 클래스 상수로 정의
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 3
    RATE_LIMIT_BASE_WAIT = 0.3
    
    @inject
    def __init__(self, 
                token_module: TokenModule = Provide[Token_Container.token_module]):
        self.host = settings.HOST
        self.app_key = settings.KIWOOM_APP_KEY
        self.sec_key = settings.KIWOOM_SECRET_KEY
        self.token = None
        self.token_module = token_module
        self.logger = logging.getLogger(__name__)
        self.KST = ZoneInfo("Asia/Seoul")

    @classmethod
    async def _ensure_min_interval(cls):
        """클래스 전체에서 최소 호출 간격 보장"""
        async with cls.interval_lock:
            current_time = time.time()
            time_since_last_call = current_time - cls.last_api_call_time

            if time_since_last_call < cls.api_call_interval:
                sleep_time = cls.api_call_interval - time_since_last_call
                await asyncio.sleep(sleep_time)

            cls.last_api_call_time = time.time()

    async def _make_api_call(self, url: str, headers: dict, data: dict, 
                            api_name: str = "API", max_retries: int = None) -> dict:
        """공통 API 호출 메서드 - 429 에러를 정상 로직으로 처리"""
        if max_retries is None:
            max_retries = self.DEFAULT_MAX_RETRIES
            
        retry_count = 0
        
        while retry_count <= max_retries:
            await self._ensure_min_interval()
            
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, 
                    lambda: requests.post(url, headers=headers, json=data)
                )
                
                self.logger.debug(f"{api_name} 응답 코드: {response.status_code}")
                
                # 🟢 429를 정상 로직으로 처리
                if response.status_code == 429:
                    if retry_count < max_retries:
                        retry_count += 1
                        wait_time = self.RATE_LIMIT_BASE_WAIT * (2 ** (retry_count - 1))  # 지수 백오프
                        self.logger.info(f"{api_name} API 속도 제한 (429) - {wait_time:.1f}초 대기 후 재시도 ({retry_count}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        self.logger.error(f"{api_name} API 속도 제한으로 최대 재시도 횟수 초과")
                        raise RuntimeError(f"{api_name} 실패: API 속도 제한 (최대 {max_retries}회 재시도)")
                
                # 🟢 200이 아닌 다른 에러들 처리
                if response.status_code != 200:
                    self.logger.error(f"{api_name} 응답 내용: {response.text}")
                    response.raise_for_status()
                
                # 🟢 정상 응답 처리
                result = response.json()
                
                # 공통으로 처리할 수 있는 헤더 정보 추가
                headers_dict = dict(response.headers)
                result['has_next'] = headers_dict.get('has-next', 'N') == 'Y'
                result['next_key'] = headers_dict.get('next-key', '')
                
                self.logger.debug(f"{api_name} 호출 성공")
                return result
                
            except requests.exceptions.RequestException as e:
                self.logger.error(f"{api_name} 네트워크 오류: {str(e)}")
                if hasattr(e, 'response') and e.response is not None:
                    self.logger.error(f"에러 응답 내용: {e.response.text}")
                raise
            except Exception as e:
                self.logger.error(f"{api_name} 예상치 못한 오류: {str(e)}")
                raise
        
        raise RuntimeError(f"예상치 못한 상태: {api_name} 재시도 루프 종료")

    async def initialize(self):
        """비동기 초기화 메서드: 토큰 요청 재시도 포함"""
        for attempt in range(1, self.DEFAULT_MAX_RETRIES + 1):
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

            if attempt < self.DEFAULT_MAX_RETRIES:
                await asyncio.sleep(self.DEFAULT_RETRY_DELAY)

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

    # ========================================
    # 주식 정보 조회 관련 메서드들
    # ========================================
    
    async def get_stock_info(self, code: str) -> dict:
        """주식 정보 조회"""
        url = f"{self.host}/api/dostk/stkinfo"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": "N",
            "next-key": "",
            "api-id": "ka10001"
        }
        
        data = {"stk_cd": code}
        
        return await self._make_api_call(url, headers, data, "주식 정보 조회")

    async def get_tick_chart(self, code: str, tick_scope: str = "1", 
                            price_type: str = "1", cont_yn: str = "N", 
                            next_key: str = "") -> dict:
        """틱차트 조회"""
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
        
        return await self._make_api_call(url, headers, data, "틱차트 조회")

    async def get_minute_chart(self, code: str, tic_scope: str = "1", 
                              price_type: str = "1", cont_yn: str = "N", 
                              next_key: str = "") -> dict:
        """분봉차트 조회"""
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
        
        return await self._make_api_call(url, headers, data, "분봉차트 조회")

    async def get_daily_chart(self, code: str, base_dt: str = "", 
                             price_type: str = "1", cont_yn: str = "N", 
                             next_key: str = "") -> dict:
        """일봉차트 조회"""
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
        
        return await self._make_api_call(url, headers, data, "일봉차트 조회")

    async def get_weekly_chart(self, code: str, base_dt: str = "", 
                              price_type: str = "1", cont_yn: str = "N", 
                              next_key: str = "") -> dict:
        """주봉차트 조회"""
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
        
        return await self._make_api_call(url, headers, data, "주봉차트 조회")

    async def get_monthly_chart(self, code: str, base_dt: str = "", 
                               price_type: str = "1", cont_yn: str = "N", 
                               next_key: str = "") -> dict:
        """월봉차트 조회"""
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
        
        return await self._make_api_call(url, headers, data, "월봉차트 조회")

    async def get_yearly_chart(self, code: str, base_dt: str = "", 
                              price_type: str = "1", cont_yn: str = "N", 
                              next_key: str = "") -> dict:
        """년봉차트 조회"""
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
        
        return await self._make_api_call(url, headers, data, "년봉차트 조회")
   
    async def get_sector_index(self, inds_cd: str = "1", 
                                  cont_yn: str = "N", next_key: str = "") -> dict:
            """전업종지수 조회
            
            Args:
                inds_cd (str): 업종코드 (1: 종합(KOSPI), 101: 종합(KOSDAQ))
                cont_yn (str): 연속조회여부 (N: 신규조회, Y: 연속조회)
                next_key (str): 연속조회키
                
            Returns:
                dict: 전업종지수 정보
            """
            url = f"{self.host}/api/dostk/sect"
            
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "Authorization": f"Bearer {self.token}",
                "cont-yn": cont_yn,
                "next-key": next_key,
                "api-id": "ka20003"
            }
            
            data = {"inds_cd": inds_cd}
            
            return await self._make_api_call(url, headers, data, "전업종지수 조회")
    # ========================================
    # 주식 주문 관련 메서드들
    # ========================================

    async def order_stock_buy(self, dmst_stex_tp: str, stk_cd: str, 
                             ord_qty: str, ord_uv: str = "", 
                             trde_tp: str = "3", cond_uv: str = "",
                             cont_yn: str = "N", next_key: str = "") -> dict:
        """매수주문"""
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
        
        result = await self._make_api_call(url, headers, data, "주식 매수주문")
        self.logger.info(f"주식 매수주문 성공: {stk_cd}, {ord_qty}주, 주문번호: {result.get('ord_no', '알 수 없음')}")
        return result

    async def order_stock_sell(self, dmst_stex_tp: str, stk_cd: str, 
                              ord_qty: str, ord_uv: str = "", 
                              trde_tp: str = "0", cond_uv: str = "",
                              cont_yn: str = "N", next_key: str = "") -> dict:
        """매도주문"""
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
        
        result = await self._make_api_call(url, headers, data, "주식 매도주문")
        self.logger.info(f"주식 매도주문 성공: {stk_cd}, {ord_qty}주, 주문번호: {result.get('ord_no', '알 수 없음')}")
        return result

    async def order_stock_modify(self, dmst_stex_tp: str, orig_ord_no: str, 
                                stk_cd: str, mdfy_qty: str, mdfy_uv: str, 
                                mdfy_cond_uv: str = "", cont_yn: str = "N",
                                next_key: str = "") -> dict:
        """정정주문"""
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
        
        result = await self._make_api_call(url, headers, data, "주식 정정주문")
        self.logger.info(f"주식 정정주문 성공: {stk_cd}, 원주문번호: {orig_ord_no}, 정정수량: {mdfy_qty}, 정정단가: {mdfy_uv}")
        return result

    async def order_stock_cancel(self, dmst_stex_tp: str, orig_ord_no: str, 
                                stk_cd: str, cncl_qty: str,
                                cont_yn: str = "N", next_key: str = "") -> dict:
        """취소주문"""
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
        
        result = await self._make_api_call(url, headers, data, "주식 취소주문")
        self.logger.info(f"주식 취소주문 성공: {stk_cd}, 원주문번호: {orig_ord_no}, 취소수량: {cncl_qty}")
        return result

    # ========================================
    # 계좌 정보 관련 메서드들
    # ========================================

    async def get_deposit_detail(self, query_type: str = "2", 
                                cont_yn: str = "N", next_key: str = "") -> dict:
        """예수금상세현황 조회"""
        url = f"{self.host}/api/dostk/acnt"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "kt00001"
        }
        
        data = {"qry_tp": query_type}
        
        return await self._make_api_call(url, headers, data, "예수금상세현황 조회")

    async def get_order_detail(self, order_date: str, query_type: str = "1", 
                              stock_bond_type: str = "1", sell_buy_type: str = "0", 
                              stock_code: str = "", from_order_no: str = "", 
                              market_type: str = "KRX", cont_yn: str = "N", 
                              next_key: str = "") -> dict:
        """주문체결내역 상세 조회"""
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
        
        return await self._make_api_call(url, headers, data, "주문체결내역 상세 조회")

    async def get_daily_trading_log(self, base_date: str = "", ottks_tp: str = "1", 
                                   ch_crd_tp: str = "0", cont_yn: str = "N", 
                                   next_key: str = "") -> dict:
        """당일매매일지 조회"""
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
        
        return await self._make_api_call(url, headers, data, "당일매매일지 조회")

    async def get_outstanding_orders(self, all_stk_tp: str = "0", trde_tp: str = "0", 
                                    stk_cd: str = "", stex_tp: str = "0",
                                    cont_yn: str = "N", next_key: str = "") -> dict:
        """미체결 주문 조회"""
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
        
        return await self._make_api_call(url, headers, data, "미체결 주문 조회")

    async def get_executed_orders(self, stk_cd: str = "", qry_tp: str = "0", 
                                 sell_tp: str = "0", ord_no: str = "", 
                                 stex_tp: str = "0", cont_yn: str = "N", 
                                 next_key: str = "") -> dict:
        """체결 주문 조회"""
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
        
        return await self._make_api_call(url, headers, data, "체결 주문 조회")

    async def get_daily_item_realized_profit(self, stk_cd: str, strt_dt: str,
                                            cont_yn: str = "N", next_key: str = "") -> dict:
        """일자별종목별실현손익 조회"""
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
        
        return await self._make_api_call(url, headers, data, "일자별종목별실현손익 조회")

    async def get_daily_realized_profit(self, strt_dt: str, end_dt: str,
                                       cont_yn: str = "N", next_key: str = "") -> dict:
        """일자별실현손익 조회"""
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
        
        return await self._make_api_call(url, headers, data, "일자별실현손익 조회")

    async def get_account_return(self, stex_tp: str = "0",
                                cont_yn: str = "N", next_key: str = "") -> dict:
        """계좌수익률 조회"""
        url = f"{self.host}/api/dostk/acnt"
        
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self.token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": "ka10085"
        }
        
        data = {"stex_tp": stex_tp}
        
        return await self._make_api_call(url, headers, data, "계좌수익률 조회")

    async def get_account_info(self, query_type: str = "1", exchange_type: str = "K", 
                              cont_yn: str = "N", next_key: str = "") -> dict:
        """계좌 정보 조회"""
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
        
        return await self._make_api_call(url, headers, data, "계좌 정보 조회")