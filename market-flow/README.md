# 한·미 시장 흐름 (Streamlit 웹 앱)

코스피·코스닥과 미국 주요 지수, 금리·환율·유가·변동성을 한 화면에서 보고,
여러 요인을 합산한 **흐름 점수**와 **과거 비슷한 국면 이후의 수익률 통계(전망)**를 보여주는 웹 앱이에요.

> 참고용 분석 도구이며 투자 권유가 아닙니다. 과거 통계는 미래를 보장하지 않아요.

## 메뉴 구성 (왼쪽 사이드바)

| 분류 | 세부 메뉴 | 내용 |
|---|---|---|
| **종합** | 오늘의 시장 | 두 시장 흐름 점수, 아침 5분 체크리스트, 전체 지표 현황 |
| | 흐름 점수·전망 | 요인별 진단, 점수 추이, 비슷한 국면 이후 N거래일 수익률 통계, 점수 검증표 |
| **시장 보고서** | 세계 동향 브리핑 | 지역별(중동·AI 투자·중국·유럽·일본·금) 현황, 잘 알려지지 않은 사실, 한국 영향 + 세계 증시 성적표 (`data/world_brief.json`) |
| | 숨은 지표 | 구리÷금, 하이일드÷국채, 운송÷산업, 반도체÷S&P, 신흥국÷미국, 소형÷대형, 엔/달러, MOVE, 비트코인 신호판 |
| | 미국 경제 보고서 | CPI·고용·FOMC·베이지북·GDP 등 한국어 요약 (`data/us_reports.json`) |
| **돈의 가격** | 금리 | 미 10년물·3개월물, 장단기 금리차(역전 여부) |
| | 환율·달러 | 원/달러와 코스피 비교, 달러인덱스 |
| | 유가·금 | WTI와 미국 금리, 금 |
| **시장의 체력** | 추세·이동평균 | 20·60·120일선, 지표 비교(시작일=100) |
| | 시장의 폭 | 한국 상승·하락 종목 수와 ADL, 미국 동일가중÷시총가중, 업종 ETF 50일선 위 비율 |
| | 거래대금 | 코스피·코스닥 거래대금과 20일 평균, S&P 500 거래량 |
| | 변동성 | VIX, VKOSPI (없으면 코스피 실제 변동성으로 대체) |
| | 업종 순환 | 코스피 업종 등락, 미국 업종 ETF, 공격÷방어 업종 비율 |
| **수급** | 투자자별 매매 | 외국인·기관·개인 순매수, 연속 매매일, 누적 추이 |
| **심리·가격 수준** | 과열·과매도 | 지수별 RSI |
| | 밸류에이션 | 코스피·코스닥 PER·PBR과 5년 중 위치 |
| | 시장 간 연결 | 60일 상관계수 |
| **일정** | 이벤트 캘린더 | 실적·FOMC·선거 등 (`data/events.csv`) |

각 화면 위쪽의 **"이 지표는 어떻게 읽나요?"**를 펼치면 해석 방법이 나와요.

## 1. 내 컴퓨터에서 실행하기

### 준비물
- 파이썬 3.10 이상 ([python.org](https://www.python.org/downloads/)에서 설치. 윈도우는 설치 화면에서 **Add python.exe to PATH**를 꼭 체크하세요.)

### 실행 순서
터미널(윈도우는 '명령 프롬프트' 또는 PowerShell)을 열고 이 폴더로 이동한 뒤:

```bash
# 1) 가상환경 만들기 (처음 한 번)
python -m venv .venv

# 2) 가상환경 켜기
#    윈도우:      .venv\Scripts\activate
#    맥/리눅스:   source .venv/bin/activate

# 3) 필요한 패키지 설치 (처음 한 번)
pip install -r requirements.txt

# 4) 앱 실행
streamlit run app.py
```

브라우저가 자동으로 열리고 `http://localhost:8501` 에서 앱이 보여요. 끄려면 터미널에서 `Ctrl + C`.

### 인터넷 없이 화면만 확인하기 (데모 모드)
```bash
# 맥/리눅스
MARKET_FLOW_DEMO=1 streamlit run app.py
# 윈도우 PowerShell
$env:MARKET_FLOW_DEMO="1"; streamlit run app.py
```
샘플(가짜) 데이터로 동작해요.

## 2. 인터넷에 무료로 배포하기 (Streamlit Community Cloud)

1. [GitHub](https://github.com)에 가입하고 새 저장소(repository)를 만들어요. 예: `market-flow`
2. 이 폴더의 파일(`app.py`, `analysis.py`, `data.py`, `config.py`, `requirements.txt`, `README.md`, `.streamlit/config.toml`)을 저장소에 올려요. 웹에서 **Add file → Upload files**로 끌어다 놓으면 돼요.
3. [share.streamlit.io](https://share.streamlit.io)에 GitHub 계정으로 로그인해요.
4. **Create app** → 방금 만든 저장소 선택 → Main file path에 `app.py` → **Deploy**.
5. 몇 분 뒤 `https://<이름>.streamlit.app` 주소가 생겨요. 이 링크를 공유하면 누구나 볼 수 있어요.

코드를 고쳐서 GitHub에 다시 올리면 앱도 자동으로 업데이트돼요.

> 참고: 클라우드 서버는 해외에 있어서 한국거래소(pykrx) 수급 데이터가 막힐 수 있어요. 그 경우 '한국 수급' 탭만 안내 문구가 나오고 나머지는 정상 동작해요.

## 3. 고쳐 쓰기

- **지표 추가/삭제**: `config.py`의 `TICKERS`에 야후 파이낸스 티커를 한 줄 추가하고, `KOREA`·`US`·`MACRO` 중 원하는 그룹에도 넣어요.
  예: 니케이 225 → `"^N225": ("니케이 225", "일본")`
- **점수 요인·가중치 바꾸기**: `analysis.py`의 `build_factors()`에서 각 `Factor(..., 가중치, ...)` 숫자를 바꿔요.
- **전망 기간 기본값**: `config.py`의 `FORWARD_DAYS` (20거래일 ≈ 1개월).

## 파일 구조

```
market-flow/
├── app.py            # 메뉴(분류·세부 메뉴)와 공통 설정
├── views/            # 분류별 화면
│   ├── overview.py   #   종합
│   ├── reports.py    #   시장 보고서 (세계 동향·숨은 지표)
│   ├── money.py      #   돈의 가격
│   ├── strength.py   #   시장의 체력
│   ├── flows.py      #   수급
│   ├── sentiment.py  #   심리·가격 수준
│   └── calendar.py   #   일정
├── common.py         # 페이지 공통 캐시·차트 도우미
├── analysis.py       # 흐름 점수, 전망 통계, 시장 폭·변동성 계산
├── data.py           # 데이터 수집 (yfinance, pykrx, data/ 파일)
├── config.py         # 티커와 설정값
├── data/             # 일정·미국 보고서·세계 동향 파일
└── requirements.txt  # 필요한 파이썬 패키지
```
저장소 맨 위의 `.streamlit/config.toml`은 화면 테마 설정이에요.

> Streamlit Cloud의 Main file path는 `market-flow/app.py`예요.

## 데이터 출처
- 지수·금리·환율·유가·VIX: Yahoo Finance (`yfinance`). 지연 시세일 수 있어요.
- 코스피 투자자별 순매수: 한국거래소 (`pykrx`).
