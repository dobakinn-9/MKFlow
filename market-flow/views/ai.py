"""AI 예측: AI 모델 예측 / Claude 시장 전망."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import common as cm
import data as dt
import ml

TONE_ICON = {"긍정": "🟢", "부정": "🔴", "중립": "⚪"}


@st.cache_data(ttl=3600 * 6, show_spinner="AI 모델을 학습하고 과거 성적을 검증하는 중… (처음엔 30초~1분 걸려요)")
def _run_model(t: str, period: str, fwd: int):
    p = cm.prices()
    sc, _ = cm.score_bundle(t, period)
    return ml.run(p, t, sc, fwd)


def _gauge(prob: float) -> go.Figure:
    color = cm.UP if prob >= 0.55 else cm.DOWN if prob <= 0.45 else cm.MUTED
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=prob * 100, number={"suffix": "%", "font": {"size": 44}},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": color},
               "steps": [{"range": [0, 45], "color": "rgba(229,83,75,0.15)"},
                         {"range": [45, 55], "color": "rgba(154,160,166,0.15)"},
                         {"range": [55, 100], "color": "rgba(63,185,127,0.15)"}],
               "threshold": {"line": {"color": "#E6E8EB", "width": 2}, "value": 50}}))
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=20, b=0))
    return fig


def model():
    t, nm, fwd = cm.target(), cm.target_name(), cm.fwd()
    st.title(f"AI 모델 예측 · {nm}")
    cm.warn_if_sample(cm.price_note())
    cm.explain(f"""
- **무엇을 예측하나요?** "{fwd}거래일 뒤 {nm}가 오늘보다 높을까?"의 **확률**이에요. 사이드바에서 시장과 기간을 바꿀 수 있어요.
- **어떻게?** 과거 수년간의 지수 흐름·변동성·금리·유가·환율·반도체·신용·구리/금·흐름 점수 등 약 17개 특성을 학습한
  두 가지 머신러닝 모델(로지스틱 회귀 + 그래디언트 부스팅)의 평균이에요.
- **믿어도 되나요?** 아래 **성적표**가 핵심이에요. 과거 각 시점에서 '그때까지의 데이터로만' 학습하고 그 뒤를 맞혔는지 기록한 결과예요.
  주가 예측은 원래 어려워서, 50%를 조금 넘기는 것도 쉽지 않아요. 성적이 '늘 오른다고 찍기'보다 못하면 참고만 하세요.
""")
    try:
        res = _run_model(t, cm.period(), fwd)
    except ImportError:
        st.error("scikit-learn이 설치돼 있지 않아요. requirements.txt에 scikit-learn을 추가했는지 확인해 주세요.")
        return
    if not res.get("ok"):
        st.info(res.get("reason", "예측을 만들 수 없어요."))
        return

    prob = res["prob"]
    view = "오를 가능성이 더 높다" if prob >= 0.55 else "내릴 가능성이 더 높다" if prob <= 0.45 else "방향을 판단하기 어렵다"
    a, b = st.columns([1, 1])
    with a:
        st.markdown(f"#### {fwd}거래일 뒤 상승 확률")
        st.plotly_chart(_gauge(prob), use_container_width=True)
    with b:
        st.markdown("#### AI의 판단")
        st.markdown(f"**{view}**고 봐요.")
        st.markdown(f"**신뢰도:** {ml.confidence(res)}")
        st.caption(f"기준일 {pd.Timestamp(res['asof']).date()} · 사용한 특성 {len(res['features'])}개")

    st.subheader("오늘 예측에 영향을 준 요인")
    top = res["contrib"].head(8)
    st.plotly_chart(cm.hbar(top["특성"], top["기여"], "{:+.2f}"), use_container_width=True)
    st.caption("오른쪽(초록)은 상승 확률을 높인 요인, 왼쪽(빨강)은 낮춘 요인이에요. (로지스틱 회귀 기준)")

    st.subheader("성적표: 과거에 얼마나 맞혔나")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("적중률", f"{res['hit']:.1f}%", f"{res['hit'] - res['naive']:+.1f}%p vs 찍기", delta_color="normal")
    c2.metric("늘 같은 쪽 찍기", f"{res['naive']:.1f}%", help="과거에 늘 '오른다'(또는 '내린다')고 했을 때의 적중률")
    c3.metric("AUC", "—" if np.isnan(res["auc"]) else f"{res['auc']:.3f}", help="0.5 = 동전 던지기, 1.0 = 완벽. 0.55 이상이면 의미 있는 편")
    c4.metric("검증한 날 수", f"{res['n_oos']:,}일")

    st.markdown("**확률 구간별 실제 결과** — AI가 높은 확률을 줬을 때 실제로 더 자주 올랐다면 쓸모가 있다는 뜻이에요.")
    st.dataframe(res["calib"], hide_index=True, use_container_width=True,
                 column_config={"실제 상승 비율(%)": st.column_config.NumberColumn(format="%.0f"),
                                "평균 수익률(%)": st.column_config.NumberColumn(format="%+.2f")})

    st.subheader("AI 예측 확률의 변화 (최근 1년)")
    h = res["history"].dropna().tail(250)
    if not h.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=h.index, y=h["price"], name=nm, line=dict(color=cm.BLUE, width=2)))
        fig.add_trace(go.Scatter(x=h.index, y=h["prob"] * 100, name="상승 확률(%) 오른쪽", yaxis="y2",
                                 line=dict(color=cm.ORANGE, width=1.5)))
        fig.update_layout(yaxis=dict(title=nm), yaxis2=dict(title="%", overlaying="y", side="right", range=[0, 100]))
        cm.show(fig, 340)
    st.caption("참고용 통계 모델이며 투자 권유가 아닙니다. 모델은 6시간마다 다시 학습해요.")


def outlook():
    st.title("Claude 시장 전망")
    f = dt.DATA_DIR / "ai_outlook.json"
    if not f.exists():
        st.info("data/ai_outlook.json 파일이 없어요.")
        return
    o = json.loads(f.read_text(encoding="utf-8"))
    st.caption(f"작성 {o['asof']} · 기간 {o['horizon']} · {o['author']}")
    st.info(o["headline"])

    tabs = st.tabs([m["name"] for m in o["markets"]])
    for tab, m in zip(tabs, o["markets"]):
        with tab:
            st.markdown(f"#### 판단: {m['stance']}")
            sc = m["scenarios"]
            fig = go.Figure(go.Bar(
                x=[s["prob"] for s in sc], y=[s["name"] for s in sc], orientation="h",
                marker_color=[cm.UP if s["tone"] == "긍정" else cm.DOWN if s["tone"] == "부정" else cm.MUTED for s in sc],
                text=[f"{s['prob']}%" for s in sc], textposition="outside"))
            fig.update_layout(yaxis=dict(autorange="reversed"), xaxis=dict(range=[0, 100], title="확률(%)"),
                              height=60 + 45 * len(sc), margin=dict(l=10, r=40, t=10, b=10), hovermode=False)
            st.plotly_chart(fig, use_container_width=True)
            for s in sc:
                st.markdown(f"{TONE_ICON.get(s['tone'], '')} **{s['name']} ({s['prob']}%)** — {s['desc']}")
            st.markdown("**지켜볼 신호**")
            st.markdown("\n".join(f"- {w}" for w in m["watch"]))
            st.success("🔄 **판단을 바꿀 조건**: " + m["change_mind"])

    st.subheader("주요 위험 요인")
    risks = pd.DataFrame(o["risks"]).rename(columns={"name": "위험", "level": "중요도", "note": "설명"})
    st.dataframe(risks, hide_index=True, use_container_width=True)
    st.caption(o["disclaimer"] + " Claude에게 \"전망 업데이트해줘\"라고 하면 최신 상황으로 다시 써 드려요.")
    st.caption("'AI 모델 예측'(데이터 학습)과 이 전망(뉴스·맥락 판단)이 같은 방향이면 신호가 더 강하고, 엇갈리면 불확실성이 크다는 뜻이에요.")
