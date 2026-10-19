# 한·미 시장 흐름 (Streamlit 웹 앱)

코스피·코스닥과 미국 주요 지수, 금리·환율·유가·변동성을 한 화면에서 보고,
여러 요인을 합산한 **흐름 점수**와 **과거 비슷한 국면 이후의 수익률 통계(전망)**를 보여주는 웹 앱이에요.

> 참고용 분석 도구이며 투자 권유가 아닙니다. 과거 통계는 미래를 보장하지 않아요.

## 화면 구성

| 탭 | 내용 |
|---|---|
| 시장 개요 | 한국·미국 지수, 금리·환율·유가·VIX의 현재값과 1일·1주·1개월·3개월 변화 |
| 흐름 점수·전망 | 요인별 진단(추세, 모멘텀, RSI, VIX, 금리, 유가, 환율, 반도체), 점수 추이, 비슷한 국면 이후 N거래일 수익률 분포, 점수 검증표 |
| 지수 차트 | 여러 지표를 시작일=100으로 맞춰 비교, 이동평균선(20·60·120일) |
| 시장 간 연결 | 선택한 시장과 다른 지표의 60일 상관계수 |
| 한국 수급 | 코스피 외국인·기관·개인 순매수와 누적 추이 (pykrx) |

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
├── app.py            # 화면 (Streamlit)
├── analysis.py       # 흐름 점수, 전망 통계, 상관관계
├── data.py           # 데이터 수집 (yfinance, pykrx)
├── config.py         # 티커와 설정값
├── requirements.txt  # 필요한 파이썬 패키지
└── .streamlit/config.toml  # 화면 테마
```

## 데이터 출처
- 지수·금리·환율·유가·VIX: Yahoo Finance (`yfinance`). 지연 시세일 수 있어요.
- 코스피 투자자별 순매수: 한국거래소 (`pykrx`).
