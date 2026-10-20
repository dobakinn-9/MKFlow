"""시장의 체력: 추세·이동평균 / 시장의 폭 / 거래대금 / 변동성 / 업종 순환."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analysis as an
import common as cm
from config import TICKERS, US_SECTORS, name


def trend():
    st.title("추세·이동평균")
    cm.explain("""
- **이동평균선**은 최근 N일 종가의 평균이에요. 지수가 **60일선·120일선 위**에 있으면 중기 상승 흐름, 아래면 하락 흐름으로 봐요.
- **20일선이 60일선 위**(정배열)면 단기 흐름도 좋다는 뜻이에요. 반대로 꺾여 내려오면(데드크로스) 조정 신호예요.
- 아래 비교 차트는 서로 다른 지표를 **시작일 = 100**으로 맞춰서 누가 더 강했는지 보여줘요.
""")
    p = cm.prices()
    t, nm = cm.target(), cm.target_name()
    n = cm.span_picker("trend_span")
    full = p[t].dropna()
    ma = pd.DataFrame({"종가": full, "20일선": full.rolling(20).mean(), "60일선": full.rolling(60).mean(),
                       "120일선": full.rolling(120).mean()}).tail(n)
    fig = px.line(ma, labels={"value": "", "index": "", "variable": ""},
                  color_discrete_sequence=[cm.BLUE, cm.ORANGE, cm.UP, cm.MUTED])
    cm.show(fig, 380)
    last = ma.iloc[-1]
    states = [f"60일선 {'위' if last['종가'] > last['60일선'] else '아래'}",
              f"120일선 {'위' if last['종가'] > last['120일선'] else '아래'}",
              "20일선 > 60일선 (정배열)" if last["20일선"] > last["60일선"] else "20일선 < 60일선 (역배열)"]
    st.markdown(f"**{nm}** 현재: " + " · ".join(states))

    st.subheader("지표 비교 (시작일 = 100)")
    pick = st.multiselect("비교할 지표", list(TICKERS), default=["^KS11", "^GSPC", "^SOX"], format_func=name)
    if pick:
        sub = p[pick].dropna(how="all").tail(n)
        norm = sub / sub.bfill().iloc[0] * 100
        norm.columns = [name(c) for c in norm.columns]
        cm.show(px.line(norm, labels={"value": "시작일 = 100", "index": "", "variable": ""}), 380)
    cm.source(cm.price_note())


def breadth():
    st.title("시장의 폭")
    cm.explain("""
- **시장의 폭**은 '지수 상승에 얼마나 많은 종목이 함께하는가'예요.
- 지수는 오르는데 **하락 종목이 더 많으면** 소수 대형주만 끄는 '얇은 장'이라 오래가기 어려워요.
- **상승-하락 누적선(ADL)**이 지수와 함께 오르면 건강한 상승, 지수만 오르고 ADL이 내려가면 경고 신호예요.
- 미국은 **동일가중 S&P 500(RSP) ÷ 시총가중(SPY)** 비율로 봐요. 이 비율이 오르면 중소형 종목까지 고르게 오르는 '넓은 장'이에요.
- **업종 ETF 중 50일선 위에 있는 비율**도 함께 보여줘요. 70% 이상이면 폭넓은 강세, 30% 이하면 폭넓은 약세예요.
""")
    st.subheader("한국: 상승·하락 종목 수")
    mkt = st.radio("시장", ["KOSPI", "KOSDAQ"], horizontal=True, key="br_mkt",
                   format_func=lambda x: {"KOSPI": "코스피", "KOSDAQ": "코스닥"}[x])
    b, note = cm.kr_breadth(mkt)
    if b is None:
        st.info(note + "\n\n한국거래소 접속이 막히면 이 부분만 비어 있고, 아래 미국 지표는 정상 동작해요.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=b.index, y=b["상승"], name="상승", marker_color=cm.UP))
        fig.add_trace(go.Bar(x=b.index, y=-b["하락"], name="하락", marker_color=cm.DOWN))
        fig.update_layout(barmode="relative", yaxis_title="종목 수 (아래 = 하락)")
        cm.show(fig, 320)
        last = b.iloc[-1]
        ratio = last["상승"] / max(last["하락"], 1)
        c1, c2, c3 = st.columns(3)
        c1.metric("오늘 상승 종목", f"{int(last['상승']):,}")
        c2.metric("오늘 하락 종목", f"{int(last['하락']):,}")
        c3.metric("상승/하락 비율", f"{ratio:.2f}", help="1보다 크면 오르는 종목이 더 많아요.")
        st.subheader("상승-하락 누적선 (ADL)")
        cm.show(go.Figure(go.Scatter(x=b.index, y=an.ad_line(b), line=dict(color=cm.BLUE, width=2))), 240)
        cm.source(note)

    st.subheader("미국: 동일가중 ÷ 시총가중 S&P 500")
    p = cm.prices()
    n = cm.span_picker("br_span")
    if {"RSP", "SPY"} <= set(p.columns):
        r = an.ratio(p["RSP"].tail(n), p["SPY"].tail(n))
        fig2 = go.Figure(go.Scatter(x=r.index, y=r, line=dict(color=cm.BLUE, width=2)))
        fig2.add_hline(y=100, line_dash="dash", line_color=cm.MUTED)
        fig2.update_yaxes(title="시작일 = 100")
        cm.show(fig2, 280)
        st.markdown("오르는 중 → 중소형 종목까지 고르게 강함 · 내리는 중 → 대형주 쏠림" +
                    f" (기간 변화 **{r.iloc[-1] - 100:+.1f}**)")
    st.subheader("미국 업종 ETF 중 50일선 위에 있는 비율")
    share = an.share_above_ma(p, list(US_SECTORS)).tail(n)
    fig3 = go.Figure(go.Scatter(x=share.index, y=share, fill="tozeroy", line=dict(color=cm.BLUE)))
    for y in (30, 70):
        fig3.add_hline(y=y, line_dash="dot", line_color=cm.MUTED)
    fig3.update_yaxes(range=[0, 100], title="%")
    cm.show(fig3, 260)
    cm.source(cm.price_note())


def turnover():
    st.title("거래대금")
    cm.explain("""
- **거래대금**은 하루 동안 거래된 돈의 총액이에요. 시장에 돈이 얼마나 몰리는지 보여줘요.
- 오를 때 거래대금이 **20일 평균보다 많으면** 힘 있는 상승, 거래 없이 오르면 힘이 약한 상승이에요.
- 내릴 때 거래대금이 폭증하면 '투매'일 수 있고, 이후 바닥이 잡히는 경우도 있어요.
""")
    nm = st.radio("지수", ["코스피", "코스닥"], horizontal=True, key="to_idx")
    df, note = cm.kr_index(nm)
    if df is not None and "거래대금" in df:
        v = (df["거래대금"] / 1e12).dropna()
        ma = v.rolling(20, min_periods=1).mean()
        if len(v) < 20:
            st.caption(f"거래대금은 매일 자동으로 쌓이는 중이에요 (현재 {len(v)}일치). 20일이 모이면 평균선이 정확해져요.")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=v.index, y=v, name="거래대금", marker_color=cm.BLUE, opacity=0.6))
        fig.add_trace(go.Scatter(x=ma.index, y=ma, name="20일 평균", line=dict(color=cm.ORANGE, width=2)))
        fig.update_yaxes(title="조 원")
        cm.show(fig, 360)
        c1, c2 = st.columns(2)
        c1.metric("최근 거래대금", f"{v.iloc[-1]:.1f}조 원",
                  f"20일 평균 대비 {(v.iloc[-1] / ma.iloc[-1] - 1) * 100:+.0f}%" if len(v) >= 5 else None)
        if "종가" in df:
            c2.metric(f"{nm} 종가", f"{df['종가'].iloc[-1]:,.2f}",
                      cm.fmt_change((df["종가"].iloc[-1] / df["종가"].iloc[-2] - 1) * 100))
        cm.source(note)
    else:
        st.info((note or "") + "\n\n대신 야후 파이낸스의 거래량(주식 수)을 보여드릴게요.")
        vol = cm.volumes()
        t = "^KS11" if nm == "코스피" else None
        if t and t in vol and vol[t].dropna().sum() > 0:
            v = vol[t].dropna().tail(250)
            fig = go.Figure(go.Bar(x=v.index, y=v, marker_color=cm.BLUE, opacity=0.6))
            fig.add_trace(go.Scatter(x=v.index, y=v.rolling(20).mean(), name="20일 평균", line=dict(color=cm.ORANGE)))
            cm.show(fig, 320)
    st.subheader("미국 S&P 500 거래량")
    vol = cm.volumes()
    if "^GSPC" in vol and vol["^GSPC"].dropna().sum() > 0:
        v = vol["^GSPC"].dropna().tail(250) / 1e9
        fig = go.Figure(go.Bar(x=v.index, y=v, name="거래량", marker_color=cm.BLUE, opacity=0.6))
        fig.add_trace(go.Scatter(x=v.index, y=v.rolling(20).mean(), name="20일 평균", line=dict(color=cm.ORANGE, width=2)))
        fig.update_yaxes(title="십억 주")
        cm.show(fig, 300)
    cm.source(cm.price_note())


def volatility():
    st.title("변동성 (VIX·VKOSPI)")
    cm.explain("""
- **VIX**(미국)와 **VKOSPI**(한국)는 옵션 가격으로 계산한 '앞으로 한 달 예상 변동폭'이에요. 흔히 **공포 지수**라고 불러요.
- 15 아래: 낙관 · 15~22: 보통 · 22~30: 불안 확대 · 30 위: 공포
- 공포 지수가 급등한 뒤 꺾이기 시작하면 바닥 신호가 되는 경우가 많아요.
- VKOSPI를 불러오지 못하면 코스피의 **실제 변동성**(최근 20일 등락폭을 연율로 환산)을 대신 보여줘요.
""")
    p = cm.prices()
    n = cm.span_picker("vol_span")
    vk, vk_note = cm.vkospi()
    fig = go.Figure()
    if "^VIX" in p:
        v = p["^VIX"].tail(n)
        fig.add_trace(go.Scatter(x=v.index, y=v, name="VIX (미국)", line=dict(color=cm.BLUE, width=2)))
    if vk is not None:
        k = vk.tail(n)
        fig.add_trace(go.Scatter(x=k.index, y=k, name="VKOSPI (한국)", line=dict(color=cm.ORANGE, width=2)))
    else:
        rv = an.realized_vol(p["^KS11"]).tail(n)
        fig.add_trace(go.Scatter(x=rv.index, y=rv, name="코스피 실제 변동성 (대체)", line=dict(color=cm.ORANGE, width=2, dash="dot")))
    for y, lbl in [(15, "낙관"), (22, "불안"), (30, "공포")]:
        fig.add_hline(y=y, line_dash="dot", line_color=cm.MUTED, annotation_text=lbl, annotation_position="right")
    cm.show(fig, 380)

    cols = st.columns(2)
    if "^VIX" in p:
        v = p["^VIX"].dropna()
        cols[0].metric("VIX", f"{v.iloc[-1]:.1f}", cm.fmt_change(v.iloc[-1] - v.iloc[-2], "p"), delta_color="inverse",
                       help=f"최근 1년 중 상위 {100 - an.percentile_rank(v.tail(252)):.0f}% 수준")
    if vk is not None:
        cols[1].metric("VKOSPI", f"{vk.iloc[-1]:.1f}", cm.fmt_change(vk.iloc[-1] - vk.iloc[-2], "p"), delta_color="inverse")
    else:
        rv = an.realized_vol(p["^KS11"]).dropna()
        cols[1].metric("코스피 실제 변동성 (대체)", f"{rv.iloc[-1]:.1f}")
        st.caption(vk_note)
    cm.source(cm.price_note() + (f" · VKOSPI: {vk_note}" if vk is not None else ""))


def sectors():
    st.title("업종 순환")
    cm.explain("""
- 돈은 업종 사이를 돌아요. **경기 좋을 때**는 기술·임의소비재·산업재가, **불안할 때**는 필수소비재·헬스케어·유틸리티(방어주)가 상대적으로 강해요.
- 아래 '공격 vs 방어' 비율이 오르면 위험을 즐기는 장, 내리면 몸을 사리는 장이에요.
- 한국은 코스피 업종지수, 미국은 업종별 대표 ETF로 봐요.
""")
    p = cm.prices()
    per = st.radio("기간", ["1주", "1개월", "3개월"], index=1, horizontal=True, key="sec_per")
    days = {"1주": 5, "1개월": 21, "3개월": 63}[per]

    st.subheader("한국: 코스피 업종 등락률")
    ks, note = cm.kr_sectors(days)
    if ks is None:
        st.info(note)
    else:
        ks = ks.sort_values("등락률", ascending=False)
        st.plotly_chart(cm.hbar(ks["업종"], ks["등락률"], "{:+.1f}%"), use_container_width=True)
        cm.source(note)

    st.subheader("미국: 업종 ETF 수익률")
    tbl = an.period_returns(p, list(US_SECTORS), {per: days}).sort_values(per, ascending=False)
    st.plotly_chart(cm.hbar(tbl["이름"], tbl[per], "{:+.1f}%"), use_container_width=True)

    st.subheader("공격 업종 vs 방어 업종 (미국)")
    off = [t for t in ("XLK", "XLY", "XLI") if t in p]
    dfn = [t for t in ("XLP", "XLV", "XLU") if t in p]
    if off and dfn:
        n = 252
        o = p[off].tail(n)
        d = p[dfn].tail(n)
        r = an.ratio((o / o.iloc[0]).mean(axis=1), (d / d.iloc[0]).mean(axis=1))
        fig = go.Figure(go.Scatter(x=r.index, y=r, line=dict(color=cm.BLUE, width=2)))
        fig.add_hline(y=100, line_dash="dash", line_color=cm.MUTED)
        fig.update_yaxes(title="공격 ÷ 방어 (1년 전 = 100)")
        cm.show(fig, 280)
        chg = r.iloc[-1] - r.iloc[-22] if len(r) > 22 else float("nan")
        st.markdown(f"최근 한 달 변화 **{chg:+.1f}** → " +
                    ("공격 업종으로 돈이 몰리는 중이에요." if chg > 1 else "방어 업종으로 돈이 옮겨가는 중이에요." if chg < -1 else "뚜렷한 쏠림은 없어요."))
    cm.source(cm.price_note())
