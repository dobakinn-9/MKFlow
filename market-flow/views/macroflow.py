"""큰 그림: 경기 국면 시계(OECD 경기선행지수) / 달러 유동성(연준 순유동성)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import common as cm
import data as dt

# ════════════════════════════════════════════════════════
# 1. 경기 국면 시계
# ════════════════════════════════════════════════════════
CLI = {"CLI_USA": "미국", "CLI_KOR": "한국", "CLI_CHN": "중국", "CLI_JPN": "일본", "CLI_DEU": "독일", "CLI_G7": "G7 평균"}
PHASE = {  # (수준≥100, 상승 중)
    (True, True): ("확장", cm.UP, "추세보다 좋고 더 좋아지는 중 — 주식에 가장 우호적인 구간이 많았어요"),
    (True, False): ("둔화", cm.ORANGE, "아직 추세보다 좋지만 꺾이는 중 — 변동성이 커지기 쉬워요"),
    (False, False): ("수축", cm.DOWN, "추세보다 나쁘고 더 나빠지는 중 — 방어적인 구간"),
    (False, True): ("회복", cm.PURPLE, "아직 추세 아래지만 좋아지는 중 — 과거엔 주가가 먼저 오르기 시작한 구간"),
}


@st.cache_data(ttl=3600 * 3)
def _cli() -> dict[str, pd.Series]:
    out = {}
    for k in CLI:
        s, _ = dt.load_us_cache(k)
        if s is not None and len(s) > 24:
            out[k] = s
    return out


def phase_of(level: float, chg: float):
    return PHASE[(level >= 100, chg >= 0)]


def _phase_series(s: pd.Series) -> pd.Series:
    ch = s.diff()
    return pd.Series([phase_of(l, c)[0] if not np.isnan(c) else None for l, c in zip(s, ch)], index=s.index)


def cycle_clock():
    st.title("경기 국면 시계")
    cm.explain("""
- **OECD 경기선행지수(CLI)**로 나라별 경기가 어디쯤인지 시계처럼 보여줘요. CLI는 주문·심리·금리차·주가 등을 묶어 **6~9개월 앞 경기**를 미리 보려고 만든 지수예요.
- **100 = 장기 추세**. 가로는 100보다 위(좋음)/아래(나쁨), 세로는 지난달보다 오르는지/내리는지예요.
- 경기는 보통 **시계 방향**으로 돌아요: 🟣 **회복** → 🔴 **확장** → 🟠 **둔화** → 🔵 **수축** → 다시 회복.
- 꼬리 선은 최근 12개월 지나온 길이에요. 점이 **어느 칸으로 향하는지**가 앞으로의 큰 흐름이에요.
- OECD는 약 1~2개월 늦게 발표하고, 최근 값은 나중에 고쳐지기도 해요. 그래서 '오늘의 경기'가 아니라 **큰 방향**을 보는 용도예요.
""")
    data = _cli()
    if not data:
        st.info("경기선행지수 자료가 아직 없어요. GitHub 자동 수집(미국 공식 통계 받기)이 한 번 돌면 생겨요.")
        return
    tail = st.radio("꼬리 길이", ["6개월", "12개월", "24개월"], index=1, horizontal=True, key="cyc_tail")
    n = {"6개월": 6, "12개월": 12, "24개월": 24}[tail]
    pick = st.multiselect("나라", [k for k in CLI if k in data], default=[k for k in ("CLI_USA", "CLI_KOR", "CLI_CHN") if k in data],
                          format_func=lambda k: CLI[k], key="cyc_pick")

    fig = go.Figure()
    xs, ys = [], []
    for k in pick:
        s = data[k].dropna()
        d = pd.DataFrame({"x": s - 100, "y": s.diff() * 10}).dropna().tail(n)  # 세로는 보기 쉽게 10배
        xs += list(d["x"])
        ys += list(d["y"])
        lab, col, _ = phase_of(s.iloc[-1], s.diff().iloc[-1])
        fig.add_trace(go.Scatter(x=d["x"], y=d["y"], mode="lines+markers", line=dict(color=col, width=1.6), opacity=0.55,
                                 marker=dict(size=4), hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=[d["x"].iloc[-1]], y=[d["y"].iloc[-1]], mode="markers+text", text=[CLI[k]],
                                 textposition="top center", marker=dict(size=14, color=col, line=dict(color="#0B0F17", width=1.5)),
                                 hovertemplate=f"<b>{CLI[k]}</b> {s.index[-1]:%Y-%m}<br>CLI {s.iloc[-1]:.2f} · {lab}<extra></extra>",
                                 showlegend=False))
    dx = max([abs(v) for v in xs] + [1.0]) * 1.2
    dy = max([abs(v) for v in ys] + [1.0]) * 1.2
    for (rx, ry), (lab, col, _) in PHASE.items():
        fig.add_shape(type="rect", x0=0, x1=dx if rx else -dx, y0=0, y1=dy if ry else -dy, fillcolor=col, opacity=0.06,
                      line_width=0, layer="below")
        fig.add_annotation(x=dx * 0.95 if rx else -dx * 0.95, y=dy * 0.95 if ry else -dy * 0.95, text=f"<b>{lab}</b>",
                           showarrow=False, font=dict(color=col, size=14), xanchor="right" if rx else "left",
                           yanchor="top" if ry else "bottom")
    fig.add_hline(y=0, line_color=cm.MUTED, line_width=1)
    fig.add_vline(x=0, line_color=cm.MUTED, line_width=1)
    fig.update_xaxes(title="경기 수준 (CLI − 100, 오른쪽 = 추세보다 좋음)", range=[-dx, dx], zeroline=False)
    fig.update_yaxes(title="경기 방향 (위 = 좋아지는 중)", range=[-dy, dy], zeroline=False, showticklabels=False)
    fig.update_layout(hovermode="closest")
    cm.show(fig, 520)

    # 표
    rows = []
    for k, s in data.items():
        s = s.dropna()
        ph = _phase_series(s).dropna()
        cur = ph.iloc[-1]
        months = int((ph[::-1] == cur).cumprod().sum())
        before = ph.iloc[-7] if len(ph) > 6 else "—"
        rows.append({"나라": CLI[k], "기준 월": f"{s.index[-1]:%Y-%m}", "CLI": float(s.iloc[-1]), "지금 국면": cur,
                     "6개월 전": before, "이 국면 지속": f"{months}개월", "의미": phase_of(s.iloc[-1], s.diff().iloc[-1])[2]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={"CLI": st.column_config.NumberColumn(format="%.2f")})

    # 추이
    st.subheader("경기선행지수 추이")
    fig2 = go.Figure()
    for k, c in zip(["CLI_USA", "CLI_KOR", "CLI_CHN", "CLI_JPN", "CLI_DEU", "CLI_G7"],
                    [cm.BLUE, cm.UP, cm.ORANGE, cm.PURPLE, "#14B8A6", cm.MUTED]):
        if k in data and k in pick:
            s = data[k].dropna().tail(84)
            fig2.add_trace(go.Scatter(x=s.index, y=s, name=CLI[k], line=dict(color=c, width=2)))
    fig2.add_hline(y=100, line_dash="dash", line_color=cm.MUTED, annotation_text="장기 추세 100")
    cm.show(fig2, 340)

    # 국면별 과거 주가
    with st.expander("과거에 국면별로 코스피·S&P 500은 어땠나요? (검증)"):
        p = cm.prices()
        for ck, tk, nm in [("CLI_KOR", "^KS11", "코스피 (한국 국면 기준)"), ("CLI_USA", "^GSPC", "S&P 500 (미국 국면 기준)")]:
            if ck not in data or tk not in p:
                continue
            ph = _phase_series(data[ck]).dropna()
            m = p[tk].dropna().resample("MS").last()
            fwd = (m.shift(-3) / m - 1) * 100
            # 발표 지연(약 2개월)을 감안해, 국면을 안 뒤부터의 수익률로 계산
            ph_known = ph.shift(2, freq="MS")
            d = pd.DataFrame({"국면": ph_known, "이후 3개월 수익률": fwd}).dropna()
            if len(d) < 12:
                continue
            g = d.groupby("국면")["이후 3개월 수익률"]
            tb = pd.DataFrame({"개월 수": g.size(), "평균(%)": g.mean(), "오를 확률(%)": g.apply(lambda x: (x > 0).mean() * 100)})
            tb = tb.reindex([x for x in ("회복", "확장", "둔화", "수축") if x in tb.index]).reset_index()
            st.markdown(f"**{nm}** — 국면이 발표된 뒤(2개월 지연 반영) 3개월 수익률")
            st.dataframe(tb, hide_index=True, use_container_width=True,
                         column_config={"평균(%)": st.column_config.NumberColumn(format="%+.2f"),
                                        "오를 확률(%)": st.column_config.NumberColumn(format="%.0f")})
        st.caption("앱이 불러온 기간(사이드바 '불러올 기간') 안에서만 계산해요. 표본이 작아 참고용이에요.")
    cm.source(dt.load_us_cache("CLI_USA")[1] or "OECD 경기선행지수 (DBnomics)")


# ════════════════════════════════════════════════════════
# 2. 달러 유동성
# ════════════════════════════════════════════════════════
@st.cache_data(ttl=3600 * 3)
def net_liquidity() -> tuple[pd.DataFrame | None, str]:
    parts, notes = {}, []
    for k in ("WALCL_B", "TGA_B", "RRP_B"):
        s, note = dt.load_us_cache(k)
        if s is None or s.empty:
            return None, f"{k} 자료가 아직 없어요"
        parts[k] = s
        notes.append(note)
    idx = pd.bdate_range(max(s.index.min() for s in parts.values()), max(s.index.max() for s in parts.values()))
    df = pd.DataFrame({k: v.reindex(idx.union(v.index)).sort_index().ffill().reindex(idx) for k, v in parts.items()})
    df = df.dropna()
    df["순유동성"] = df["WALCL_B"] - df["TGA_B"] - df["RRP_B"]
    return df, "연준 자산(H.4.1)·재무부 현금잔고(TGA)·역레포 — 연준·미 재무부·뉴욕 연은 공식 자료"


def liquidity():
    st.title("달러 유동성")
    cm.explain("""
- **순유동성 = 연준 총자산 − 재무부 현금잔고(TGA) − 역레포 잔액**. 금융시장에 실제로 풀려 있는 달러의 양을 보는 대표적인 방법이에요.
- **연준 자산**이 줄면(양적긴축) 돈이 빠져요. **TGA**가 늘면 정부가 시장 돈을 거둬 금고에 넣은 것이고, **역레포**가 늘면 돈이 연준에 잠겨 있는 거예요.
- 2020년 이후 순유동성과 미국 주가(특히 나스닥)는 큰 흐름이 비슷하게 움직인 적이 많아요. **유동성이 늘면 순풍, 줄면 역풍**으로 봐요.
- 매주 목요일(한국 금요일 아침) 연준 자산이 갱신되고, TGA·역레포는 매일 갱신돼요.
""")
    df, note = net_liquidity()
    if df is None:
        st.info(note + ". GitHub 자동 수집(미국 공식 통계 받기)이 한 번 돌면 생겨요.")
        return
    nl = df["순유동성"]
    c1, c2, c3 = st.columns(3)
    for col, (lab, d) in zip((c1, c2, c3), [("최근 1주", 5), ("최근 1개월", 21), ("최근 3개월", 63)]):
        if len(nl) > d:
            ch = nl.iloc[-1] - nl.iloc[-1 - d]
            col.metric(f"순유동성 변화 ({lab})", f"{ch:+,.0f}B$",
                       f"{ch / nl.iloc[-1 - d] * 100:+.1f}%")
    now = nl.iloc[-1]
    d3 = nl.iloc[-1] - nl.iloc[-64] if len(nl) > 64 else float("nan")
    st.markdown(f"지금 순유동성은 **{now / 1000:,.2f}조 달러**({df.index[-1]:%Y-%m-%d})예요. 최근 3개월 "
                + f"**{d3:+,.0f}B$**"
                + (" 늘어 **주식에 순풍**이에요." if d3 > 50 else " 줄어 **주식에 역풍**이에요." if d3 < -50 else " 거의 변화가 없어 중립이에요."))
    st.caption("B$ = 10억 달러 (예: +100B$ = 1,000억 달러 증가)")

    span = cm.span_picker("liq_span", "1년")
    sub = df.tail(span)
    p = cm.prices()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub.index, y=sub["순유동성"] / 1000, name="순유동성 (조 달러)", line=dict(color=cm.ORANGE, width=2.4)))
    for t, nm, c in [("^GSPC", "S&P 500 (오른쪽)", cm.BLUE), ("^IXIC", "나스닥 (오른쪽)", cm.PURPLE)]:
        if t in p:
            s = p[t].reindex(sub.index).ffill()
            fig.add_trace(go.Scatter(x=s.index, y=s, name=nm, yaxis="y2", line=dict(color=c, width=1.5)))
            break
    fig.update_layout(yaxis=dict(title="조 달러"), yaxis2=dict(title="지수", overlaying="y", side="right"))
    cm.show(fig, 380)

    st.subheader("무엇이 유동성을 움직였나")
    fig2 = go.Figure()
    for k, nm, c in [("WALCL_B", "연준 총자산", cm.BLUE), ("TGA_B", "재무부 현금잔고 (TGA)", cm.UP), ("RRP_B", "역레포 잔액", cm.PURPLE)]:
        fig2.add_trace(go.Scatter(x=sub.index, y=sub[k] / 1000, name=nm, line=dict(color=c, width=2)))
    fig2.update_yaxes(title="조 달러")
    cm.show(fig2, 320)
    if len(df) > 64:
        ch = (df.iloc[-1] - df.iloc[-64])[["WALCL_B", "TGA_B", "RRP_B"]]
        eff = pd.Series({"연준 총자산": ch["WALCL_B"], "재무부 현금잔고 (늘면 −)": -ch["TGA_B"], "역레포 (늘면 −)": -ch["RRP_B"]})
        st.plotly_chart(cm.hbar(eff.index, eff.values, "{:+,.0f}B$"), use_container_width=True)
        st.caption("최근 3개월 동안 각 항목이 순유동성을 얼마나 늘렸는지(+)·줄였는지(−)예요.")

    if "^GSPC" in p and len(df) > 200:
        sp = p["^GSPC"].reindex(df.index).ffill()
        a, b = df["순유동성"].pct_change(63), sp.pct_change(63)
        c = a.corr(b)
        st.markdown(f"지난 {len(df) // 252}년여 동안 3개월 순유동성 변화와 S&P 500 3개월 수익률의 상관계수는 **{c:+.2f}**예요. "
                    + ("+0.3 이상이라 '유동성 따라 주가가 움직이는' 관계가 꽤 뚜렷해요." if c >= 0.3 else
                     "0에 가까워 이 기간엔 유동성보다 실적·금리가 주가를 더 좌우했어요." if c > -0.3 else
                     "음수라 이 기간엔 유동성과 주가가 오히려 반대로 움직였어요. 유동성은 '큰 배경'으로만 참고하세요."))
    cm.source(note)
