"""한·미 시장 흐름 분석 웹 앱 (Streamlit).

실행:  streamlit run app.py

왼쪽 메뉴는 6개 분류와 그 아래 세부 메뉴로 나뉘어 있어요.
  종합 / AI 예측 / 시장 보고서 / 돈의 가격 / 시장의 체력 / 수급 / 심리·가격 수준 / 일정
"""
from __future__ import annotations

import sys

import streamlit as st

# Streamlit Cloud는 코드를 새로 올려도 예전에 불러온 모듈을 기억해 둘 때가 있어요.
# 그러면 새로 추가한 설정을 못 찾아 ImportError가 나요. 매번 우리 파일을 새로 읽도록 지워 둬요.
_LOCAL = {"config", "data", "analysis", "common", "ml", "tracker", "views"}
for _m in [m for m in list(sys.modules) if m.split(".")[0] in _LOCAL]:
    del sys.modules[_m]

from config import FORWARD_DAYS, SCORE_TARGETS  # noqa: E402
from views import ai, calendar, flows, money, overview, reports, sentiment, strength

st.set_page_config(page_title="한·미 시장 흐름", page_icon="📈", layout="wide")

# ── 메뉴 (분류 → 세부 메뉴) ──────────────────────────────
P = st.Page
pages = {
    "종합": [
        P(overview.today, title="오늘의 시장", icon="🏠", url_path="today", default=True),
        P(overview.score, title="흐름 점수·전망", icon="🧭", url_path="score"),
    ],
    "AI 예측": [
        P(ai.model, title="AI 모델 예측", icon="🤖", url_path="ai-model"),
        P(ai.outlook, title="Claude 시장 전망", icon="🔮", url_path="ai-outlook"),
        P(ai.growth, title="AI 성장 기록", icon="🌱", url_path="ai-growth"),
    ],
    "시장 보고서": [
        P(reports.world, title="세계 동향 브리핑", icon="🌍", url_path="world"),
        P(reports.hidden, title="숨은 지표", icon="🔎", url_path="hidden"),
        P(money.us_reports, title="미국 경제 보고서", icon="📰", url_path="us-reports"),
    ],
    "돈의 가격": [
        P(money.rates, title="금리", icon="🏦", url_path="rates"),
        P(money.fx, title="환율·달러", icon="💱", url_path="fx"),
        P(money.commodities, title="유가·금", icon="🛢️", url_path="commodities"),
    ],
    "시장의 체력": [
        P(strength.trend, title="추세·이동평균", icon="📈", url_path="trend"),
        P(strength.breadth, title="시장의 폭", icon="📊", url_path="breadth"),
        P(strength.turnover, title="거래대금", icon="💰", url_path="turnover"),
        P(strength.volatility, title="변동성 (VIX·VKOSPI)", icon="🌪️", url_path="volatility"),
        P(strength.sectors, title="업종 순환", icon="🔄", url_path="sectors"),
    ],
    "수급": [
        P(flows.investors, title="투자자별 매매", icon="👥", url_path="investors"),
    ],
    "심리·가격 수준": [
        P(sentiment.overheat, title="과열·과매도 (RSI)", icon="🌡️", url_path="rsi"),
        P(sentiment.valuation, title="밸류에이션 (PER·PBR)", icon="⚖️", url_path="valuation"),
        P(sentiment.links, title="시장 간 연결", icon="🔗", url_path="links"),
    ],
    "일정": [
        P(calendar.events, title="이벤트 캘린더", icon="📅", url_path="events"),
    ],
}
nav = st.navigation(pages)

# ── 공통 설정 (모든 페이지 사이드바 아래쪽) ──────────────
with st.sidebar:
    st.divider()
    st.subheader("설정")
    st.selectbox("분석 기준 시장", list(SCORE_TARGETS), format_func=lambda t: SCORE_TARGETS[t], key="target",
                 help="흐름 점수·추세·RSI·상관관계 화면에서 기준이 되는 지수예요.")
    st.slider("전망 기간 (거래일)", 5, 60, FORWARD_DAYS, step=5, key="fwd",
              help="과거 비슷한 국면 이후 며칠 뒤 수익률을 볼지 정해요. 20거래일 ≈ 1개월.")
    st.selectbox("불러올 기간", ["3y", "6y", "10y"], index=1, key="period",
                 format_func=lambda x: {"3y": "3년", "6y": "6년", "10y": "10년"}[x],
                 help="길수록 '과거 비슷한 국면' 표본이 많아져요.")
    if st.button("데이터 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("참고용 분석 도구이며 투자 권유가 아닙니다.")

nav.run()
