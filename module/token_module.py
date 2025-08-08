import logging
import requests
from config import settings
import time

logger = logging.getLogger("TokenModule")

class TokenModule:
    def __init__(self):
        # 실전투자 또는 모의투자 호스트 선택
        self.host = settings.HOST
        self.app_key = settings.KIWOOM_APP_KEY
        self.sec_key = settings.KIWOOM_SECRET_KEY
        self.token = None
        self.issued_at = 0

    def get_token(self):
        # 요청할 API URL
        endpoint = '/oauth2/token'
        url = self.host + endpoint
        
        # header 데이터
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
        }
        
        # 요청 데이터
        data = {
            'grant_type': 'client_credentials',
            'appkey': self.app_key,
            'secretkey': self.sec_key,
        }
        
        # HTTP POST 요청
        response = requests.post(url, headers=headers, json=data)

        response_data = response.json()
        return response_data["token"]
      
    def get_token_info(self):
        # 요청할 API URL
        endpoint = '/oauth2/token'
        url = self.host + endpoint
        
        # header 데이터
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
        }
        
        # 요청 데이터
        data = {
            'grant_type': 'client_credentials',
            'appkey': self.app_key,
            'secretkey': self.sec_key,
        }
        
        gap_time = time.time() - self.issued_at
        
        if gap_time > 1800 and self.token is None : 
            response = requests.post(url, headers=headers, json=data)
            response_data = response.json()
            self.token = response_data
            self.issued_at = time.time()
            logger.info(f"{self.issued_at} 에 토큰 발급 성공.")
        else : logger.info(f"{self.issued_at} 에 발급된 토큰이 이미 있습니다.")
        return self.token 

    def delete_token(self):
        # 요청할 API URL
        endpoint = '/oauth2/revoke'
        url = self.host + endpoint
        
        # header 데이터
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
        }
        
        # 요청 데이터
        data = {
            'grant_type': 'client_credentials',
            'appkey': self.app_key,
            'secretkey': self.sec_key,
        }
        
        # HTTP POST 요청
        response = requests.post(url, headers=headers, json=data)
        response_data = response.json()        
        return response_data["return_msg"]
