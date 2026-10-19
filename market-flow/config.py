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

KOREA = ["^KS11", "^KQ11"]
US = ["^GSPC", "^IXIC", "^DJI", "^RUT", "^SOX"]
RATES = ["^TNX", "^IRX"]
FX = ["KRW=X", "DX-Y.NYB"]
COMMOD = ["CL=F", "GC=F"]
MACRO = ["^VIX"] + RATES + FX + COMMOD

ALL_YF = list(TICKERS) + list(US_SECTORS) + list(BREADTH_US)

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
    return ticker
