"""한·미 시장 흐름 분석 웹 앱 (Streamlit).

실행:  streamlit run app.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analysis as an
from config import CACHE_TTL, FORWARD_DAYS, KOREA, MACRO, SCORE_TARGETS, TICKERS, US, name
from data import load_investor_flows, load_prices

st.set_page_config(page_title="한·미 시장 흐름", page_icon="📈", layout="wide")

UP, DOWN, MUTED = "#2E7D5B", "#C0392B", "#8A8F98"


@st.cache_data(ttl=CACHE_TTL, show_spinner="시장 데이터를 불러오는 중…")
def get_prices(period: str):
    return load_prices(period)


@st.cache_data(ttl=CACHE_TTL, show_spinner="투자자별 수급을 불러오는 중…")
def get_flows():
    return load_investor_flows()


def fmt_change(v: float, unit: str) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:+.2f}{unit}"


# ── 사이드바 ─────────────────────────────────────────────
with st.sidebar:
    st.header("설정")
    target = st.selectbox("분석할 시장", list(SCORE_TARGETS), format_func=lambda t: SCORE_TARGETS[t])
    fwd = st.slider("전망 기간 (거래일)", 5, 60, FORWARD_DAYS, step=5,
                    help="과거 비슷한 국면 이후 며칠 뒤 수익률을 볼지 정해요. 20거래일 ≈ 1개월.")
    period = st.selectbox("불러올 기간", ["3y", "6y", "10y"], index=1,
                          format_func=lambda x: {"3y": "3년", "6y": "6년", "10y": "10년"}[x],
                          help="길수록 '과거 비슷한 국면' 표본이 많아져요.")
    if st.button("데이터 새로고침"):
        st.cache_data.clear()
    st.caption("이 앱은 참고용 분석 도구이며 투자 권유가 아닙니다.")

prices, source_note = get_prices(period)
if "샘플" in source_note:
    st.warning(source_note)

factors = an.build_factors(prices, target)
score = an.flow_score(factors)
now_score = float(score.dropna().iloc[-1])
ol = an.outlook(prices[target], score, fwd)
last_day = prices[target].dropna().index[-1].date()

# ── 헤더 ─────────────────────────────────────────────────
st.title("한·미 시장 흐름")
st.caption(f"기준일 {last_day} · 데이터: {source_note}")

c1, c2, c3 = st.columns([1, 1, 2])
c1.metric(f"{SCORE_TARGETS[target]} 흐름 점수", f"{now_score:+.1f}", help="−10(강한 약세) ~ +10(강한 강세)")
c2.metric("국면", an.regime(now_score))
sim = ol["similar"]
if sim.get("n", 0) >= 20:
    c3.markdown(
        f"**과거 비슷한 점수였던 {sim['n']:,}일**을 보면 {fwd}거래일 뒤 "
        f"평균 **{sim['mean']:+.1f}%**, 오를 확률 **{sim['up']:.0f}%** "
        f"(전체 평균 {ol['base']['mean']:+.1f}%, {ol['base']['up']:.0f}%)였어요."
    )
else:
    c3.markdown("비슷한 점수였던 과거 사례가 적어 통계 전망을 내기 어려워요.")

tab_over, tab_score, tab_chart, tab_corr, tab_flow = st.tabs(
    ["시장 개요", "흐름 점수·전망", "지수 차트", "시장 간 연결", "한국 수급"])

# ── 1. 시장 개요 ─────────────────────────────────────────
with tab_over:
    for title, group in [("한국", KOREA), ("미국", US), ("금리·환율·유가·변동성", MACRO)]:
        st.subheader(title)
        tbl = an.change_table(prices, group)
        cols = st.columns(max(len(tbl), 1))
        for col, (_, r) in zip(cols, tbl.iterrows()):
            val = f"{r['현재']:.2f}" if r["티커"] in an.RATE_TICKERS else f"{r['현재']:,.2f}"
            col.metric(r["지표"], val, fmt_change(r["1일"], r["단위"]),
                       delta_color="inverse" if r["티커"] in ("^VIX", "^TNX", "KRW=X", "CL=F") else "normal")
        show = tbl.drop(columns=["티커"]).copy()
        for k in ["1일", "1주", "1개월", "3개월"]:
            show[k] = [fmt_change(v, u) for v, u in zip(show[k], show["단위"])]
        st.dataframe(show.drop(columns=["단위"]), hide_index=True, use_container_width=True,
                     column_config={"현재": st.column_config.NumberColumn(format="%.2f")})
    st.caption("금리는 %p(포인트) 변화, 나머지는 % 변화예요. VIX·금리·환율·유가는 오르면 주식에 부담이라 색을 반대로 표시해요.")

# ── 2. 흐름 점수·전망 ────────────────────────────────────
with tab_score:
    st.subheader("요인별 진단")
    i = -1
    rows = []
    for f in factors:
        sig = float(f.series.iloc[i]) if not pd.isna(f.series.iloc[i]) else 0.0
        rows.append({"요인": f.label, "기여": sig * f.weight, "설명": f.explain(len(prices) - 1)})
    fdf = pd.DataFrame(rows)
    fig = go.Figure(go.Bar(x=fdf["기여"], y=fdf["요인"], orientation="h",
                           marker_color=[UP if v > 0 else DOWN if v < 0 else MUTED for v in fdf["기여"]],
                           text=[f"{v:+.1f}" for v in fdf["기여"]], textposition="outside"))
    fig.update_layout(height=60 + 40 * len(fdf), margin=dict(l=10, r=40, t=10, b=10),
                      xaxis_title="점수 기여 (오른쪽 = 상승 요인)", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, use_container_width=True)
    for r in rows:
        st.markdown(f"- **{r['요인']}**: {r['설명']}")

    st.subheader("흐름 점수 추이")
    hist = pd.DataFrame({"흐름 점수": score, SCORE_TARGETS[target]: prices[target]}).dropna().tail(250)
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=hist.index, y=hist[SCORE_TARGETS[target]], name=SCORE_TARGETS[target],
                              line=dict(color="#3B6FB6", width=2)))
    fig2.add_trace(go.Bar(x=hist.index, y=hist["흐름 점수"], name="흐름 점수", yaxis="y2",
                          marker_color=[UP if v > 0 else DOWN for v in hist["흐름 점수"]], opacity=0.35))
    fig2.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h"),
                       yaxis=dict(title=SCORE_TARGETS[target]),
                       yaxis2=dict(title="점수", overlaying="y", side="right", range=[-10, 10]))
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader(f"전망: 비슷한 국면 이후 {fwd}거래일 수익률")
    if sim.get("n", 0) >= 20:
        a, b, c, d = st.columns(4)
        a.metric("평균", f"{sim['mean']:+.1f}%")
        b.metric("중간값", f"{sim['median']:+.1f}%")
        c.metric("오를 확률", f"{sim['up']:.0f}%")
        d.metric("범위 (하위 10%~상위 10%)", f"{sim['p10']:+.1f}% ~ {sim['p90']:+.1f}%")
        fig3 = px.histogram(ol["dist"], nbins=40, labels={"value": f"{fwd}거래일 뒤 수익률 (%)"})
        fig3.add_vline(x=0, line_dash="dash", line_color=MUTED)
        fig3.update_layout(height=280, showlegend=False, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="일수")
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("비슷한 점수의 과거 사례가 20일 미만이에요. 불러올 기간을 늘려 보세요.")

    with st.expander("이 점수가 과거에 실제로 맞았나요? (검증)"):
        st.dataframe(an.score_buckets(prices[target], score, fwd), hide_index=True, use_container_width=True,
                     column_config={"평균 수익률(%)": st.column_config.NumberColumn(format="%+.2f"),
                                    "상승 확률(%)": st.column_config.NumberColumn(format="%.0f")})
        st.caption("점수가 높은 구간일수록 이후 수익률·상승 확률이 높다면 점수에 의미가 있다는 뜻이에요. "
                   "과거 통계는 미래를 보장하지 않아요.")

# ── 3. 지수 차트 ─────────────────────────────────────────
with tab_chart:
    pick = st.multiselect("비교할 지표", list(TICKERS), default=["^KS11", "^GSPC", "^SOX"], format_func=name)
    span = st.radio("기간", ["3개월", "6개월", "1년", "3년"], index=2, horizontal=True)
    n = {"3개월": 63, "6개월": 126, "1년": 252, "3년": 756}[span]
    if pick:
        sub = prices[pick].dropna(how="all").tail(n)
        norm = sub / sub.bfill().iloc[0] * 100
        norm.columns = [name(t) for t in norm.columns]
        fig4 = px.line(norm, labels={"value": "시작일 = 100", "index": "", "variable": ""})
        fig4.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h"))
        st.plotly_chart(fig4, use_container_width=True)
        st.caption("서로 다른 지표를 비교하기 쉽게 시작일을 100으로 맞췄어요.")

    st.subheader(f"{SCORE_TARGETS[target]} 이동평균선")
    p = prices[target].dropna().tail(n)
    full = prices[target].dropna()
    ma = pd.DataFrame({"종가": p, "20일선": full.rolling(20).mean().tail(n), "60일선": full.rolling(60).mean().tail(n),
                       "120일선": full.rolling(120).mean().tail(n)})
    fig5 = px.line(ma, labels={"value": "", "index": "", "variable": ""})
    fig5.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h"))
    st.plotly_chart(fig5, use_container_width=True)

# ── 4. 시장 간 연결 ──────────────────────────────────────
with tab_corr:
    st.markdown(f"**{SCORE_TARGETS[target]}**가 다른 시장과 얼마나 같이 움직이는지(60일 상관계수, −1~+1)예요. "
                "+1에 가까우면 같은 방향, −1에 가까우면 반대 방향으로 움직여요.")
    others = [t for t in TICKERS if t != target]
    rc = an.rolling_corr(prices, target, others).tail(500)
    if not rc.empty:
        latest = rc.iloc[-1].sort_values()
        fig6 = go.Figure(go.Bar(x=latest.values, y=latest.index, orientation="h",
                                marker_color=[UP if v > 0 else DOWN for v in latest.values],
                                text=[f"{v:+.2f}" for v in latest.values], textposition="outside"))
        fig6.update_layout(height=420, margin=dict(l=10, r=40, t=10, b=10), xaxis=dict(range=[-1, 1]))
        st.plotly_chart(fig6, use_container_width=True)
        default = [c for c in rc.columns if c in (name("^GSPC"), name("^SOX"), name("KRW=X"))][:3] or list(rc.columns[:3])
        chosen = st.multiselect("추이 보기", list(rc.columns), default=default)
        if chosen:
            fig7 = px.line(rc[chosen], labels={"value": "상관계수", "index": "", "variable": ""})
            fig7.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h"))
            st.plotly_chart(fig7, use_container_width=True)
    st.caption("한국 시장은 시차 때문에 전날 밤 미국 시장의 영향을 다음 날 받아요. 같은 날짜 상관계수는 실제보다 낮게 나올 수 있어요.")

# ── 5. 한국 수급 ─────────────────────────────────────────
with tab_flow:
    flows, flow_note = get_flows()
    if flows is None:
        st.info(flow_note + "\n\n`pip install pykrx`로 설치했는지 확인해 주세요. 한국거래소 사이트 정책에 따라 막힐 수도 있어요.")
    else:
        st.caption(f"코스피 투자자별 순매수 (단위: 억 원) · 출처: {flow_note}")
        f = flows / 1e8
        fig8 = go.Figure()
        for col, color in [("외국인", "#3B6FB6"), ("기관", "#E39B2D"), ("개인", MUTED)]:
            if col in f:
                fig8.add_trace(go.Bar(x=f.index, y=f[col], name=col, marker_color=color))
        fig8.update_layout(barmode="relative", height=360, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h"))
        st.plotly_chart(fig8, use_container_width=True)
        cum = f.cumsum()
        fig9 = px.line(cum, labels={"value": "누적 순매수 (억 원)", "index": "", "variable": ""})
        fig9.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h"))
        st.plotly_chart(fig9, use_container_width=True)
        s20 = f.tail(20).sum()
        st.markdown(" · ".join(f"최근 20일 {k} **{v:+,.0f}억 원**" for k, v in s20.items()))
