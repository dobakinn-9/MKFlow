"""돈의 가격: 금리 / 환율·달러 / 유가·금 / 미국 경제 보고서."""
from __future__ import annotations

import json

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


US_AUTO = [  # (FRED 코드, 이름, 표시 방식, 단위, 좋은 방향) — 발표되면 자동으로 최신값이 들어와요
    ("ICSA", "신규 실업수당 청구 (주간)", "level_k", "천 건", "down"),
    ("UNRATE", "실업률", "level", "%", "down"),
    ("PAYEMS", "비농업 일자리 증가", "diff_k", "천 명", "up"),
    ("CPIAUCSL", "CPI (전년비)", "yoy", "%", "down"),
    ("CPILFESL", "근원 CPI (전년비)", "yoy", "%", "down"),
    ("PCEPILFE", "근원 PCE (전년비)", "yoy", "%", "down"),
    ("RSAFS", "소매판매 (전월비)", "mom", "%", "up"),
    ("INDPRO", "산업생산 (전월비)", "mom", "%", "up"),
    ("UMCSENT", "미시간대 소비자심리", "level", "", "up"),
    ("HOUST", "주택 착공 (연율)", "level_k", "천 호", "up"),
]


@st.cache_data(ttl=3600 * 3, show_spinner="미국 공식 통계(FRED)를 불러오는 중…")
def _us_auto():
    return dt.load_fred([c for c, *_ in US_AUTO])


def _auto_value(s, how):
    s = s.dropna()
    if how == "yoy":
        v = (s / s.shift(12) - 1) * 100
    elif how == "mom":
        v = s.pct_change() * 100
    elif how == "diff_k":
        v = s.diff()
    elif how == "level_k":
        v = s / 1000 if s.median() > 10000 else s
    else:
        v = s
    v = v.dropna()
    return v


def us_reports():
    st.title("미국 경제 보고서")
    meta_f = dt.DATA_DIR / "us_reports_meta.json"
    meta = json.loads(meta_f.read_text(encoding="utf-8")) if meta_f.exists() else {}
    st.caption("미국 정부·연준의 공식 보고서를 한국어로 요약했어요. 매일 아침 새 발표를 확인해 갱신해요."
               + (f" · 마지막 확인 **{meta['checked']}**" if meta.get("checked") else ""))

    # ── 자동 갱신 지표판 ─────────────────────
    st.subheader("주요 지표 최신값 (자동 갱신)")
    fred, fnote = _us_auto()
    if "샘플" in fnote:
        st.warning(fnote)
    rows = []
    for code, nm, how, unit, good in US_AUTO:
        s = fred.get(code)
        if s is None or s.dropna().empty:
            continue
        v = _auto_value(s, how)
        if len(v) < 2:
            continue
        last, prev = float(v.iloc[-1]), float(v.iloc[-2])
        trend = "⬆️" if last > prev else "⬇️" if last < prev else "➡️"
        better = (last < prev) if good == "down" else (last > prev)
        rows.append({"지표": nm, "최신값": last, "단위": unit, "직전": prev, "변화": f"{trend} {last - prev:+.2f}",
                     "판단": "🟢 개선" if better and last != prev else ("🔴 악화" if last != prev else "⚪ 보합"),
                     "기준 시점": v.index[-1].strftime("%Y-%m-%d" if code == "ICSA" else "%Y-%m")})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                     column_config={"최신값": st.column_config.NumberColumn(format="%.2f"),
                                    "직전": st.column_config.NumberColumn(format="%.2f")})
        st.caption("미국 노동통계국·경제분석국·연준 통계가 발표되면 FRED를 통해 자동으로 최신값이 들어와요. "
                   "실업수당 청구는 매주 목요일, 나머지는 매월 발표돼요. 출처: " + fnote)

    # ── 발표 예정 ────────────────────────────
    nxt = meta.get("upcoming") or []
    if nxt:
        st.subheader("이번 주·다음 주 발표 예정")
        st.dataframe(pd.DataFrame(nxt).rename(columns={"date": "날짜", "report": "보고서", "why": "의미"}),
                     hide_index=True, use_container_width=True)
        st.caption("매일 아침 공식 발표 일정을 확인해 갱신해요. 일정은 기관 사정에 따라 바뀔 수 있어요.")

    # ── 보고서 요약 카드 ─────────────────────
    st.subheader("최근 보고서 요약")
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
