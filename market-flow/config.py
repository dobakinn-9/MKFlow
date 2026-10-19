"""앱 전체에서 쓰는 설정값.

티커는 야후 파이낸스(yfinance) 기준이에요. 새 지표를 추가하려면 아래 목록에 한 줄만 넣으면 됩니다.
"""

# 티커: (한국어 이름, 그룹)
TICKERS = {
    "^KS11": ("코스피", "한국"),
    "^KQ11": ("코스닥", "한국"),
    "^GSPC": ("S&P 500", "미국"),
    "^IXIC": ("나스닥 종합", "미국"),
    "^DJI": ("다우존스", "미국"),
    "^RUT": ("러셀 2000", "미국"),
    "^SOX": ("필라델피아 반도체", "미국"),
    "^VIX": ("VIX 변동성", "거시"),
    "^TNX": ("미 10년물 금리", "거시"),
    "^IRX": ("미 3개월물 금리", "거시"),
    "KRW=X": ("원/달러 환율", "거시"),
    "DX-Y.NYB": ("달러인덱스", "거시"),
    "CL=F": ("WTI 유가", "거시"),
    "GC=F": ("금", "거시"),
}

# 미국 업종(섹터) ETF — 업종 순환 분석용
US_SECTORS = {
    "XLK": "기술",
    "XLC": "커뮤니케이션",
    "XLY": "임의소비재",
    "XLF": "금융",
    "XLI": "산업재",
    "XLE": "에너지",
    "XLB": "소재",
    "XLV": "헬스케어",
    "XLP": "필수소비재",
    "XLU": "유틸리티",
    "XLRE": "부동산",
}

# 시장의 폭(미국): 동일가중 S&P 500(RSP) vs 시가총액가중(SPY)
BREADTH_US = {"RSP": "S&P 500 동일가중", "SPY": "S&P 500 시총가중"}

# 세계 주요 지수
WORLD = {
    "^N225": "일본 닛케이 225",
    "000001.SS": "중국 상하이종합",
    "^HSI": "홍콩 항셍",
    "^TWII": "대만 가권",
    "^NSEI": "인도 니프티 50",
    "^STOXX50E": "유로 스톡스 50",
    "^GDAXI": "독일 DAX",
}

# 숨은 지표: 잘 알려지지 않았지만 전문가들이 보는 신호
# kind="ratio": num ÷ den 이 오르면 good_when_up 이 True일 때 긍정 신호
# kind="level": 값 자체가 높으면 부담(high_is_bad)
HIDDEN = [
    {"key": "copper_gold", "title": "구리 ÷ 금 비율", "kind": "ratio", "num": "HG=F", "den": "GC=F", "good_when_up": True,
     "what": "구리는 공장·건설에 쓰이는 '경기 금속', 금은 불안할 때 사는 '안전 금속'이에요. 이 비율이 오르면 시장이 경기 회복을, 내리면 경기 둔화를 예상한다는 뜻이에요.",
     "why": "별명이 '닥터 코퍼'예요. 미국 10년물 금리와 방향이 비슷하게 움직여서 금리 흐름을 먼저 보여주기도 해요."},
    {"key": "credit", "title": "하이일드 채권 ÷ 국채", "kind": "ratio", "num": "HYG", "den": "IEF", "good_when_up": True,
     "what": "신용등급이 낮은 회사채(하이일드)와 안전한 미국 국채의 가격 비율이에요. 오르면 투자자들이 위험을 감수하고, 급락하면 '돈줄이 마르는' 신용 경색 신호예요.",
     "why": "주식보다 채권 투자자가 먼저 위험을 알아채는 경우가 많아요. 주가는 버티는데 이 비율이 먼저 꺾이면 경고등이에요."},
    {"key": "transports", "title": "운송주 ÷ 다우산업", "kind": "ratio", "num": "^DJT", "den": "^DJI", "good_when_up": True,
     "what": "물건을 실어 나르는 운송 회사(항공·철도·트럭)와 물건을 만드는 산업 대기업의 상대 강도예요. 운송이 같이 올라야 실물 경기가 진짜 좋다는 뜻이에요.",
     "why": "100년 넘게 쓰인 '다우 이론'의 핵심이에요. 산업주만 오르고 운송주가 못 따라오면 상승이 오래가지 못한다고 봐요."},
    {"key": "semis", "title": "반도체 ÷ S&P 500", "kind": "ratio", "num": "^SOX", "den": "^GSPC", "good_when_up": True,
     "what": "AI·반도체 사이클이 시장을 주도하고 있는지 보여줘요. 한국 시장(삼성전자·SK하이닉스 비중이 큼)에 특히 중요해요.",
     "why": "이 비율이 꺾이면 코스피도 외국인 매도로 흔들리는 경우가 많아요."},
    {"key": "em", "title": "신흥국 ÷ 미국 주식", "kind": "ratio", "num": "EEM", "den": "SPY", "good_when_up": True,
     "what": "한국·대만·중국 등 신흥국 주식이 미국 주식보다 강한지 보여줘요. 오르면 세계 자금이 신흥국으로 흘러들어오는 중이에요.",
     "why": "달러가 약해질 때 이 비율이 오르는 경향이 있어서, 외국인의 한국 주식 매수와 함께 움직여요."},
    {"key": "small", "title": "소형주 ÷ 대형주 (미국)", "kind": "ratio", "num": "^RUT", "den": "^GSPC", "good_when_up": True,
     "what": "빚이 많고 국내 경기에 민감한 소형주가 대형주보다 강한지 보여줘요.",
     "why": "금리가 내려갈 거라는 기대가 생기면 소형주가 먼저 반응해요. 금리 방향의 '숨은 투표'예요."},
    {"key": "yen", "title": "엔/달러 환율 (엔 캐리 위험)", "kind": "level_change", "series": "JPY=X", "bad_when_down": True,
     "what": "1달러에 몇 엔인지예요. 숫자가 빠르게 내려가면(엔화 급강세) 싼 엔화를 빌려 해외 자산에 투자하던 돈이 한꺼번에 빠져나갈 수 있어요.",
     "why": "'엔 캐리 트레이드 청산'이라고 해요. 2024년 8월 초 엔화 급등 때 한국·일본 증시가 하루에 8~12% 급락한 적이 있어요."},
    {"key": "move", "title": "MOVE 지수 (채권 공포 지수)", "kind": "level", "series": "^MOVE", "warn": 120, "calm": 90,
     "what": "미국 국채 가격이 얼마나 크게 흔들릴지 예상하는 지수예요. 주식의 VIX에 해당하는 '채권판 공포 지수'예요.",
     "why": "채권 시장이 불안하면 결국 주식으로 번져요. VIX보다 먼저 오르는 경우가 많아 선행 경고로 쓰여요. 120 이상이면 불안, 90 이하면 안정이에요."},
    {"key": "btc", "title": "비트코인 (위험 선호 온도계)", "kind": "level_change", "series": "BTC-USD", "bad_when_down": True,
     "what": "가장 위험한 자산 중 하나라서, 시장의 '위험을 즐기는 정도'를 실시간으로 보여주는 온도계로 쓰여요.",
     "why": "24시간 거래돼서 주말에 생긴 충격을 월요일 아침 증시보다 먼저 반영해요."},
]

KOREA = ["^KS11", "^KQ11"]
US = ["^GSPC", "^IXIC", "^DJI", "^RUT", "^SOX"]
RATES = ["^TNX", "^IRX"]
FX = ["KRW=X", "DX-Y.NYB"]
COMMOD = ["CL=F", "GC=F"]
MACRO = ["^VIX"] + RATES + FX + COMMOD

HIDDEN_TICKERS = ["HG=F", "HYG", "IEF", "^DJT", "EEM", "JPY=X", "^MOVE", "BTC-USD"]

ALL_YF = list(dict.fromkeys(list(TICKERS) + list(US_SECTORS) + list(BREADTH_US) + list(WORLD) + HIDDEN_TICKERS))

# 흐름 점수를 계산할 기준 지수
SCORE_TARGETS = {"^KS11": "코스피", "^GSPC": "S&P 500"}

# 앞으로 며칠 뒤 수익률을 '전망'으로 볼지 (거래일 기준)
FORWARD_DAYS = 20

# 데이터 캐시 시간(초). 30분마다 새로 받아와요.
CACHE_TTL = 1800

# 한국거래소(pykrx) 지수 코드
KRX_INDEX = {"코스피": "1001", "코스닥": "2001", "코스피200": "1028"}


def name(ticker: str) -> str:
    if ticker in TICKERS:
        return TICKERS[ticker][0]
    if ticker in US_SECTORS:
        return US_SECTORS[ticker]
    if ticker in BREADTH_US:
        return BREADTH_US[ticker]
    if ticker in WORLD:
        return WORLD[ticker]
    extra = {"HG=F": "구리", "HYG": "하이일드 채권 ETF", "IEF": "미 중기 국채 ETF", "^DJT": "다우 운송",
             "EEM": "신흥국 주식 ETF", "JPY=X": "엔/달러", "^MOVE": "MOVE 지수", "BTC-USD": "비트코인"}
    return extra.get(ticker, ticker)
