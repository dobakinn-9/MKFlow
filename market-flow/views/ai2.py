"""AI 예측(추가) · AI 분석 도구 화면."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ai_extra as ax
import common as cm
import data as dt
from config import SCORE_TARGETS, name

FLOW_MKT = {"^KS11": "KOSPI", "^KQ11": "KOSDAQ"}


def _flows_for(t: str):
    mkt = FLOW_MKT.get(t)
    if not mkt:
        return None
    f, _ = cm.flows_long(mkt)
    return f


def _trust(auc: float, better: bool) -> str:
    if np.isnan(auc) or auc < 0.55 or not better:
        return "낮음 — 과거 검증에서 뚜렷한 예측력이 없었어요. 참고만 하세요."
    if auc < 0.62:
        return "보통 — 과거에 어느 정도 예측력이 있었어요."
    return "비교적 높음 — 과거 검증에서 의미 있는 예측력을 보였어요(그래도 틀릴 수 있어요)."


# ═══ AI 예측 ═══════════════════════════════════════════════
@st.cache_data(ttl=3600 * 6, show_spinner="급락 위험 모델을 학습하고 검증하는 중… (처음엔 30초 정도 걸려요)")
def _crash(t: str, period: str):
    sc, _ = cm.score_bundle(t, period)
    return ax.crash_risk(cm.prices(), t, sc, _flows_for(t))


def crash():
    st.title("급락 위험 경보")
    cm.explain("""
- **무엇을 예측하나요?** "앞으로 1주(5거래일) 안에 지수가 오늘보다 크게 빠지는 날이 올까?"의 확률이에요. 기준은 코스피·코스닥 **−5%**, S&P 500 **−3%**예요.
- **왜 이게 더 잘 맞나요?** 오를지 내릴지 '방향'은 맞히기 어렵지만, 시장이 **출렁이는 시기**는 몰려서 오는 성질이 있어 훨씬 잘 맞혀요(변동성 군집).
- **신호등**: 평소 급락 확률과 비교해 2.5배 이상이면 🔴 폭풍 경보, 1.5배 이상이면 🟠 주의, 그 아래면 🟢 평온이에요.
- 코스피·코스닥은 외국인·기관 수급도 학습 재료로 써요.
""")
    cols = st.columns(3)
    for col, t in zip(cols, ["^KS11", "^KQ11", "^GSPC"]):
        with col:
            try:
                r = _crash(t, cm.period())
            except ImportError:
                st.error("scikit-learn이 필요해요.")
                return
            if not r.get("ok"):
                st.info(f"{name(t)}: {r.get('reason')}")
                continue
            st.markdown(f"#### {name(t)}")
            st.markdown(f"## {r['level']}")
            st.metric(f"1주 안 −{r['thr']:.0f}% 급락 확률", f"{r['prob'] * 100:.1f}%",
                      f"평소의 {r['ratio']:.1f}배", delta_color="inverse")
            st.caption(f"평소 확률 {r['base'] * 100:.1f}% · 검증 {r['n']:,}일 · AUC {r['auc']:.2f}")
    t = st.radio("자세히 볼 시장", ["^KS11", "^KQ11", "^GSPC"], horizontal=True, format_func=name, key="crash_t")
    r = _crash(t, cm.period())
    if not r.get("ok"):
        return
    st.subheader("성적표: 경보가 실제로 맞았나")
    a, b, c = st.columns(3)
    a.metric("확률 상위 20% 날의 실제 급락 비율", f"{r['top_rate'] * 100:.1f}%")
    b.metric("확률 하위 50% 날의 실제 급락 비율", f"{r['low_rate'] * 100:.1f}%")
    c.metric("AUC (0.5=동전, 1=완벽)", f"{r['auc']:.3f}")
    st.markdown(f"**신뢰도**: {_trust(r['auc'], r['top_rate'] > r['low_rate'] * 1.3)}")
    st.subheader("급락 확률 추이 (최근 1년)")
    h = r["hist"].tail(250)
    p = cm.prices()[t].reindex(h.index)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=p.index, y=p, name=name(t), line=dict(color=cm.BLUE, width=2)))
    fig.add_trace(go.Scatter(x=h.index, y=h["prob"] * 100, name="급락 확률 % (오른쪽)", yaxis="y2", fill="tozeroy",
                             line=dict(color=cm.DOWN, width=1), fillcolor="rgba(229,83,75,0.2)"))
    hit = h[h["y"] == 1]
    fig.add_trace(go.Scatter(x=hit.index, y=p.reindex(hit.index), mode="markers", name="실제로 급락이 시작된 날",
                             marker=dict(color=cm.DOWN, size=6, symbol="x")))
    fig.update_layout(yaxis=dict(title=name(t)), yaxis2=dict(overlaying="y", side="right", title="%", rangemode="tozero"))
    cm.show(fig, 380)
    top = r["contrib"].head(7)
    st.subheader("오늘 확률에 영향을 준 요인")
    st.plotly_chart(cm.hbar(top["특성"], top["기여"], "{:+.2f}"), use_container_width=True)
    st.caption("오른쪽(초록)은 급락 확률을 높인 요인, 왼쪽(빨강)은 낮춘 요인이에요. 참고용이며 투자 권유가 아니에요.")


@st.cache_data(ttl=3600 * 6, show_spinner="환율 모델을 학습하는 중…")
def _fx(period: str, fwd: int):
    return ax.fx_forecast(cm.prices(), _flows_for("^KS11"), fwd)


def fx():
    st.title("환율 예측 (원/달러)")
    fwd = cm.fwd()
    cm.explain(f"""
- **방향**: "{fwd}거래일 뒤 원/달러 환율이 지금보다 높을까(원화 약세)?" 확률이에요. 환율 흐름, 달러인덱스, 미국 금리, 코스피, 반도체, 유가, 엔화, VIX를 학습했어요.
- **범위**: 지금의 환율 변동성을 반영해 5·20·60거래일 뒤 있을 법한 범위를 보여줘요.
- 환율이 오르면(원화 약세) 외국인은 한국 주식을 팔고, 수입 물가가 올라요.
""")
    r = _fx(cm.period(), fwd)
    p = cm.prices()
    if "KRW=X" not in p:
        st.info("환율 데이터를 불러오지 못했어요.")
        return
    now = p["KRW=X"].dropna().iloc[-1]
    a, b = st.columns(2)
    a.metric("현재 원/달러", f"{now:,.1f}원", cm.fmt_change((now / p['KRW=X'].dropna().iloc[-22] - 1) * 100) + " (1개월)",
             delta_color="inverse")
    if r.get("ok"):
        b.metric(f"{fwd}거래일 뒤 상승(원화 약세) 확률", f"{r['prob'] * 100:.0f}%")
        st.markdown(f"**신뢰도**: {_trust(r['auc'], r['hit'] > max(r['base'], 1 - r['base']) * 100)} "
                    f"(적중률 {r['hit']:.1f}% · AUC {r['auc']:.3f} · 검증 {r['n']:,}일)")
    rf = r.get("range")
    if rf is not None and not rf.empty:
        st.subheader("예상 범위")
        hist = p["KRW=X"].dropna().tail(126)
        last = hist.index[-1]
        xs = [last] + [last + pd.tseries.offsets.BDay(int(h)) for h in rf["horizon"]]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist.index, y=hist, name="원/달러", line=dict(color=cm.BLUE, width=2)))
        for lo, hi, op, lbl in [("q10", "q90", 0.15, "80% 범위"), ("q25", "q75", 0.3, "50% 범위")]:
            fig.add_trace(go.Scatter(x=xs + xs[::-1], y=[now] + list(rf[hi]) + list(rf[lo])[::-1] + [now], fill="toself",
                                     fillcolor=f"rgba(240,163,58,{op})", line=dict(width=0), name=lbl))
        fig.add_trace(go.Scatter(x=xs, y=[now] + list(rf["q50"]), name="중앙값", line=dict(color=cm.ORANGE, dash="dot")))
        cm.show(fig, 340)
        tb = pd.DataFrame({"기간": [f"{h}거래일 뒤" for h in rf["horizon"]], "하단(10%)": rf["q10"], "중앙": rf["q50"],
                           "상단(90%)": rf["q90"]})
        st.dataframe(tb, hide_index=True, use_container_width=True,
                     column_config={c: st.column_config.NumberColumn(format="%,.1f원") for c in ("하단(10%)", "중앙", "상단(90%)")})
    if r.get("ok"):
        top = r["contrib"].head(6)
        st.subheader("오늘 판단에 영향을 준 요인")
        st.plotly_chart(cm.hbar(top["특성"], top["기여"], "{:+.2f}"), use_container_width=True)
        st.caption("오른쪽(초록)은 환율 상승(원화 약세) 쪽, 왼쪽(빨강)은 하락(원화 강세) 쪽 요인이에요.")


def recession():
    st.title("미국 경기침체 확률")
    cm.explain("""
- **뉴욕 연방준비은행이 쓰는 방식**이에요. 장기 금리(10년물)와 단기 금리(3개월물)의 차이로 **12개월 뒤 경기침체에 있을 확률**을 계산해요.
- 단기 금리가 장기 금리보다 높아지면(역전) 시장이 앞으로 금리가 내려갈 만큼 경기가 나빠진다고 본다는 뜻이에요. 지난 50년 동안 미국 경기침체 대부분 전에 역전이 나타났어요.
- 확률이 **30%를 넘으면** 과거에는 대체로 1~2년 안에 침체가 왔어요. 다만 2022~2024년처럼 오래 역전됐는데 침체가 오지 않은 예외도 있어요.
- 여기서는 3개월물 금리를 단순 차이로 써서 뉴욕 연은 공식 수치와 약간 다를 수 있어요.
""")
    rp = ax.recession_prob(cm.prices())
    if rp.empty:
        st.info("금리 데이터를 불러오지 못했어요.")
        return
    now = rp.iloc[-1]
    a, b, c = st.columns(3)
    a.metric("12개월 뒤 침체 확률", f"{now['prob']:.0f}%",
             f"{now['prob'] - rp['prob'].iloc[-4]:+.0f}%p (3개월 전 대비)" if len(rp) > 4 else None, delta_color="inverse")
    b.metric("장단기 금리차 (10년−3개월)", f"{now['spread']:+.2f}%p")
    c.metric("기준 시점", f"{rp.index[-1]:%Y-%m} → {now['target_month']:%Y-%m}")
    level = "🔴 높음" if now["prob"] >= 30 else "🟠 경계" if now["prob"] >= 20 else "🟢 낮음"
    st.markdown(f"### 판단: {level}")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rp["target_month"], y=rp["prob"], name="침체 확률 (12개월 뒤 기준)", fill="tozeroy",
                             line=dict(color=cm.DOWN, width=2), fillcolor="rgba(229,83,75,0.15)"))
    fig.add_trace(go.Scatter(x=rp.index, y=rp["spread"], name="금리차 %p (오른쪽)", yaxis="y2", line=dict(color=cm.BLUE, width=1.5)))
    fig.add_hline(y=30, line_dash="dot", line_color=cm.MUTED, annotation_text="30%")
    fig.update_layout(yaxis=dict(title="침체 확률 %", range=[0, 100]), yaxis2=dict(overlaying="y", side="right", title="%p"))
    cm.show(fig, 380)
    st.caption("빨간 영역은 '그 달에 침체일 확률'이에요. 오늘의 금리차가 12개월 뒤를 가리키도록 옮겨 그렸어요.")


@st.cache_data(ttl=1800)
def _sector_rank():
    sec, _, note = cm.sector_flows()
    if sec is None or sec.empty:
        return None, note
    return ax.sector_rank(sec), note


def sectors_ai():
    st.title("분야별 AI 순위")
    cm.explain("""
- 반도체·2차전지·에너지 등 10개 분야를 **다음 2주 동안 상대적으로 강할 가능성** 순으로 점수를 매겨요.
- **점수 구성**: 큰손(외국인+기관) 5일 수급 35% · 20일 수급 30% · 20일 가격 모멘텀 25% · 단기 과열 보정 10%(최근 5일 너무 많이 오르면 감점). 수급은 각 분야의 평소 수준과 비교해요.
- **검증**: 지금까지 쌓인 데이터에서 점수 순위와 실제 다음 10거래일 수익률 순위가 얼마나 일치했는지(순위 상관)를 보여줘요. +면 맞는 방향, 0 근처면 우연 수준이에요.
- 데이터가 약 120거래일치라 검증 표본이 작아요. 기록이 쌓일수록 믿을 만해져요.
""")
    rk, note = _sector_rank()
    if rk is None:
        st.info(note)
        return
    tb = rk["table"]
    fig = go.Figure(go.Bar(x=tb["점수"], y=tb.index, orientation="h",
                           marker_color=[cm.UP if v > 0 else cm.DOWN for v in tb["점수"]],
                           text=[f"{v:+.2f}" for v in tb["점수"]], textposition="outside"))
    fig.update_layout(yaxis=dict(autorange="reversed"), hovermode=False, height=80 + 40 * len(tb),
                      margin=dict(l=10, r=50, t=36, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(f"**{pd.Timestamp(rk['asof']):%m/%d} 기준** · 상위: " + ", ".join(f"**{s}**" for s in tb.index[:3])
                + " · 하위: " + ", ".join(tb.index[-3:]))
    st.dataframe(tb.reset_index().rename(columns={"sector": "분야"}), hide_index=True, use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(format="%+.2f") for c in tb.columns if c not in ("20일 수익률(%)", "큰손 20일(억)")}
                 | {"20일 수익률(%)": st.column_config.NumberColumn(format="%+.1f%%"),
                    "큰손 20일(억)": st.column_config.NumberColumn(format="%+,.0f")})
    a, b = st.columns(2)
    a.metric("점수 순위 ↔ 실제 10일 수익률 순위 (평균 상관)", "—" if np.isnan(rk["ic_mean"]) else f"{rk['ic_mean']:+.2f}")
    b.metric("상관이 +였던 날 비율", "—" if np.isnan(rk["ic_hit"]) else f"{rk['ic_hit']:.0f}%", f"검증 {rk['ic_n']}일", delta_color="off")
    st.caption("상관이 +0.1 이상이고 +인 날이 55% 넘으면 쓸 만한 편이에요. " + note)


# ═══ AI 분석 도구 ══════════════════════════════════════════
@st.cache_data(ttl=3600 * 6, show_spinner="지금과 닮은 과거를 찾는 중…")
def _analogs(t: str, period: str):
    return ax.analogs(cm.prices(), t)


def analogs():
    t, nm = cm.target(), cm.target_name()
    st.title(f"지금과 닮은 과거 · {nm}")
    cm.explain("""
- 지금의 **주가 흐름(1·3개월 수익률, 120일선 거리), 변동성, VIX, 미국 금리 수준·변화, 유가, 환율, 반도체** 조합과 가장 비슷했던 과거 날짜 5개를 찾아요.
- 그 뒤 60거래일 동안 지수가 어떻게 움직였는지 겹쳐 보여줘요. 경로가 한쪽으로 모이면 신호가 강하고, 제각각이면 불확실하다는 뜻이에요.
- 사이드바에서 '불러올 기간'을 10년으로 늘리면 더 다양한 과거와 비교할 수 있어요.
""")
    r = _analogs(t, cm.period())
    if not r.get("ok"):
        st.info(r.get("reason"))
        return
    tb = r["table"]
    fig = go.Figure()
    colors = [cm.BLUE, cm.ORANGE, cm.UP, "#B07CFF", "#E6E8EB"]
    for (d, path), c in zip(r["paths"].items(), colors):
        fig.add_trace(go.Scatter(x=list(range(len(path))), y=path, name=f"{d:%Y-%m-%d}", line=dict(color=c, width=1.6)))
    L = min(len(p) for p in r["paths"].values())
    avg = np.mean([p[:L] for p in r["paths"].values()], axis=0)
    fig.add_trace(go.Scatter(x=list(range(L)), y=avg, name="평균", line=dict(color="#FFD166", width=3, dash="dot")))
    fig.add_hline(y=0, line_color=cm.MUTED)
    fig.update_layout(xaxis_title="그날 이후 거래일", yaxis_title="수익률 %", hovermode="x unified")
    cm.show(fig, 420)
    up = (tb.iloc[:, 3] > 0).sum() if tb.shape[1] > 3 else 0
    st.markdown(f"닮은 과거 5번 중 60일 뒤 오른 경우 **{up}번** · 평균 **{tb.iloc[:, 3].mean():+.1f}%** · "
                f"그 사이 평균 최저 **{tb['그 사이 최저(%)'].mean():+.1f}%**")
    st.dataframe(tb.assign(날짜=tb["날짜"].dt.strftime("%Y-%m-%d")), hide_index=True, use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(format="%+.1f") for c in tb.columns if "(%)" in c and c != "닮은 정도(%)"}
                 | {"닮은 정도(%)": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f")})
    st.caption("특히 비슷했던 요소: " + ", ".join(r["closest_feats"]) + ". 과거가 반복된다는 보장은 없어요.")
    now = r["now"]
    with st.expander("지금 상태 숫자로 보기"):
        st.dataframe(pd.DataFrame({"항목": [ax.ANALOG_FEATS.get(k, k) for k in now.index], "값": now.values}),
                     hide_index=True, use_container_width=True, column_config={"값": st.column_config.NumberColumn(format="%.3f")})


@st.cache_data(ttl=3600 * 6)
def _sens(t: str, period: str):
    return ax.sensitivity(cm.prices(), t)


def simulator():
    st.title("시나리오 계산기")
    cm.explain("""
- "유가가 20% 오르고 금리가 0.5%p 오르면 코스피는?"처럼 조건을 바꿔 보는 계산기예요.
- 최근 3년 동안 **한 달 단위 변화** 사이의 관계(민감도)를 회귀분석으로 구해 계산해요.
- 결과 범위가 넓으면 그만큼 다른 요인(실적, 뉴스 등)의 영향이 크다는 뜻이에요. 요인끼리 서로 얽혀 있어 하나만 바꾸면 실제보다 과장될 수 있어요.
""")
    t = st.radio("대상 지수", list(SCORE_TARGETS), horizontal=True, format_func=lambda x: SCORE_TARGETS[x], key="sim_t")
    r = _sens(t, cm.period())
    if not r.get("ok"):
        st.info(r.get("reason"))
        return
    limits = {"oil": (-40, 40, 5, "%"), "rate": (-1.0, 1.0, 0.1, "%p"), "fx": (-10, 10, 1, "%"),
              "sox": (-30, 30, 5, "%"), "spx": (-20, 20, 2, "%"), "vix": (-15, 25, 1, "p")}
    shock = {}
    cols = st.columns(2)
    for i, k in enumerate(r["cols"]):
        lo, hi, step, unit = limits[k]
        lbl = ax.SENS[k][2]
        shock[k] = cols[i % 2].slider(f"{lbl} 한 달 변화 ({unit})", float(lo), float(hi), 0.0, float(step), key=f"sim_{k}_{t}")
    pred = r["intercept"] + sum(r["coef"][k] * v for k, v in shock.items())
    lo, hi = pred - 1.28 * r["resid_sd"], pred + 1.28 * r["resid_sd"]
    now = r["now"]
    a, b, c = st.columns(3)
    a.metric(f"{SCORE_TARGETS[t]} 예상 한 달 수익률", f"{pred:+.1f}%")
    b.metric("예상 지수", f"{now * (1 + pred / 100):,.0f}", f"현재 {now:,.0f}", delta_color="off")
    c.metric("80% 범위", f"{lo:+.1f}% ~ {hi:+.1f}%")
    st.subheader("민감도: 각 요인이 한 단위 변할 때 지수 한 달 수익률 변화")
    unit_lbl = {"oil": "유가 +10%", "rate": "금리 +0.1%p", "fx": "환율 +1%", "sox": "반도체 +10%", "spx": "S&P +5%", "vix": "VIX +5p"}
    mult = {"oil": 10, "rate": 0.1, "fx": 1, "sox": 10, "spx": 5, "vix": 5}
    ks = r["cols"]
    vals = [r["coef"][k] * mult[k] for k in ks]
    st.plotly_chart(cm.hbar([unit_lbl[k] for k in ks], vals, "{:+.2f}%"), use_container_width=True)
    st.caption(f"설명력(R²) {r['r2']:.2f} — 지수 한 달 움직임의 약 {r['r2'] * 100:.0f}%를 이 요인들로 설명해요. 표본 {r['n']}개.")


def events_impact():
    st.title("이벤트 영향 분석")
    cm.explain("""
- 과거 **FOMC 금리 결정일**과 **미국 고용보고서 발표일** 전후로 시장이 평균적으로 어떻게 움직였는지 보여줘요.
- 0일 = 발표 당일(미국 시간). 한국 시장은 발표가 한국 시간 새벽이라 **다음 거래일**을 0일로 맞췄어요.
- **반응 크기**: 발표일 하루 움직임 폭(절댓값)이 평소보다 크면, 그 이벤트 때 변동성이 커진다는 뜻이에요.
- 고용보고서 날짜는 '매월 첫 금요일'로 근사했어요(일부 달은 다를 수 있어요).
""")
    ev = st.radio("이벤트", ["FOMC 금리 결정", "미국 고용보고서"], horizontal=True, key="ev_kind")
    p = cm.prices()
    dates = ax.FOMC_DATES if ev.startswith("FOMC") else ax.first_fridays(p.index[0], p.index[-1])
    today = pd.Timestamp.today().normalize()
    nxt = [d for d in pd.to_datetime(dates) if d >= today]
    if nxt:
        st.info(f"다음 {ev}: **{nxt[0]:%Y-%m-%d}** (D-{(nxt[0] - today).days})")
    past = [d for d in pd.to_datetime(dates) if d < today]
    rows = []
    fig = go.Figure()
    for t, lag, c in (("^GSPC", 0, cm.BLUE), ("^KS11", 1, cm.ORANGE), ("^TNX", 0, cm.UP)):
        if t not in p:
            continue
        r = ax.event_study(p[t], past, window=5, lag=lag)
        if not r.get("ok"):
            continue
        if t != "^TNX":
            fig.add_trace(go.Scatter(x=r["x"], y=r["mean"], name=name(t), line=dict(color=c, width=2.5)))
            fig.add_trace(go.Scatter(x=list(r["x"]) + list(r["x"])[::-1], y=list(r["q75"]) + list(r["q25"])[::-1],
                                     fill="toself", fillcolor=c, opacity=0.12, line=dict(width=0), showlegend=False))
        rows.append({"지표": name(t), "표본": r["n"], "발표일 반응 크기": r["react_abs"], "평소 하루 움직임": r["normal_abs"],
                     "발표일 상승 비율(%)": r["up_rate"], "발표 후 5일 평균(%)": r["after_mean"]})
    fig.add_vline(x=0, line_dash="dash", line_color=cm.MUTED, annotation_text="발표일")
    fig.add_hline(y=0, line_color=cm.MUTED)
    fig.update_layout(xaxis_title="발표일 기준 거래일", yaxis_title="발표 전날 대비 %", hovermode="x unified")
    cm.show(fig, 380)
    if rows:
        tb = pd.DataFrame(rows)
        tb["반응 배수"] = tb["발표일 반응 크기"] / tb["평소 하루 움직임"]
        st.dataframe(tb, hide_index=True, use_container_width=True,
                     column_config={"발표일 반응 크기": st.column_config.NumberColumn(format="%.2f"),
                                    "평소 하루 움직임": st.column_config.NumberColumn(format="%.2f"),
                                    "발표일 상승 비율(%)": st.column_config.NumberColumn(format="%.0f"),
                                    "발표 후 5일 평균(%)": st.column_config.NumberColumn(format="%+.2f"),
                                    "반응 배수": st.column_config.NumberColumn(format="%.2f배")})
        st.caption("주가는 % 변화, 미 10년물 금리는 %p 변화예요. 반응 배수가 1보다 크면 그날 평소보다 크게 움직였다는 뜻이에요.")


def news():
    st.title("뉴스 분위기 점수")
    cm.explain("""
- 매일 아침 Claude가 시장 전망을 쓰면서 그날 뉴스의 분위기를 **−5(매우 부정) ~ +5(매우 긍정)**로 매겨 기록해요. 전체, 한국, 미국을 따로 매겨요.
- 점수는 지수가 오르고 내린 것만이 아니라, **앞으로의 위험·기회에 대한 뉴스의 무게**를 반영해요.
- 기록이 쌓이면 '뉴스 분위기가 지수를 앞서갔는지'를 비교할 수 있고, 충분히 쌓이면 AI 모델의 학습 재료로도 써요.
""")
    f = dt.DATA_DIR / "news_sentiment.csv"
    if not f.exists():
        st.info("아직 기록이 없어요. 매일 아침 전망 작업이 기록을 쌓아요.")
        return
    d = pd.read_csv(f, parse_dates=["date"]).sort_values("date")
    last = d.iloc[-1]
    a, b, c = st.columns(3)
    for col, k, lbl in ((a, "overall", "전체"), (b, "kr", "한국"), (c, "us", "미국")):
        prev = d[k].iloc[-2] if len(d) > 1 else None
        col.metric(f"{lbl} 분위기", f"{last[k]:+.0f}", f"{last[k] - prev:+.0f} (전날 대비)" if prev is not None else None)
    st.info(f"**{last['date']:%Y-%m-%d}** · {last['summary']}")
    p = cm.prices()
    fig = go.Figure()
    for k, c, lbl in (("overall", "#FFD166", "전체"), ("kr", cm.ORANGE, "한국"), ("us", cm.BLUE, "미국")):
        fig.add_trace(go.Scatter(x=d["date"], y=d[k], name=lbl, mode="lines+markers", line=dict(color=c, width=2)))
    if "^KS11" in p:
        ks = p["^KS11"].loc[d["date"].min() - pd.Timedelta(days=5):]
        fig.add_trace(go.Scatter(x=ks.index, y=ks, name="코스피 (오른쪽)", yaxis="y2", line=dict(color=cm.MUTED, width=1, dash="dot")))
    fig.add_hline(y=0, line_color=cm.MUTED)
    fig.update_layout(yaxis=dict(range=[-5.5, 5.5], title="분위기"), yaxis2=dict(overlaying="y", side="right", title="코스피"))
    cm.show(fig, 340)
    st.dataframe(d.iloc[::-1].assign(date=d["date"].dt.strftime("%Y-%m-%d")).rename(
        columns={"date": "날짜", "overall": "전체", "kr": "한국", "us": "미국", "summary": "요약"}),
        hide_index=True, use_container_width=True)
    if len(d) >= 20 and "^KS11" in p:
        ks = p["^KS11"].reindex(d["date"], method="ffill")
        fwd5 = (p["^KS11"].shift(-5) / p["^KS11"] - 1).reindex(d["date"], method="ffill") * 100
        corr = pd.Series(d["kr"].values).corr(pd.Series(fwd5.values))
        st.metric("한국 분위기 ↔ 코스피 5일 뒤 수익률 상관", f"{corr:+.2f}", help="+면 분위기가 좋을 때 이후 실제로 올랐다는 뜻")
    else:
        st.caption(f"기록 {len(d)}일째예요. 20일 이상 쌓이면 분위기와 이후 지수 움직임의 관계를 계산해 보여드릴게요.")
