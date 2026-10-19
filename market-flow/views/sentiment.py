"""심리·가격 수준: 공포·탐욕 지수 / 과열·과매도 / 밸류에이션 / 시장 간 연결."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analysis as an
import common as cm
from config import KOREA, TICKERS, US, name

FG_COLORS = [(25, "#E5534B"), (45, "#F0A33A"), (55, "#9AA0A6"), (75, "#8BC34A"), (101, "#3FB97F")]


def _fg_color(v: float) -> str:
    for th, c in FG_COLORS:
        if v < th:
            return c
    return FG_COLORS[-1][1]


@st.cache_data(ttl=1800)
def _fg(market: str, period: str):
    return an.fear_greed(cm.prices(), market)


def _gauge(v: float, title: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=v, number={"font": {"size": 42}},
        title={"text": f"{title}<br><span style='font-size:0.8em'>{an.fg_label(v)}</span>"},
        gauge={"axis": {"range": [0, 100], "tickvals": [0, 25, 45, 55, 75, 100]},
               "bar": {"color": _fg_color(v)},
               "steps": [{"range": [0, 25], "color": "rgba(229,83,75,0.18)"},
                         {"range": [25, 45], "color": "rgba(240,163,58,0.15)"},
                         {"range": [45, 55], "color": "rgba(154,160,166,0.15)"},
                         {"range": [55, 75], "color": "rgba(139,195,74,0.15)"},
                         {"range": [75, 100], "color": "rgba(63,185,127,0.18)"}]}))
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=70, b=0))
    return fig


def fear_greed():
    st.title("공포·탐욕 지수")
    cm.explain("""
- 시장 참여자들이 지금 **겁을 먹었는지(공포)**, **들떠 있는지(탐욕)**를 0~100으로 나타낸 지수예요. 미국 CNN의 같은 이름 지수를 참고해 직접 계산했어요.
- 각 구성요소를 **최근 1년 중 어느 위치인지**로 0~100점을 매기고 평균을 내요.
- 0~25 **극단적 공포** · 25~45 공포 · 45~55 중립 · 55~75 탐욕 · 75~100 **극단적 탐욕**
- 워런 버핏의 말처럼 "남들이 탐욕스러울 때 두려워하고, 두려워할 때 탐욕스러워라" — 극단 구간은 **반대로 움직일 가능성**을 살펴보는 참고 신호예요. 아래 표에서 과거에 실제로 그랬는지 확인할 수 있어요.
""")
    period = cm.period()
    us, kr = _fg("US", period), _fg("KR", period)
    a, b = st.columns(2)
    for col, df, title in [(a, us, "미국"), (b, kr, "한국")]:
        with col:
            if df.empty:
                st.info(f"{title} 지수를 계산할 데이터가 부족해요.")
                continue
            now = df["종합"].iloc[-1]
            st.plotly_chart(_gauge(now, title), use_container_width=True)
            prev_w = df["종합"].iloc[-6] if len(df) > 6 else now
            prev_m = df["종합"].iloc[-22] if len(df) > 22 else now
            st.caption(f"1주 전 {prev_w:.0f} ({an.fg_label(prev_w)}) · 1개월 전 {prev_m:.0f} ({an.fg_label(prev_m)})")

    mkt = st.radio("자세히 볼 시장", ["미국", "한국"], horizontal=True, key="fg_mkt")
    df = us if mkt == "미국" else kr
    if df.empty:
        return
    comp = df.drop(columns=["종합"]).iloc[-1].dropna().sort_values()

    st.subheader("구성요소별 점수")
    fig = go.Figure(go.Bar(x=comp.values, y=comp.index, orientation="h",
                           marker_color=[_fg_color(v) for v in comp.values],
                           text=[f"{v:.0f}" for v in comp.values], textposition="outside"))
    fig.add_vline(x=50, line_dash="dot", line_color=cm.MUTED)
    fig.update_layout(xaxis=dict(range=[0, 105]), hovermode=False, height=60 + 42 * len(comp),
                      margin=dict(l=10, r=40, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
    hot = [k for k, v in comp.items() if v >= 75]
    cold = [k for k, v in comp.items() if v <= 25]
    if hot:
        st.markdown("🟢 **탐욕 쪽으로 쏠린 요소**: " + ", ".join(hot))
    if cold:
        st.markdown("🔴 **공포 쪽으로 쏠린 요소**: " + ", ".join(cold))

    st.subheader("추이")
    n = cm.span_picker("fg_span")
    h = df["종합"].tail(n)
    t = "^GSPC" if mkt == "미국" else "^KS11"
    pr = cm.prices()[t].reindex(h.index)
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=h.index, y=h, name="공포·탐욕", line=dict(color=cm.ORANGE, width=2)))
    fig2.add_trace(go.Scatter(x=pr.index, y=pr, name=name(t) + " (오른쪽)", yaxis="y2", line=dict(color=cm.BLUE, width=1.5)))
    for y in (25, 75):
        fig2.add_hline(y=y, line_dash="dot", line_color=cm.MUTED)
    fig2.update_layout(yaxis=dict(range=[0, 100], title="공포 ← → 탐욕"),
                       yaxis2=dict(overlaying="y", side="right", title=name(t)))
    cm.show(fig2, 360)

    fwd = cm.fwd()
    st.subheader(f"'공포에 사라'는 통했을까? ({fwd}거래일 뒤 수익률)")
    st.dataframe(an.fg_buckets(cm.prices()[t], df["종합"], fwd), hide_index=True, use_container_width=True,
                 column_config={"평균 수익률(%)": st.column_config.NumberColumn(format="%+.2f"),
                                "상승 확률(%)": st.column_config.NumberColumn(format="%.0f")})
    st.caption("극단적 공포 구간의 이후 수익률이 높았다면, 과거에는 공포가 매수 기회였다는 뜻이에요. 과거 통계는 미래를 보장하지 않아요.")
    cm.source(cm.price_note())


def overheat():
    st.title("과열·과매도")
    cm.explain("""
- **RSI**: 최근 14일 오른 폭과 내린 폭의 비율(0~100). **70 이상 과열, 30 이하 과매도**예요.
- **이격도**: 현재가 ÷ 이동평균 × 100. 100보다 크면 평균보다 위에 있다는 뜻이에요. 20일 이격도가 **105~110 이상**이면 단기 과열, **90~95 이하**면 단기 과매도로 많이 봐요.
- **52주 고점·저점 대비**: 1년 중 가장 비쌌던·쌌던 가격에서 얼마나 떨어져 있는지예요. 고점 대비 −10% 이상이면 '조정', −20% 이상이면 '약세장'이라고 불러요.
- **연속 상승·하락일**: 며칠 연속 같은 방향으로 움직였는지예요. 너무 길게 이어지면 되돌림이 나오기 쉬워요.
- 강한 상승장에서는 과열 상태가 오래 이어질 수 있어서, 단독 신호보다는 추세와 함께 보세요.
""")
    p = cm.prices()
    tbl = an.stretch_table(p, KOREA + US)
    if tbl.empty:
        st.info("데이터가 부족해요.")
        return

    def status(r):
        tags = []
        if r["RSI"] >= 70 or r["이격도 20일"] >= 106:
            tags.append("🔴 과열")
        if r["RSI"] <= 30 or r["이격도 20일"] <= 94:
            tags.append("🟢 과매도")
        if r["52주 고점 대비(%)"] <= -20:
            tags.append("약세장 구간")
        elif r["52주 고점 대비(%)"] <= -10:
            tags.append("조정 구간")
        return " · ".join(tags) or "⚪ 보통"

    tbl["상태"] = tbl.apply(status, axis=1)
    tbl["연속"] = tbl["연속(일)"].map(lambda v: f"{abs(int(v))}일 {'상승' if v > 0 else '하락' if v < 0 else '보합'}")
    st.subheader("한눈에 보는 과열 판단표")
    st.dataframe(tbl[["지표", "상태", "RSI", "이격도 20일", "이격도 60일", "52주 고점 대비(%)", "52주 저점 대비(%)", "연속"]],
                 hide_index=True, use_container_width=True,
                 column_config={"RSI": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
                                "이격도 20일": st.column_config.NumberColumn(format="%.1f"),
                                "이격도 60일": st.column_config.NumberColumn(format="%.1f"),
                                "52주 고점 대비(%)": st.column_config.NumberColumn(format="%+.1f%%"),
                                "52주 저점 대비(%)": st.column_config.NumberColumn(format="%+.1f%%")})

    st.subheader("52주 범위 안의 현재 위치")
    pos = []
    for t in KOREA + US:
        if t in p and not p[t].dropna().empty:
            y = p[t].dropna().tail(252)
            pos.append((name(t), (y.iloc[-1] - y.min()) / (y.max() - y.min()) * 100 if y.max() > y.min() else 50))
    pos = pd.DataFrame(pos, columns=["지표", "위치"]).sort_values("위치")
    fig = go.Figure(go.Bar(x=pos["위치"], y=pos["지표"], orientation="h",
                           marker_color=[cm.DOWN if v > 85 else cm.UP if v < 15 else cm.MUTED for v in pos["위치"]],
                           text=[f"{v:.0f}%" for v in pos["위치"]], textposition="outside"))
    fig.update_layout(xaxis=dict(range=[0, 110], title="0% = 52주 최저 · 100% = 52주 최고"), hovermode=False,
                      height=60 + 40 * len(pos), margin=dict(l=10, r=40, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader(f"{cm.target_name()} RSI와 이격도 추이")
    n = cm.span_picker("rsi_span")
    s = p[cm.target()].dropna()
    r = an.rsi(s).tail(n)
    disp = (s / s.rolling(20).mean() * 100).tail(n)
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=r.index, y=r, name="RSI", line=dict(color=cm.BLUE, width=2)))
    fig2.add_trace(go.Scatter(x=disp.index, y=disp, name="이격도 20일 (오른쪽)", yaxis="y2", line=dict(color=cm.ORANGE, width=1.5)))
    for y in (30, 70):
        fig2.add_hline(y=y, line_dash="dot", line_color=cm.MUTED)
    fig2.update_layout(yaxis=dict(range=[0, 100], title="RSI"), yaxis2=dict(overlaying="y", side="right", title="이격도"))
    cm.show(fig2, 320)
    cm.source(cm.price_note())


def valuation():
    st.title("밸류에이션 (비싼가, 싼가)")
    cm.explain("""
- **PER**(주가수익비율) = 주가 ÷ 1주당 이익. 높을수록 이익에 비해 비싸게 거래된다는 뜻이에요.
- **PBR**(주가순자산비율) = 주가 ÷ 1주당 순자산. 코스피는 오랫동안 1배 안팎에서 움직였어요.
- 지금 값이 **과거 5년 중 어느 위치(백분위)**인지가 중요해요. 상위권이면 작은 악재에도 크게 흔들리기 쉬워요.
- PER·PBR을 불러오지 못하면 **가격 위치**(5년 범위 중 위치, 200일선 대비 거리)로 대신 보여줘요. 이건 이익을 반영하지 않은 단순 비교라 참고용이에요.
""")
    st.subheader("가격 위치로 본 비싸고 싼 정도")
    p = cm.prices()
    pp = an.price_position(p, KOREA + US)
    if not pp.empty:
        pp["판단"] = pp["5년 범위 중 위치(%)"].map(lambda v: "🔴 5년 중 높은 편" if v >= 80 else "🟢 5년 중 낮은 편" if v <= 20 else "⚪ 중간")
        st.dataframe(pp, hide_index=True, use_container_width=True,
                     column_config={"5년 범위 중 위치(%)": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
                                    "200일선 대비(%)": st.column_config.NumberColumn(format="%+.1f%%")})
        st.caption("200일선 대비 +15% 이상이면 장기 평균보다 많이 올라 있다는 뜻이고, −15% 이하면 많이 빠져 있다는 뜻이에요.")

    st.subheader("한국 지수 PER·PBR")
    nm = st.radio("지수", ["코스피", "코스닥"], horizontal=True, key="val_idx")
    df, note = cm.kr_fundamental(nm)
    if df is None:
        st.info(note + "\n\n한국거래소 접속이 막히면 PER·PBR은 비어 있어요. 위의 가격 위치를 참고해 주세요.")
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
        st.markdown(f"**{nm} {c} 추이**")
        fig = go.Figure(go.Scatter(x=s.index, y=s, line=dict(color=cm.BLUE, width=2), name=c))
        fig.add_hline(y=s.mean(), line_dash="dash", line_color=cm.MUTED, annotation_text=f"5년 평균 {s.mean():.2f}")
        cm.show(fig, 260)
        pr = an.percentile_rank(s)
        st.markdown(f"현재 {c}는 과거 5년 중 **하위 {pr:.0f}%** 위치예요 → " +
                    ("역사적으로 **비싼 편**이에요." if pr > 80 else "역사적으로 **싼 편**이에요." if pr < 20 else "평균 범위예요."))
    cm.source(note)


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
