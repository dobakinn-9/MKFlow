"""심리·가격 수준: 과열/과매도 / 밸류에이션 / 시장 간 연결."""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analysis as an
import common as cm
from config import KOREA, TICKERS, US, name


def overheat():
    st.title("과열·과매도 (RSI)")
    cm.explain("""
- **RSI**는 최근 14일 동안 오른 폭과 내린 폭을 비교한 0~100 지표예요.
- **70 이상**: 짧은 기간에 많이 올라 과열 → 숨 고르기 가능성
- **30 이하**: 짧은 기간에 많이 내려 과매도 → 기술적 반등 가능성
- 강한 상승장에서는 70 위에 오래 머물 수 있어서, 단독 신호보다는 추세와 함께 보세요.
""")
    p = cm.prices()
    rows = []
    for t in KOREA + US:
        if t in p:
            r = an.rsi(p[t].dropna())
            rows.append({"지표": name(t), "RSI": r.iloc[-1]})
    import pandas as pd
    tbl = pd.DataFrame(rows).sort_values("RSI")
    fig = go.Figure(go.Bar(x=tbl["RSI"], y=tbl["지표"], orientation="h",
                           marker_color=[cm.DOWN if v > 70 else cm.UP if v < 30 else cm.MUTED for v in tbl["RSI"]],
                           text=[f"{v:.0f}" for v in tbl["RSI"]], textposition="outside"))
    for x in (30, 70):
        fig.add_vline(x=x, line_dash="dot", line_color=cm.MUTED)
    fig.update_layout(xaxis=dict(range=[0, 100]), hovermode=False, height=60 + 40 * len(tbl), margin=dict(l=10, r=40, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("초록 = 과매도(30 이하), 빨강 = 과열(70 이상)")

    st.subheader(f"{cm.target_name()} RSI 추이")
    n = cm.span_picker("rsi_span")
    r = an.rsi(p[cm.target()].dropna()).tail(n)
    fig2 = go.Figure(go.Scatter(x=r.index, y=r, line=dict(color=cm.BLUE, width=2)))
    for y in (30, 70):
        fig2.add_hline(y=y, line_dash="dot", line_color=cm.MUTED)
    fig2.update_yaxes(range=[0, 100])
    cm.show(fig2, 280)
    cm.source(cm.price_note())


def valuation():
    st.title("밸류에이션 (PER·PBR)")
    cm.explain("""
- **PER**(주가수익비율) = 주가 ÷ 1주당 이익. 높을수록 이익에 비해 비싸게 거래된다는 뜻이에요.
- **PBR**(주가순자산비율) = 주가 ÷ 1주당 순자산. 코스피는 오랫동안 1배 안팎에서 움직였어요.
- 지금 값이 **과거 5년 중 어느 위치(백분위)**인지가 중요해요. 상위권이면 작은 악재에도 크게 흔들리기 쉬워요.
- 이익이 급변하는 시기(예: 반도체 호황·불황)에는 PER이 왜곡될 수 있어요.
""")
    nm = st.radio("지수", ["코스피", "코스닥"], horizontal=True, key="val_idx")
    df, note = cm.kr_fundamental(nm)
    if df is None:
        st.info(note)
        return
    cols = st.columns(len(df.columns))
    for col, c in zip(cols, df.columns):
        s = df[c].dropna()
        if s.empty:
            continue
        col.metric(c, f"{s.iloc[-1]:.2f}" + ("%" if c == "배당수익률" else "배"),
                   help=f"과거 5년 중 하위 {an.percentile_rank(s):.0f}% 위치")
    for c in [c for c in ("PER", "PBR") if c in df]:
        s = df[c].dropna()
        st.subheader(f"{nm} {c} 추이")
        fig = go.Figure(go.Scatter(x=s.index, y=s, line=dict(color=cm.BLUE, width=2), name=c))
        fig.add_hline(y=s.mean(), line_dash="dash", line_color=cm.MUTED, annotation_text=f"5년 평균 {s.mean():.2f}")
        cm.show(fig, 280)
        pr = an.percentile_rank(s)
        st.markdown(f"현재 {c}는 과거 5년 중 **하위 {pr:.0f}%** 위치예요 → " +
                    ("역사적으로 **비싼 편**이에요." if pr > 80 else "역사적으로 **싼 편**이에요." if pr < 20 else "평균 범위예요."))
    cm.source(note)
    st.caption("미국 지수의 PER은 무료 데이터로 안정적으로 받기 어려워 한국 지수만 보여드려요.")


def links():
    st.title("시장 간 연결 (상관관계)")
    t, nm = cm.target(), cm.target_name()
    cm.explain(f"""
- **{nm}**가 다른 시장과 얼마나 같은 방향으로 움직이는지 보여줘요(최근 60거래일 상관계수, −1 ~ +1).
- +1에 가까우면 같이 오르내리고, −1에 가까우면 반대로 움직여요.
- 한국 시장은 시차 때문에 전날 밤 미국 시장의 영향을 다음 날 받아서, 같은 날짜 기준 상관계수는 실제보다 낮게 나올 수 있어요.
""")
    p = cm.prices()
    rc = an.rolling_corr(p, t, [x for x in TICKERS if x != t]).tail(500)
    if rc.empty:
        st.info("상관관계를 계산할 데이터가 부족해요.")
        return
    latest = rc.iloc[-1].sort_values()
    st.plotly_chart(cm.hbar(latest.index, latest.values, "{:+.2f}", xrange=[-1, 1]), use_container_width=True)
    default = [c for c in rc.columns if c in (name("^GSPC"), name("^SOX"), name("KRW=X"))][:3] or list(rc.columns[:3])
    chosen = st.multiselect("추이 보기", list(rc.columns), default=default)
    if chosen:
        cm.show(px.line(rc[chosen], labels={"value": "상관계수", "index": "", "variable": ""}), 320)
    cm.source(cm.price_note())
