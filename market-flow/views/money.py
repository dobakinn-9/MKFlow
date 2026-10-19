"""돈의 가격: 금리 / 환율·달러 / 유가·금 / 미국 경제 보고서."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analysis as an
import common as cm
import data as dt
from config import COMMOD, FX, RATES


def _changes(tickers):
    tbl = an.change_table(cm.prices(), tickers)
    if tbl.empty:
        return
    show = tbl.drop(columns=["티커"]).copy()
    for k in ["1일", "1주", "1개월", "3개월"]:
        show[k] = [cm.fmt_change(v, u) for v, u in zip(show[k], show["단위"])]
    st.dataframe(show.drop(columns=["단위"]), hide_index=True, use_container_width=True,
                 column_config={"현재": st.column_config.NumberColumn(format="%.2f")})


def rates():
    st.title("금리")
    cm.explain("""
- **미 10년물 금리**는 전 세계 자산 가격의 기준이에요. 오르면 주식(특히 기술·성장주)의 매력이 떨어져요.
- **장단기 금리차(10년물 − 3개월물)**가 마이너스(역전)면 과거에 경기 침체가 뒤따른 경우가 많았어요. 역전이 풀리며 다시 플러스로 돌아설 때 주식 변동성이 커지기도 해요.
- 한 달 새 0.25%p 이상 급등하면 흐름 점수에서 부담 요인으로 계산해요.
""")
    p = cm.prices()
    _changes(RATES)
    n = cm.span_picker("rates_span")
    sub = p[[t for t in RATES if t in p]].tail(n)
    fig = go.Figure()
    for t, c in zip(sub.columns, [cm.BLUE, cm.ORANGE]):
        fig.add_trace(go.Scatter(x=sub.index, y=sub[t], name=an.name(t), line=dict(color=c, width=2)))
    fig.update_yaxes(title="%")
    cm.show(fig)
    if {"^TNX", "^IRX"} <= set(p.columns):
        st.subheader("장단기 금리차 (10년물 − 3개월물)")
        spread = (p["^TNX"] - p["^IRX"]).tail(n)
        fig2 = go.Figure(go.Scatter(x=spread.index, y=spread, fill="tozeroy", line=dict(color=cm.BLUE)))
        fig2.add_hline(y=0, line_dash="dash", line_color=cm.MUTED)
        fig2.update_yaxes(title="%p")
        cm.show(fig2, 280)
        now = spread.iloc[-1]
        st.markdown(f"현재 금리차 **{now:+.2f}%p** → " + ("**역전 상태**예요. 경기 둔화 신호로 봐요." if now < 0 else "정상(플러스) 상태예요."))
    cm.source(cm.price_note())


def fx():
    st.title("환율·달러")
    cm.explain("""
- **원/달러 환율**이 오르면(원화 약세) 외국인 입장에서 한국 주식 가치가 줄어 매도 압력이 커지는 경향이 있어요.
- **달러인덱스**는 주요 통화 대비 달러 가치예요. 달러 강세는 보통 신흥국 주식에 부담이에요.
- 아래 차트에서 환율은 **거꾸로(위가 원화 강세)** 그려서 코스피와 같은 방향인지 보기 쉽게 했어요.
""")
    p = cm.prices()
    _changes(FX)
    n = cm.span_picker("fx_span")
    if {"KRW=X", "^KS11"} <= set(p.columns):
        sub = p[["KRW=X", "^KS11"]].dropna().tail(n)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=sub.index, y=sub["^KS11"], name="코스피", line=dict(color=cm.BLUE, width=2)))
        fig.add_trace(go.Scatter(x=sub.index, y=sub["KRW=X"], name="원/달러 (오른쪽, 거꾸로)", yaxis="y2",
                                 line=dict(color=cm.ORANGE, width=2)))
        fig.update_layout(yaxis=dict(title="코스피"), yaxis2=dict(title="원", overlaying="y", side="right", autorange="reversed"))
        cm.show(fig, 380)
        c = p["^KS11"].pct_change().tail(n).corr(p["KRW=X"].pct_change().tail(n))
        st.markdown(f"이 기간 코스피와 원/달러 일간 변동의 상관계수는 **{c:+.2f}**예요. 마이너스일수록 '환율 오르면 코스피 내림' 관계가 강해요.")
    if "DX-Y.NYB" in p:
        st.subheader("달러인덱스")
        d = p["DX-Y.NYB"].tail(n)
        cm.show(go.Figure(go.Scatter(x=d.index, y=d, line=dict(color=cm.BLUE, width=2))), 260)
    cm.source(cm.price_note())


def commodities():
    st.title("유가·금")
    cm.explain("""
- **유가(WTI)**가 급등하면 물가를 밀어 올려 금리 인상 압력이 커져요. 한 달 새 10% 넘게 오르면 흐름 점수에서 부담 요인이에요.
- **금**은 대표적인 안전자산이에요. 주식과 함께 금이 급등하면 불안 심리가 섞인 상승일 수 있어요.
""")
    p = cm.prices()
    _changes(COMMOD)
    n = cm.span_picker("cmd_span")
    if {"CL=F", "^TNX"} <= set(p.columns):
        st.subheader("유가와 미국 금리")
        sub = p[["CL=F", "^TNX"]].dropna().tail(n)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=sub.index, y=sub["CL=F"], name="WTI ($)", line=dict(color=cm.ORANGE, width=2)))
        fig.add_trace(go.Scatter(x=sub.index, y=sub["^TNX"], name="미 10년물 (%) 오른쪽", yaxis="y2", line=dict(color=cm.BLUE, width=2)))
        fig.update_layout(yaxis=dict(title="$"), yaxis2=dict(title="%", overlaying="y", side="right"))
        cm.show(fig, 360)
    if "GC=F" in p:
        st.subheader("금")
        g = p["GC=F"].tail(n)
        cm.show(go.Figure(go.Scatter(x=g.index, y=g, line=dict(color="#C9A227", width=2))), 260)
    cm.source(cm.price_note())


def us_reports():
    st.title("미국 경제 보고서")
    st.caption("미국 정부·연준의 최근 공식 보고서를 한국어로 요약했어요. 새 보고서가 나오면 요청하시면 갱신해 드려요.")
    reps, note = dt.load_us_reports()
    if not reps:
        st.info(note)
        return
    reps = sorted(reps, key=lambda r: r.get("released", ""), reverse=True)
    for i in range(0, len(reps), 2):
        cols = st.columns(2)
        for col, r in zip(cols, reps[i:i + 2]):
            with col.container(border=True):
                st.caption(f"{r['org']} · {r['released']} 발표")
                st.markdown(f"#### {r['report']}")
                st.metric(r["tile"], f"{r['value']:g}{'' if r['unit'] in ('%',) else ' '}{r['unit']}")
                st.markdown("\n".join(f"- {x}" for x in str(r["points"]).split(" · ")))
                st.info("시장 의미: " + r["impact"])
                if str(r.get("url", "")).startswith("https://"):
                    st.markdown(f"[원문 보기 →]({r['url']})")
    cm.source(note)
