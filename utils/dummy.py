import random
import time
import copy



# 기반 딕셔너리 구조 정의
template = {
    "trnm": "REAL",
    "data": [
        {
            "type": "0B",
            "name": "주식체결",
            "item": "005930",
            "values": {
                "20": "165208",
                "10": "-20800",
                "11": "-50",
                "12": "-0.24",
                "27": "-20800",
                "28": "-20700",
                "15": "+82",
                "13": "30379732",
                "14": "632640",
                "16": "20850",
                "17": "+21150",
                "18": "-20450",
                "25": "5",
                "26": "-1057122",
                "29": "-22041267850",
                "30": "-96.64",
                "31": "36.67",
                "32": "44",
                "228": "98.92",
                "311": "17230",
                "290": "2",
                "691": "0",
                "567": "000000",
                "568": "000000",
                "851": "",
                "1890": "",
                "1891": "",
                "1892": "",
                "1030": "",
                "1031": "",
                "1032": "",
                "1071": "",
                "1072": "",
                "1313": "",
                "1315": "",
                "1316": "",
                "1314": "",
                "1497": "",
                "1498": "",
                "620": "",
                "732": "",
                "852": "",
                "9081": "1"
            }
        }
    ]
}

# 랜덤 값 생성기
def randomize_value(value: str) -> str:
    if value == '':
        return ''
    try:
        if value.startswith('+') or value.startswith('-'):
            num = float(value[1:])
            change = num * random.uniform(0.01, 0.1)
            new_val = num + change if value.startswith('+') else num - change
            return f"{value[0]}{int(new_val)}" if '.' not in value else f"{value[0]}{new_val:.2f}"
        elif '.' in value:
            return f"{float(value) + random.uniform(-1.0, 1.0):.2f}"
        elif value.isdigit():
            return str(max(0, int(value) + random.randint(-1000, 1000)))
        else:
            return value
    except:
        return value

# 반복적으로 방출하는 제너레이터
def stock_data_stream():
    while True:
        new_data = copy.deepcopy(template)
        values = new_data['data'][0]['values']
        for key in values:
            values[key] = randomize_value(values[key])
        # 타임스탬프 예시 업데이트
        values["20"] = str(int(time.time()))
        yield new_data
        
        
