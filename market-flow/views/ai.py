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
import tracker

TONE_ICON = {"긍정": "🟢", "부정": "🔴", "중립": "⚪"}


@st.cache_data(ttl=3600 * 6, show_spinner="AI 모델을 학습하고 과거 성적을 검증하는 중… (처음엔 30초~1분 걸려요)")
def _run_model(t: str, period: str, fwd: int, w_lr: float):
    p = cm.prices()
    sc, _ = cm.score_bundle(t, period)
    return ml.run(p, t, sc, fwd, w_lr=w_lr)


def _nearest_h(fwd: int) -> int:
    return min(tracker.HORIZONS, key=lambda h: abs(h - fwd))


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
        preds = tracker.load_predictions()
        lw = tracker.live_weights(preds, t, _nearest_h(fwd))
        res = _run_model(t, cm.period(), fwd, round(lw["w_lr"], 2))
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

    live = tracker.live_report(preds, t, _nearest_h(fwd))
    if live.get("n_graded", 0) >= 30 and live["hit"] < live["naive"]:
        st.error(f"⚠️ 실전 성적 경고: 최근 채점된 {live['n_graded']}건의 실제 적중률 {live['hit']:.0f}%가 "
                 f"'늘 같은 쪽 찍기'({live['naive']:.0f}%)보다 낮아요. 지금은 이 모델을 믿지 마세요.")
    st.caption(f"모델 가중치(실전 성적 반영): 로지스틱 회귀 {res['w_lr']:.0%} · 그래디언트 부스팅 {1 - res['w_lr']:.0%} "
               f"— 로지스틱 {res['p_lr']:.0%}, 부스팅 {res['p_gb']:.0%} · 자세한 내용은 'AI 성장 기록' 메뉴")

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


def growth():
    t, nm = cm.target(), cm.target_name()
    st.title(f"AI 성장 기록 · {nm}")
    cm.explain("""
**AI가 스스로 나아지는 방법**
1. **매일 예측을 기록해요.** 하루 2번(한국 07:40 미국 장 마감 후 · 16:10 한국 장 마감 후) GitHub에서 자동 작업이 돌면서 코스피·S&P 500의 1주(5거래일)·1개월(20거래일) 뒤 상승 확률을 저장해요.
2. **만기가 되면 채점해요.** 5·20거래일이 지나면 실제로 올랐는지 확인해 맞음/틀림을 기록해요. 과거 데이터로 시뮬레이션한 '모의고사'가 아니라 **실제 미래를 맞혔는지** 보는 '실전 성적'이에요.
3. **잘 맞힌 모델에 더 귀 기울여요.** 두 모델(로지스틱 회귀, 그래디언트 부스팅) 중 최근 60건에서 더 정확했던 쪽의 가중치를 높여요. 기록이 적을 땐 반반에서 시작해서, 쌓일수록 성적 차이를 더 크게 반영해요.
4. **실전 성적이 나쁘면 경고해요.** 30건 이상 채점됐는데 '늘 같은 쪽 찍기'보다 못하면 'AI 모델 예측' 화면에 경고가 떠요.
5. **Claude 전망도 채점해요.** 전망 작성 후 약 1개월(21거래일) 뒤, 지수가 ±3% 넘게 움직였는지로 상승·기본·하락 중 무엇이 맞았는지 기록해요.
""")
    preds = tracker.load_predictions()
    h = st.radio("예측 기간", tracker.HORIZONS, index=1, horizontal=True, key="gr_h",
                 format_func=lambda x: {5: "1주 (5거래일)", 20: "1개월 (20거래일)"}.get(x, f"{x}일"))
    g = preds[(preds["target"] == t) & (preds["horizon"] == h)].copy() if len(preds) else preds
    if g is None or len(g) == 0:
        st.info("아직 기록된 예측이 없어요. GitHub 자동 작업이 처음 실행되면(한국 07:40·16:10, 또는 Actions 탭에서 수동 실행) 첫 기록이 생겨요.")
    else:
        rep = tracker.live_report(preds, t, h)
        w = tracker.live_weights(preds, t, h)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("기록된 예측", f"{rep['n_total']}건", f"채점 대기 {rep['n_pending']}건", delta_color="off")
        if rep["n_graded"]:
            c2.metric("실전 적중률", f"{rep['hit']:.1f}%", f"{rep['hit'] - rep['naive']:+.1f}%p vs 찍기")
            c3.metric("최근 20건 적중률", f"{rep['recent_hit']:.1f}%")
        else:
            c2.metric("실전 적중률", "채점 전")
            c3.metric("최근 20건 적중률", "—")
        c4.metric("채점 완료", f"{rep['n_graded']}건")
        if rep["n_graded"] < 30:
            st.caption("채점된 기록이 30건 미만이라 아직 성적을 판단하기 일러요. 기록이 쌓일수록 믿을 만해져요.")

        st.subheader("두 모델의 경쟁과 가중치")
        a, b = st.columns(2)
        with a:
            fig = go.Figure(go.Bar(x=["로지스틱 회귀", "그래디언트 부스팅"], y=[w["w_lr"] * 100, (1 - w["w_lr"]) * 100],
                                   marker_color=[cm.BLUE, cm.ORANGE], text=[f"{w['w_lr']:.0%}", f"{1 - w['w_lr']:.0%}"],
                                   textposition="outside"))
            fig.update_layout(yaxis=dict(range=[0, 100], title="현재 가중치(%)"), hovermode=False,
                              height=260, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        with b:
            if rep["n_graded"]:
                st.metric("로지스틱 회귀 실전 적중률", f"{rep['hit_lr']:.1f}%")
                st.metric("그래디언트 부스팅 실전 적중률", f"{rep['hit_gb']:.1f}%")
            st.caption(f"최근 {w['n']}건 기준. 정확도 점수(브라이어, 낮을수록 좋음): "
                       + ("—" if np.isnan(w["brier_lr"]) else f"로지스틱 {w['brier_lr']:.3f} · 부스팅 {w['brier_gb']:.3f}"))

        g = g.sort_values("asof")
        if g["w_lr"].notna().sum() > 1:
            st.subheader("가중치 변화 — AI가 어느 모델을 더 믿게 됐나")
            fig2 = go.Figure(go.Scatter(x=g["asof"], y=g["w_lr"] * 100, mode="lines+markers", line=dict(color=cm.BLUE)))
            fig2.add_hline(y=50, line_dash="dot", line_color=cm.MUTED)
            fig2.update_yaxes(range=[15, 85], title="로지스틱 회귀 가중치(%)")
            cm.show(fig2, 240)
        gg = g[g["actual_up"].notna()]
        if len(gg) >= 5:
            st.subheader("실전 적중률 누적 추이")
            cum = gg["hit"].expanding().mean() * 100
            fig3 = go.Figure(go.Scatter(x=gg["asof"], y=cum, line=dict(color=cm.UP, width=2)))
            fig3.add_hline(y=50, line_dash="dot", line_color=cm.MUTED)
            fig3.update_yaxes(range=[0, 100], title="%")
            cm.show(fig3, 240)

        st.subheader("예측 일기장 (최근 30건)")
        show = g.tail(30).iloc[::-1].copy()
        show["결과"] = np.where(show["actual_up"].isna(), "⏳ 채점 대기",
                              np.where(show["hit"] == 1, "✅ 맞음", "❌ 틀림"))
        show["상승 확률"] = (show["prob"] * 100).round(0).astype(int).astype(str) + "%"
        show["실제 수익률"] = show["ret_pct"].map(lambda v: "—" if pd.isna(v) else f"{v:+.2f}%")
        show["예측일"] = pd.to_datetime(show["asof"]).dt.strftime("%Y-%m-%d")
        st.dataframe(show[["예측일", "상승 확률", "regime", "실제 수익률", "결과"]].rename(columns={"regime": "당시 국면"}),
                     hide_index=True, use_container_width=True)

    st.subheader("Claude 전망 채점표")
    log = tracker.load_outlook_log()
    if len(log) == 0:
        st.info("아직 기록된 Claude 전망이 없어요. 자동 작업이 처음 실행되면 오늘 전망이 기록돼요.")
        return
    lg = log.copy()
    lg["시장"] = lg["market"].map({"kospi": "코스피", "spx": "S&P 500"})
    lg["작성일"] = pd.to_datetime(lg["asof"]).dt.strftime("%Y-%m-%d")
    lg["시나리오(상승/기본/하락)"] = lg["p_up"].astype(int).astype(str) + " / " + lg["p_base"].astype(int).astype(str) + " / " + lg["p_down"].astype(int).astype(str)
    lg["실제"] = np.where(lg["outcome"].isna(), "⏳ 채점 대기",
                        lg["outcome"].astype(str) + " (" + lg["ret_pct"].map(lambda v: "" if pd.isna(v) else f"{v:+.1f}%") + ")")
    lg["판정"] = np.where(lg["outcome"].isna(), "—", np.where(lg["top_hit"] == 1, "✅ 가장 높게 본 시나리오 적중", "❌ 빗나감"))
    st.dataframe(lg[["작성일", "시장", "stance", "시나리오(상승/기본/하락)", "실제", "판정"]].rename(columns={"stance": "판단"}).iloc[::-1],
                 hide_index=True, use_container_width=True)
    done = lg[lg["outcome"].notna()]
    if len(done):
        st.markdown(f"채점 {len(done)}건 · 가장 높게 본 시나리오 적중률 **{done['top_hit'].mean() * 100:.0f}%** · "
                    f"실제 결과에 줬던 평균 확률 **{done['prob_on_outcome'].mean():.0f}%**")
    st.caption("상승: 21거래일 뒤 +3% 초과 · 하락: −3% 미만 · 기본: 그 사이. 이 기록은 다음 전망을 쓸 때 참고해요.")
