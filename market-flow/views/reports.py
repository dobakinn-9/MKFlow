"""시장 보고서: 세계 동향 브리핑 / 숨은 지표."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analysis as an
import common as cm
import data as dt
from config import HIDDEN, WORLD, name

TONE = {"긍정": "🟢 한국에 우호적", "부정": "🔴 한국에 부담", "중립": "⚪ 영향 혼재"}


def world():
    st.title("세계 동향 브리핑")
    brief, note = dt.load_world_brief()
    if not brief:
        st.info(note)
        return
    st.caption(f"기준일 {brief['asof']} · 지역별로 '지금 무슨 일이 있는지', '잘 알려지지 않은 사실', '한국에 미치는 영향'을 정리했어요.")
    st.info(brief["summary"])

    # 세계 증시 성적표
    st.subheader("세계 증시 성적표")
    p = cm.prices()
    per = st.radio("기간", ["1주", "1개월", "3개월", "1년"], index=1, horizontal=True, key="world_per")
    days = {"1주": 5, "1개월": 21, "3개월": 63, "1년": 252}[per]
    tickers = ["^KS11", "^GSPC"] + list(WORLD)
    tbl = an.period_returns(p, tickers, {per: days}).sort_values(per, ascending=False)
    if not tbl.empty:
        st.plotly_chart(cm.hbar(tbl["이름"], tbl[per], "{:+.1f}%"), use_container_width=True)
    st.caption("한국(코스피)과 미국(S&P 500)을 함께 넣어 상대적인 위치를 볼 수 있게 했어요.")

    # 지역별 브리핑
    st.subheader("지역별 브리핑")
    items = brief["items"]
    labels = [f"{it['icon']} {it['region']}" for it in items]
    tabs = st.tabs(labels)
    for tab, it in zip(tabs, items):
        with tab:
            st.markdown(f"### {it['title']}")
            st.caption(TONE.get(it.get("tone"), ""))
            st.markdown("\n".join(f"- {x}" for x in it["points"]))
            st.warning("🔎 **잘 알려지지 않은 사실**\n\n" + it["hidden"])
            st.success("🇰🇷 **한국에 미치는 영향**\n\n" + it["korea"])
            if it.get("sources"):
                st.caption("출처: " + " · ".join(f"[{s['title']}]({s['url']})" for s in it["sources"]
                                                if str(s.get("url", "")).startswith("https://")))
    st.caption("이 브리핑은 공개 뉴스와 공식 발표를 조사해 정리한 것이에요. Claude에게 \"세계 동향 업데이트해줘\"라고 하면 최신 내용으로 바꿔 드려요.")


def _signal(spec: dict, p: pd.DataFrame):
    """숨은 지표 하나의 (시계열, 현재값, 1개월 변화%, 신호, 설명) 계산."""
    kind = spec["kind"]
    if kind == "ratio":
        if spec["num"] not in p or spec["den"] not in p:
            return None
        s = (p[spec["num"]] / p[spec["den"]]).dropna()
        s = s / s.iloc[-252] * 100 if len(s) > 252 else s / s.iloc[0] * 100
    else:
        if spec["series"] not in p:
            return None
        s = p[spec["series"]].dropna()
    if len(s) < 25:
        return None
    ch = (s.iloc[-1] / s.iloc[-22] - 1) * 100
    if kind == "ratio":
        good = ch > 2 if spec["good_when_up"] else ch < -2
        bad = ch < -2 if spec["good_when_up"] else ch > 2
        reading = f"한 달 새 {ch:+.1f}%"
    elif kind == "level_change":
        bad = ch < -3 if spec["bad_when_down"] else ch > 3
        good = ch > 3 if spec["bad_when_down"] else ch < -3
        reading = f"{s.iloc[-1]:,.2f} · 한 달 새 {ch:+.1f}%"
    else:  # level
        v = s.iloc[-1]
        bad, good = v >= spec["warn"], v <= spec["calm"]
        reading = f"현재 {v:.0f} (불안 {spec['warn']} 이상 · 안정 {spec['calm']} 이하)"
    sig = "🟢 긍정" if good else "🔴 경고" if bad else "⚪ 중립"
    return s, ch, sig, reading


def hidden():
    st.title("숨은 지표")
    st.caption("뉴스에는 잘 안 나오지만 전문 투자자들이 시장의 속마음을 읽을 때 보는 신호들이에요. 신호는 최근 한 달 변화를 기준으로 판단해요.")
    p = cm.prices()
    results = []
    for spec in HIDDEN:
        r = _signal(spec, p)
        if r:
            results.append((spec, *r))

    if not results:
        st.info("지표 데이터를 불러오지 못했어요.")
        return

    # 요약판
    st.subheader("한눈에 보는 신호")
    summary = pd.DataFrame([{"지표": sp["title"], "신호": sig, "현재": reading} for sp, s, ch, sig, reading in results])
    st.dataframe(summary, hide_index=True, use_container_width=True)
    n_good = sum("긍정" in r[3] for r in results)
    n_bad = sum("경고" in r[3] for r in results)
    verdict = ("위험을 즐기는 분위기예요." if n_good - n_bad >= 3 else
               "속으로는 경계심이 커지고 있어요." if n_bad - n_good >= 3 else "뚜렷한 쏠림 없이 엇갈리고 있어요.")
    st.markdown(f"🟢 {n_good}개 · 🔴 {n_bad}개 · ⚪ {len(results) - n_good - n_bad}개 → 시장의 속마음은 **{verdict}**")

    # 지표별 상세
    st.subheader("지표별 자세히 보기")
    n = cm.span_picker("hid_span")
    for spec, s, ch, sig, reading in results:
        with st.container(border=True):
            a, b = st.columns([3, 1])
            a.markdown(f"#### {spec['title']}")
            b.markdown(f"**{sig}**")
            st.markdown(spec["what"])
            st.caption("💡 왜 중요할까: " + spec["why"])
            ss = s.tail(n)
            fig = go.Figure(go.Scatter(x=ss.index, y=ss, line=dict(color=cm.BLUE, width=2)))
            if spec["kind"] == "level":
                fig.add_hline(y=spec["warn"], line_dash="dot", line_color=cm.DOWN)
                fig.add_hline(y=spec["calm"], line_dash="dot", line_color=cm.UP)
            elif spec["kind"] == "ratio":
                fig.update_yaxes(title="1년 전 = 100")
            cm.show(fig, 240)
            st.caption(reading)
    cm.source(cm.price_note())
