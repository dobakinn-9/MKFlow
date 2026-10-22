"""위험선호/회피 게이지: 돈이 위험자산으로 가는지, 안전자산으로 숨는지."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analysis as an
import common as cm

WIN = 20  # 최근 20거래일(약 1개월) 상대 성과로 봐요

# (이름, 계산 방식, 설명) — 값이 클수록 '위험선호'
COMPONENTS = [
    ("주식 vs 국채", ("rel", "SPY", "IEF"), "주식이 국채보다 많이 오르면 위험을 즐기는 돈"),
    ("하이일드 vs 국채", ("rel", "HYG", "IEF"), "위험한 회사채를 사는 돈이 늘면 위험선호"),
    ("구리 vs 금", ("rel", "HG=F", "GC=F"), "경기 금속(구리)이 안전 금속(금)보다 강하면 위험선호"),
    ("공격 vs 방어 업종", ("grp", ("XLK", "XLY", "XLI"), ("XLP", "XLV", "XLU")), "기술·소비·산업재가 필수소비·헬스·유틸리티보다 강하면 위험선호"),
    ("신흥국 vs 미국", ("rel", "EEM", "SPY"), "돈이 신흥국(한국 포함)으로 가면 위험선호"),
    ("반도체 vs 시장", ("rel", "^SOX", "^GSPC"), "가장 위험한 성장주인 반도체가 강하면 위험선호"),
    ("달러 약세", ("inv", "DX-Y.NYB"), "달러가 약해지면 돈이 달러 밖 위험자산으로 나감"),
    ("원화 강세", ("inv", "KRW=X"), "원화가 강해지면 외국인 돈이 한국으로 들어옴"),
    ("엔화 약세", ("up", "JPY=X"), "안전통화 엔화가 약해지면(엔/달러 상승) 위험선호"),
    ("변동성 안정", ("vix", "^VIX"), "공포지수(VIX)가 낮고 내려가면 위험선호"),
]


def _raw(p: pd.DataFrame, how) -> pd.Series | None:
    def ok(*ts):
        return all(t in p and p[t].notna().mean() > 0.5 for t in ts)

    kind = how[0]
    if kind == "rel" and ok(how[1], how[2]):
        r = np.log(p[how[1]].ffill() / p[how[2]].ffill())
        return r - r.shift(WIN)
    if kind == "grp":
        a, b = [t for t in how[1] if ok(t)], [t for t in how[2] if ok(t)]
        if a and b:
            ra = np.log(p[a].ffill()).diff(WIN).mean(axis=1)
            rb = np.log(p[b].ffill()).diff(WIN).mean(axis=1)
            return ra - rb
    if kind == "inv" and ok(how[1]):
        return -np.log(p[how[1]].ffill()).diff(WIN)
    if kind == "up" and ok(how[1]):
        return np.log(p[how[1]].ffill()).diff(WIN)
    if kind == "vix" and ok(how[1]):
        v = p[how[1]].ffill()
        return -(v / v.rolling(50).mean())
    return None


@st.cache_data(ttl=3600)
def gauge_frame(p: pd.DataFrame) -> pd.DataFrame:
    """구성요소별 점수(0~100, 1년 중 위치)와 '종합'."""
    comp = {}
    for nm, how, _ in COMPONENTS:
        r = _raw(p, how)
        if r is not None and r.notna().sum() > 150:
            comp[nm] = an.rolling_pct(r.dropna(), 252)
    df = pd.DataFrame(comp)
    if df.empty:
        return df
    df["종합"] = df.mean(axis=1, skipna=True).ewm(span=3).mean()  # 하루 잡음 줄이기
    return df.dropna(subset=["종합"])


def label(v: float) -> tuple[str, str]:
    if v < 25:
        return "강한 위험회피", cm.DOWN
    if v < 45:
        return "위험회피", "#F97316"
    if v <= 55:
        return "중립", cm.MUTED
    if v <= 75:
        return "위험선호", "#84CC16"
    return "강한 위험선호", cm.UP


def _gauge(v: float, title: str) -> go.Figure:
    lab, col = label(v)
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=v, number={"font": {"size": 42}, "valueformat": ".0f"},
        title={"text": f"{title}<br><span style='font-size:0.85em;color:{col}'>{lab}</span>"},
        gauge={"axis": {"range": [0, 100], "tickvals": [0, 25, 45, 55, 75, 100]},
               "bar": {"color": col},
               "steps": [{"range": [0, 25], "color": "rgba(239,68,68,0.18)"},
                         {"range": [25, 45], "color": "rgba(249,115,22,0.14)"},
                         {"range": [45, 55], "color": "rgba(148,163,184,0.14)"},
                         {"range": [55, 75], "color": "rgba(132,204,22,0.14)"},
                         {"range": [75, 100], "color": "rgba(34,197,94,0.18)"}]}))
    fig.update_layout(height=270, margin=dict(l=24, r=24, t=80, b=0))
    return fig


def summary(p: pd.DataFrame) -> dict | None:
    df = gauge_frame(p)
    if df.empty or len(df) < 25:
        return None
    s = df["종합"]
    return {"now": float(s.iloc[-1]), "d1": float(s.iloc[-2]), "w1": float(s.iloc[-6]), "m1": float(s.iloc[-22]),
            "df": df}


def mini(p: pd.DataFrame):
    """첫 화면용 한 줄 카드."""
    sm = summary(p)
    if not sm:
        return
    lab, _ = label(sm["now"])
    st.metric("💹 위험선호/회피 게이지", f"{sm['now']:.0f} · {lab}", f"{sm['now'] - sm['w1']:+.0f} (1주 전 대비)")


def page():
    st.title("위험선호/회피 게이지")
    cm.explain(f"""
- 전 세계 돈이 지금 **위험자산(주식·신흥국·하이일드·구리)**으로 가는지, **안전자산(국채·금·달러·엔화)**으로 숨는지를 0~100으로 나타냈어요.
- 서로 짝을 이루는 자산 10쌍의 **최근 {WIN}거래일 상대 성과**를 각각 '최근 1년 중 어느 위치인지'로 바꿔 평균 냈어요.
- 0~25 **강한 위험회피** · 25~45 위험회피 · 45~55 중립 · 55~75 위험선호 · 75~100 **강한 위험선호**
- '공포·탐욕 지수'가 **주식시장 안의 기분**이라면, 이 게이지는 **주식·채권·원자재·통화 사이에서 돈이 어디로 움직이는지**를 봐요. 둘이 엇갈리면(예: 주가는 탐욕인데 돈은 안전자산으로) 경계 신호예요.
- 한국 증시는 위험선호 국면에서 외국인 돈이 들어오는 경향이 있어서, 이 게이지가 코스피의 '바람 방향'이에요.
""")
    p = cm.prices()
    cm.warn_if_sample(cm.price_note())
    sm = summary(p)
    if not sm:
        st.info("게이지를 계산할 자료가 부족해요. 사이드바에서 불러올 기간을 늘려 보세요.")
        return
    df = sm["df"]
    st.plotly_chart(_gauge(sm["now"], "지금 돈의 방향"), use_container_width=True)
    c1, c2, c3 = st.columns(3)
    for col, k, nm in [(c1, "d1", "어제"), (c2, "w1", "1주 전"), (c3, "m1", "1개월 전")]:
        col.metric(nm, f"{sm[k]:.0f} · {label(sm[k])[0]}", f"지금 {sm['now'] - sm[k]:+.0f}", delta_color="off")

    # 구성요소
    st.subheader("무엇이 돈의 방향을 정하고 있나")
    last = df.drop(columns="종합").iloc[-1].dropna().sort_values()
    st.plotly_chart(cm.hbar(last.index, last.values - 50, "{:+.0f}", xrange=[-60, 60]), use_container_width=True)
    st.caption("막대는 '1년 중 위치 − 50'이에요. 오른쪽(초록)은 위험선호 쪽으로, 왼쪽(빨강)은 위험회피 쪽으로 끌고 있어요.")
    desc = {nm: d for nm, _, d in COMPONENTS}
    on = [n for n in last.index[::-1] if last[n] >= 65][:3]
    off = [n for n in last.index if last[n] <= 35][:3]
    lines = []
    if on:
        lines.append("🟢 **위험선호 쪽으로 끄는 힘**: " + " · ".join(f"{n}({last[n]:.0f})" for n in on))
    if off:
        lines.append("🔴 **안전자산 쪽으로 끄는 힘**: " + " · ".join(f"{n}({last[n]:.0f})" for n in off))
    if lines:
        st.markdown("  \n".join(lines))
    with st.expander("구성요소 설명"):
        st.markdown("\n".join(f"- **{nm}**: {desc[nm]}" + (f" — 지금 **{last[nm]:.0f}**" if nm in last else " — 자료 없음")
                              for nm, _, _ in COMPONENTS))

    # 추이와 코스피
    st.subheader("게이지 추이와 코스피")
    n = cm.span_picker("rg_span")
    h = df["종합"].tail(n)
    fig = go.Figure()
    fig.add_hrect(y0=0, y1=25, fillcolor=cm.DOWN, opacity=0.07, line_width=0)
    fig.add_hrect(y0=75, y1=100, fillcolor=cm.UP, opacity=0.07, line_width=0)
    fig.add_trace(go.Scatter(x=h.index, y=h, name="위험선호 게이지", line=dict(color=cm.ORANGE, width=2)))
    if "^KS11" in p:
        k = p["^KS11"].reindex(h.index).ffill()
        fig.add_trace(go.Scatter(x=k.index, y=k, name="코스피 (오른쪽)", yaxis="y2", line=dict(color=cm.BLUE, width=1.6)))
    fig.add_hline(y=50, line_dash="dot", line_color=cm.MUTED)
    fig.update_layout(yaxis=dict(title="게이지", range=[0, 100]), yaxis2=dict(title="코스피", overlaying="y", side="right"))
    cm.show(fig, 380)

    # 주식 심리와 엇갈림
    try:
        fg = an.fear_greed(p, "US")
        if not fg.empty:
            g = float(fg["종합"].iloc[-1])
            gap = g - sm["now"]
            msg = f"미국 공포·탐욕 지수는 **{g:.0f}({an.fg_label(g)})**, 위험선호 게이지는 **{sm['now']:.0f}({label(sm['now'])[0]})**예요. "
            if gap >= 20:
                msg += "⚠️ 주식시장 기분은 들떠 있는데 돈은 안전자산 쪽으로 가고 있어요. 상승이 오래가지 못할 수 있는 엇갈림이에요."
            elif gap <= -20:
                msg += "주식시장 기분은 움츠러들었지만 돈은 이미 위험자산으로 움직이고 있어요. 심리가 뒤따라 개선될 수 있는 신호예요."
            else:
                msg += "두 지표가 같은 방향을 가리키고 있어요 (엇갈림 없음)."
            st.markdown(msg)
    except Exception:
        pass

    # 과거 검증
    with st.expander("과거에 이 게이지 다음 코스피·S&P 500은 어땠나요? (검증)"):
        fwd = cm.fwd()
        for t, nm in [("^KS11", "코스피"), ("^GSPC", "S&P 500")]:
            if t in p:
                tb = an.fg_buckets(p[t], df["종합"], fwd)
                tb["구간"] = tb["구간"].astype(str).map({"극단적 공포": "강한 위험회피", "공포": "위험회피", "중립": "중립",
                                                     "탐욕": "위험선호", "극단적 탐욕": "강한 위험선호"})
                st.markdown(f"**{nm}: 게이지 구간별 이후 {fwd}거래일**")
                st.dataframe(tb, hide_index=True, use_container_width=True,
                             column_config={"평균 수익률(%)": st.column_config.NumberColumn(format="%+.2f"),
                                            "상승 확률(%)": st.column_config.NumberColumn(format="%.0f")})
        st.caption("위험선호 구간 뒤에 수익률이 높으면 '흐름을 따라가는' 지표, 위험회피 구간 뒤에 더 높으면 '반대로 보는' 지표예요.")
    cm.source(cm.price_note())
