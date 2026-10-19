"""AI 예측: 채권 금리 예측 / 미국 물가 예측."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import common as cm
import data as dt
import macro_ml as mm
from config import BOND_ETFS, BOND_TICKERS, DURATION, FRED_SERIES


@st.cache_data(ttl=3600 * 6, show_spinner="금리 예측 모델을 학습하고 검증하는 중… (처음엔 30초 정도 걸려요)")
def _yield_dir(period: str, fwd: int):
    return mm.yield_direction(cm.prices(), fwd)


@st.cache_data(ttl=3600 * 6, show_spinner="미국 물가 통계(FRED)를 불러오는 중…")
def _fred():
    return dt.load_fred(list(FRED_SERIES))


@st.cache_data(ttl=3600 * 6)
def _infl(oil_shift: float, months: int):
    fred, _ = _fred()
    return mm.inflation_forecast(fred, months, oil_shift)


def _gauge(prob: float, title: str) -> go.Figure:
    color = cm.DOWN if prob >= 0.55 else cm.UP if prob <= 0.45 else cm.MUTED  # 금리 상승 = 채권 가격 하락 = 빨강
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=prob * 100, number={"suffix": "%", "font": {"size": 40}}, title={"text": title},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": color},
               "threshold": {"line": {"color": "#E6E8EB", "width": 2}, "value": 50}}))
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=0))
    return fig


def bonds():
    st.title("채권 금리 예측")
    fwd = cm.fwd()
    cm.warn_if_sample(cm.price_note())
    cm.explain(f"""
- **금리와 채권 가격은 반대로 움직여요.** 금리가 오르면 이미 발행된 채권의 가격은 떨어지고, 금리가 내리면 채권 가격은 올라요.
- **얼마나 움직이나요?** '듀레이션'만큼이에요. 10년 국채(듀레이션 약 8.5)는 금리가 0.1%p 오르면 가격이 약 0.85% 떨어져요. 장기 국채 ETF(TLT, 약 16.5)는 약 1.65% 떨어져요.
- **이 화면의 예측 두 가지**
  1. **방향**: "{fwd}거래일 뒤 미 10년물 금리가 지금보다 높을까?" 확률이에요. 금리 흐름, 장단기 금리차, 유가, 달러, VIX, 채권 변동성, 주식, 기대인플레이션 등을 학습한 AI 모델(워크포워드 검증)이에요.
  2. **범위**: 지금의 시장 변동성을 반영해 5·20·60거래일 뒤 금리가 있을 법한 범위(10%~90%)를 보여줘요.
""")
    p = cm.prices()
    if "^TNX" not in p:
        st.info("금리 데이터를 불러오지 못했어요.")
        return

    st.subheader("미국 국채 금리 곡선")
    cur = {v: p[k].dropna().iloc[-1] for k, v in BOND_TICKERS.items() if k in p and p[k].notna().any()}

    def at(lag):
        return {v: p[k].dropna().iloc[-1 - lag] for k, v in BOND_TICKERS.items() if k in p and p[k].notna().sum() > lag}
    fig = go.Figure()
    for lbl, d, c, dash in [("지금", cur, cm.BLUE, None), ("1개월 전", at(21), cm.ORANGE, "dot"), ("1년 전", at(252), cm.MUTED, "dash")]:
        fig.add_trace(go.Scatter(x=list(d), y=list(d.values()), name=lbl, mode="lines+markers",
                                 line=dict(color=c, width=2, dash=dash)))
    fig.update_yaxes(title="금리(%)")
    cm.show(fig, 300)
    cols = st.columns(len(cur))
    for col, (k, v) in zip(cols, cur.items()):
        prev = at(21).get(k, v)
        col.metric(k, f"{v:.2f}%", f"{v - prev:+.2f}%p (1개월)", delta_color="inverse")
    if "3개월물" in cur and "10년물" in cur:
        sp = cur["10년물"] - cur["3개월물"]
        st.caption(f"장단기 금리차(10년−3개월) {sp:+.2f}%p → " + ("역전 상태: 경기 둔화 신호로 봐요." if sp < 0 else "정상(플러스) 상태예요."))

    st.subheader(f"방향 예측: {fwd}거래일 뒤 10년물 금리")
    try:
        r = _yield_dir(cm.period(), fwd)
    except ImportError:
        st.error("scikit-learn이 필요해요.")
        return
    if not r.get("ok"):
        st.info(r.get("reason"))
    else:
        a, b = st.columns(2)
        with a:
            st.plotly_chart(_gauge(r["prob"], "금리 상승 확률"), use_container_width=True)
        with b:
            prob = r["prob"]
            view = ("금리 **상승** 쪽 → 채권 가격엔 부담" if prob >= 0.55 else
                    "금리 **하락** 쪽 → 채권 가격엔 우호적" if prob <= 0.45 else "방향을 판단하기 어려워요")
            st.markdown(f"#### AI의 판단\n{view}")
            edge = r["hit"] - r["naive"]
            trust = ("낮음 — 찍기보다 낫지 않았어요" if (np.isnan(r["auc"]) or r["auc"] < 0.52 or edge < 0)
                     else "보통" if r["auc"] < 0.56 else "비교적 높음")
            st.markdown(f"**과거 성적**: 적중률 {r['hit']:.1f}% (찍기 {r['naive']:.1f}%) · AUC {r['auc']:.3f} · 검증 {r['n']:,}일")
            st.markdown(f"**신뢰도**: {trust}")
        top = r["contrib"].head(7)
        st.plotly_chart(cm.hbar(top["특성"], top["기여"], "{:+.2f}"), use_container_width=True)
        st.caption("오른쪽(초록)은 금리 상승 확률을 높인 요인, 왼쪽(빨강)은 낮춘 요인이에요.")

    st.subheader("예상 범위 (10년물 금리)")
    rf = mm.range_forecast(p["^TNX"])
    if not rf.empty:
        now = p["^TNX"].dropna().iloc[-1]
        hist = p["^TNX"].dropna().tail(126)
        last_day = hist.index[-1]
        fut_x = [last_day + pd.tseries.offsets.BDay(int(h)) for h in rf["horizon"]]
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=hist.index, y=hist, name="10년물", line=dict(color=cm.BLUE, width=2)))
        xs = [last_day] + fut_x
        for lo, hi, op, lbl in [("q10", "q90", 0.15, "80% 범위"), ("q25", "q75", 0.3, "50% 범위")]:
            fig2.add_trace(go.Scatter(x=xs + xs[::-1], y=[now] + list(rf[hi]) + list(rf[lo])[::-1] + [now],
                                      fill="toself", fillcolor=f"rgba(91,155,240,{op})", line=dict(width=0), name=lbl))
        fig2.add_trace(go.Scatter(x=xs, y=[now] + list(rf["q50"]), name="중앙값", line=dict(color=cm.ORANGE, dash="dot")))
        fig2.update_yaxes(title="%")
        cm.show(fig2, 340)
        tbl = pd.DataFrame({
            "기간": [f"{h}거래일 뒤" for h in rf["horizon"]],
            "하단(10%)": rf["q10"], "중앙": rf["q50"], "상단(90%)": rf["q90"],
            "10년 국채 가격 변화 (상단 금리일 때)": -(rf["q90"] - now) * DURATION["10년 국채"],
            "10년 국채 가격 변화 (하단 금리일 때)": -(rf["q10"] - now) * DURATION["10년 국채"],
        })
        st.dataframe(tbl, hide_index=True, use_container_width=True,
                     column_config={c: st.column_config.NumberColumn(format="%.2f%%") for c in ["하단(10%)", "중앙", "상단(90%)"]}
                     | {c: st.column_config.NumberColumn(format="%+.1f%%") for c in tbl.columns if "가격" in c})
        st.caption("'80% 범위'는 과거 비슷한 변동성 상황에서 10번 중 8번은 이 안에 있었다는 뜻이에요.")

    st.subheader("채권 ETF 가격 흐름")
    n = cm.span_picker("bond_span")
    etfs = [t for t in BOND_ETFS if t in p]
    if etfs:
        sub = p[etfs].dropna(how="all").tail(n)
        norm = sub / sub.bfill().iloc[0] * 100
        fig3 = go.Figure()
        for t, c in zip(etfs, [cm.UP, cm.BLUE, cm.DOWN, cm.ORANGE]):
            fig3.add_trace(go.Scatter(x=norm.index, y=norm[t], name=BOND_ETFS[t], line=dict(color=c, width=2)))
        fig3.update_yaxes(title="시작일 = 100")
        cm.show(fig3, 320)
        st.caption("물가연동 국채(TIP)가 일반 국채(IEF)보다 강하면 시장이 물가 상승을 더 걱정한다는 뜻이에요.")
    cm.source(cm.price_note())


def inflation():
    st.title("미국 물가 예측")
    cm.explain("""
- 뉴스에 나오는 **'CPI 3.7%'**는 1년 전보다 물가가 얼마나 올랐는지(전년비)예요. 연준 목표는 **2%**예요.
- **근원 CPI**는 변동이 큰 식품·에너지를 뺀 물가로, 물가의 '기초 체력'을 보여줘요.
- **어떻게 예측하나요?** 최근 물가 흐름(1·3·6·12개월), 근원 물가, 유가 변화, 채권시장의 기대인플레이션을 학습해 다음 달 상승률을 예측하고, 이를 몇 달 이어 붙여요.
- **기저효과**: 전년비는 '1년 전 그 달 상승률'이 빠지고 '새 달 상승률'이 들어오며 바뀌어요. 1년 전에 많이 올랐던 달이 빠지면, 이번 달이 같아도 전년비는 내려가요.
- **유가 시나리오**를 바꾸면 에너지 가격이 물가 경로를 어떻게 바꾸는지 볼 수 있어요. 유가 변화는 다음 달부터 반영돼요.
""")
    fred, note = _fred()
    if "샘플" in note:
        st.warning(note)
    c1, c2 = st.columns(2)
    oil = c1.select_slider("유가 시나리오 (예측 기간 동안)", options=[-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3], value=0.0,
                           format_func=lambda v: "그대로" if v == 0 else f"{v:+.0%}")
    months = c2.select_slider("예측 기간", options=[3, 6, 9, 12], value=6, format_func=lambda v: f"{v}개월")
    try:
        res = _infl(oil, months)
    except ImportError:
        st.error("scikit-learn이 필요해요.")
        return
    if not res.get("ok"):
        st.info(res.get("reason"))
        return
    last_m = pd.Timestamp(res["last_month"])
    st.caption(f"마지막 발표치: {last_m:%Y년 %-m월} · 출처: {note}")

    cards = st.columns(4)
    for col, key, label in [(cards[0], "cpi", "CPI 전년비"), (cards[1], "core", "근원 CPI 전년비")]:
        if key in res:
            h = res[key]["yoy_hist"]
            col.metric(label, f"{h.iloc[-1]:.1f}%", f"{h.iloc[-1] - h.iloc[-2]:+.1f}%p (전월 대비)", delta_color="inverse")
    if "cpi" in res:
        cards[2].metric("최근 3개월 연율", f"{res['cpi']['ann3']:.1f}%", help="최근 3개월 속도가 1년 내내 이어진다면의 물가 상승률")
        fut = res["cpi"]["yoy_fut"]
        cards[3].metric(f"{months}개월 뒤 CPI 예측", f"{fut.iloc[-1]:.1f}%",
                        f"{fut.iloc[-1] - res['cpi']['yoy_hist'].iloc[-1]:+.1f}%p", delta_color="inverse")

    st.subheader("CPI 전년비: 지금까지와 앞으로")
    fig = go.Figure()
    for key, color, lbl in [("cpi", cm.ORANGE, "CPI"), ("core", cm.BLUE, "근원 CPI")]:
        if key not in res:
            continue
        r = res[key]
        h = r["yoy_hist"].tail(36)
        fig.add_trace(go.Scatter(x=h.index, y=h, name=lbl, line=dict(color=color, width=2)))
        fx = [h.index[-1]] + list(r["yoy_fut"].index)
        fig.add_trace(go.Scatter(x=fx, y=[h.iloc[-1]] + list(r["yoy_fut"]), name=f"{lbl} 예측",
                                 line=dict(color=color, width=2, dash="dot")))
        if key == "cpi":
            fig.add_trace(go.Scatter(x=fx + fx[::-1], y=[h.iloc[-1]] + list(r["hi"]) + list(r["lo"])[::-1] + [h.iloc[-1]],
                                     fill="toself", fillcolor="rgba(240,163,58,0.15)", line=dict(width=0), name="CPI 예측 범위(약 80%)"))
    fig.add_hline(y=2, line_dash="dash", line_color=cm.UP, annotation_text="연준 목표 2%")
    fig.update_yaxes(title="전년비 %")
    cm.show(fig, 380)

    if "cpi" in res:
        r = res["cpi"]
        st.subheader("월별 예측과 기저효과")
        tbl = pd.DataFrame({
            "월": [f"{d:%Y-%m}" for d in r["yoy_fut"].index],
            "예측 전월비(%)": r["mm_fut"].values,
            "빠져나가는 1년 전 전월비(%)": list(r["base"]) + [np.nan] * (months - len(r["base"])),
            "예측 전년비(%)": r["yoy_fut"].values,
            "범위 하단": r["lo"].values, "범위 상단": r["hi"].values,
        })
        tbl["전년비 방향"] = np.where(tbl["예측 전월비(%)"] > tbl["빠져나가는 1년 전 전월비(%)"], "⬆️ 올라감", "⬇️ 내려감")
        st.dataframe(tbl, hide_index=True, use_container_width=True,
                     column_config={c: st.column_config.NumberColumn(format="%.2f") for c in tbl.columns if c not in ("월", "전년비 방향")})
        st.caption("예측 전월비가 '빠져나가는 1년 전 전월비'보다 크면 전년비가 올라가고, 작으면 내려가요.")

        st.subheader("성적표: 과거에 얼마나 맞혔나")
        m1, m2 = st.columns(2)
        m1.metric("모델 평균 오차 (다음 달 전월비)", f"{r['mae']:.3f}%p")
        m2.metric("단순 예측 오차 (최근 3개월 평균)", f"{r['mae_naive']:.3f}%p",
                  f"{(r['mae_naive'] - r['mae']):+.3f}%p 모델이 {'더 정확' if r['mae'] < r['mae_naive'] else '덜 정확'}",
                  delta_color="normal" if r["mae"] < r["mae_naive"] else "inverse")
        st.caption("최근 60개월 동안 '그때까지의 데이터로만' 다음 달을 예측해 실제와 비교한 결과예요.")

    st.subheader("시장과 소비자가 보는 앞으로의 물가")
    exp_cols = st.columns(3)
    for col, sid in zip(exp_cols, ["T5YIE", "T10YIE", "MICH"]):
        s = fred.get(sid)
        if s is None or s.dropna().empty:
            continue
        s = s.dropna()
        prev = s[s.index <= s.index[-1] - pd.Timedelta(days=30)]
        col.metric(FRED_SERIES[sid], f"{s.iloc[-1]:.2f}%",
                   f"{s.iloc[-1] - prev.iloc[-1]:+.2f}%p (1개월)" if len(prev) else None, delta_color="inverse")
    be = fred.get("T10YIE")
    if be is not None and not be.dropna().empty:
        b = be.dropna().tail(500)
        fig2 = go.Figure(go.Scatter(x=b.index, y=b, line=dict(color=cm.BLUE, width=2), name="10년 기대인플레이션"))
        fig2.add_hline(y=2, line_dash="dash", line_color=cm.UP, annotation_text="2%")
        fig2.update_yaxes(title="%")
        cm.show(fig2, 260)
        st.caption("채권시장이 앞으로 10년 평균 물가를 몇 %로 보는지예요. 2.5%를 넘어 오르면 시장이 물가를 걱정하기 시작했다는 신호예요.")
    st.caption("참고용 통계 모델이며 실제 발표치와 다를 수 있어요. 큰 사건(전쟁·관세·공급 충격)은 모델이 미리 알 수 없어요.")
