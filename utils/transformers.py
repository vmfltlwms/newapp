# utils/transformers.py

import re

def transform_numeric_data(data):
    """데이터를 재귀적으로 순회하며 음수/양수 문자열을 숫자로 변환"""
    # 문자열로 유지할 필드 목록
    string_fields = ['stk_cd', 'cntr_tm', 'dt']
    
    # 특수 포맷이 필요한 필드 (예: 앞에 0을 채워야 하는 필드)
    special_format_fields = {
        'stk_cd': lambda x: str(x).zfill(6) if isinstance(x, (int, float)) else x
    }
    
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            # 특수 포맷이 필요한 필드인 경우
            if k in special_format_fields:
                result[k] = special_format_fields[k](v)
            # 문자열로 유지할 필드인 경우
            elif k in string_fields:
                result[k] = v
            else:
                result[k] = transform_numeric_data(v)
        return result
    elif isinstance(data, list):
        return [transform_numeric_data(item) for item in data]
    elif isinstance(data, str):
        # 문자열이 숫자 형태인지 확인 (+ 또는 - 부호 모두 처리)
        if re.match(r'^[+-]?\d+(\.\d+)?$', data):
            # 숫자 문자열이면 변환
            try:
                # '+' 또는 '-' 기호가 있으면 제거
                if data.startswith(('+', '-')):
                    # '-' 부호인 경우 음수로 변환
                    if data.startswith('-'):
                        numeric_value = -float(data[1:])
                    else:  # '+' 부호인 경우
                        numeric_value = float(data[1:])
                else:
                    numeric_value = float(data)
                
                # 정수인 경우 int로 변환
                if numeric_value.is_integer():
                    return int(numeric_value)
                return numeric_value
            except ValueError:
                return data
        return data
    else:
        return data