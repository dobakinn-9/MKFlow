"""수급: 투자자별 매매 / 수급 타이밍 신호."""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import pandas as pd

import common as cm
import flow_signals as fs


def _streak(s) -> int:
    """마지막 날부터 같은 방향(+/−)이 며칠 연속인지. 양수=연속 순매수."""
    sign = (s > 0).astype(int) - (s < 0).astype(int)
    last = sign.iloc[-1]
    n = 0
    for v in reversed(sign.tolist()):
        if v == last and v != 0:
            n += 1
        else:
            break
    return n * last


def investors():
    st.title("투자자별 매매")
    cm.explain("""
- 한국 시장은 **외국인** 매매가 지수 방향과 가장 밀접해요. 며칠 **연속**으로 사고파는지가 특히 중요해요.
- 외국인이 판 물량을 **기관과 개인 중 누가 받아내는지**도 봐요. 개인만 받아내는 하락장은 오래가는 경우가 많아요.
- 누적 차트가 꾸준히 오르는 주체가 '지금 시장을 끌고 가는 쪽'이에요.
""")
    mkt = st.radio("시장", ["KOSPI", "KOSDAQ"], horizontal=True, key="inv_mkt",
                   format_func=lambda x: {"KOSPI": "코스피", "KOSDAQ": "코스닥"}[x])
    f, note = cm.flows(mkt)
    if f is None:
        st.info(note + "\n\n`pykrx` 설치 여부와 한국거래소 접속을 확인해 주세요.")
        return
    f = f / 1e8
    if "외국인" in f:
        st_ = _streak(f["외국인"])
        c1, c2, c3 = st.columns(3)
        c1.metric("외국인 연속", f"{abs(st_)}일 {'순매수' if st_ > 0 else '순매도'}")
        c2.metric("최근 5일 외국인", f"{f['외국인'].tail(5).sum():+,.0f}억 원")
        c3.metric("최근 20일 외국인", f"{f['외국인'].tail(20).sum():+,.0f}억 원")
    fig = go.Figure()
    for col, color in [("외국인", cm.BLUE), ("기관", cm.ORANGE), ("개인", cm.MUTED)]:
        if col in f:
            fig.add_trace(go.Bar(x=f.index, y=f[col], name=col, marker_color=color))
    fig.update_layout(barmode="relative", yaxis_title="억 원")
    st.subheader("일별 순매수")
    cm.show(fig, 360)
    st.subheader("누적 순매수")
    cm.show(px.line(f.cumsum(), labels={"value": "억 원", "index": "", "variable": ""},
                    color_discrete_map={"외국인": cm.BLUE, "기관": cm.ORANGE, "개인": cm.MUTED}), 300)
    s20 = f.tail(20).sum()
    st.markdown(" · ".join(f"최근 20일 {k} **{v:+,.0f}억 원**" for k, v in s20.items()))
    cm.source(note)



def _gauge(v: float):
    color = cm.UP if v >= 15 else cm.DOWN if v <= -15 else cm.MUTED
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=v, number={"font": {"size": 40}},
        title={"text": f"수급 점수<br><span style='font-size:0.8em'>{fs.score_label(v)}</span>"},
        gauge={"axis": {"range": [-100, 100], "tickvals": [-100, -50, -15, 15, 50, 100]}, "bar": {"color": color},
               "steps": [{"range": [-100, -15], "color": "rgba(229,83,75,0.15)"},
                         {"range": [-15, 15], "color": "rgba(154,160,166,0.15)"},
                         {"range": [15, 100], "color": "rgba(63,185,127,0.15)"}]}))
    fig.update_layout(height=270, margin=dict(l=20, r=20, t=70, b=0))
    return fig


def timing():
    st.title("수급 타이밍 신호")
    st.caption("외국인·기관·개인의 매매 흐름에서 '흐름이 바뀌는 순간'을 찾아 보여줘요. "
               "과거 통계를 보여주는 참고 자료이며 매매 권유가 아니에요.")
    cm.explain("""
- **수급 점수 (−100 ~ +100)**: 외국인·기관의 최근 5일·20일 순매수를 각자의 평소 수준과 비교해 합친 점수예요. +15 이상이면 매수 우위, −15 이하면 매도 우위예요.
- **신호 6가지**
  - 🟢 **외국인 매수 전환**: 한 달간 팔던 외국인이 최근 5일 합계로 순매수 전환
  - 🟢 **외국인·기관 동반 매수**: 두 큰손이 3일 연속 함께 순매수
  - 🟢 **바닥 다이버전스**: 지수는 한 달 새 3% 넘게 빠졌는데 외국인은 그동안 순매수
  - 🔴 **외국인 연속 매도**: 외국인이 5일 연속 팔면서 지수도 하락
  - 🔴 **개인 홀로 매수**: 외국인·기관이 모두 팔고 개인만 3일 연속 받는 장
  - 🔴 **고점 다이버전스**: 지수는 한 달 새 3% 넘게 올랐는데 외국인은 그동안 순매도
- 아래 **검증표**에서 같은 신호가 과거에 나온 뒤 지수가 실제로 어떻게 움직였는지 확인할 수 있어요. '평소'보다 확실히 좋거나 나빴던 신호만 의미가 있어요.
""")
    mkt = st.radio("시장", ["KOSPI", "KOSDAQ"], horizontal=True, key="tm_mkt",
                   format_func=lambda x: {"KOSPI": "코스피", "KOSDAQ": "코스닥"}[x])
    f, note = cm.flows_long(mkt)
    if f is None or len(f) < 80:
        st.info((note or "데이터가 부족해요.") + "\n\n한국거래소(pykrx) 접속이 필요해요. 해외 서버에서는 막힐 수 있어요.")
        return
    t = "^KS11" if mkt == "KOSPI" else "^KQ11"
    p = cm.prices()
    if t not in p:
        st.info("지수 데이터를 불러오지 못했어요.")
        return
    sig = fs.compute(f, p[t])
    last = sig.iloc[-1]
    nm = "코스피" if mkt == "KOSPI" else "코스닥"

    a, b = st.columns([1, 1])
    with a:
        st.plotly_chart(_gauge(float(last["score"]) if pd.notna(last["score"]) else 0), use_container_width=True)
    with b:
        st.markdown(f"#### 지금 수급 상태 ({sig.index[-1]:%m/%d} 기준)")
        stv = int(last["f_streak"])
        st.markdown(f"- 외국인: **{abs(stv)}일 연속 {'순매수' if stv > 0 else '순매도'}**")
        st.markdown(f"- 외국인 5일 {last['f5']:+,.0f}억 · 20일 {last['f20']:+,.0f}억")
        st.markdown(f"- 기관 5일 {last['i5']:+,.0f}억 · 20일 {last['i20']:+,.0f}억")
        st.markdown(f"- {nm} 20일 등락 {last['px20']:+.1f}%")

    st.subheader("최근 5거래일 안에 나온 신호")
    act = fs.active_now(sig, 5)
    bt = fs.backtest(sig).set_index("key")
    if not act:
        st.info("최근 5거래일 동안 새로 나온 신호가 없어요. 수급이 뚜렷한 방향 없이 흘러가는 중이에요.")
    for s in act:
        r = bt.loc[s["key"]]
        icon = "🟢" if s["kind"] == "매수" else "🔴"
        stat = (f"과거 {int(r['횟수'])}번 중 20일 뒤 평균 **{r['20일 뒤 평균(%)']:+.1f}%**, "
                f"오른 확률 **{r['20일 뒤 상승 확률(%)']:.0f}%** (평소 {r['평소 20일 평균(%)']:+.1f}%)"
                if r["횟수"] and pd.notna(r["20일 뒤 평균(%)"]) else "과거 사례가 부족해 통계를 낼 수 없어요.")
        box = st.success if s["kind"] == "매수" else st.error
        box(f"{icon} **{s['name']}** ({s['date']:%m/%d})\n\n{s['desc']}\n\n{stat}")

    st.subheader(f"{nm}와 신호 위치 (최근 1년)")
    h = sig.tail(250)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=h.index, y=h["price"], name=nm, line=dict(color=cm.BLUE, width=2)))
    for key, sname, kind, _ in fs.SIGNALS:
        d = h[h[key].fillna(False)]
        if d.empty:
            continue
        up = kind == "매수"
        fig.add_trace(go.Scatter(x=d.index, y=d["price"] * (0.985 if up else 1.015), mode="markers", name=sname,
                                 marker=dict(symbol="triangle-up" if up else "triangle-down", size=11,
                                             color=cm.UP if up else cm.DOWN,
                                             line=dict(width=1, color="#0E1117"))))
    fig.add_trace(go.Bar(x=h.index, y=h["score"], name="수급 점수 (오른쪽)", yaxis="y2", opacity=0.25,
                         marker_color=[cm.UP if v > 0 else cm.DOWN for v in h["score"].fillna(0)]))
    fig.update_layout(yaxis=dict(title=nm), yaxis2=dict(overlaying="y", side="right", range=[-100, 100], title="점수"))
    cm.show(fig, 420)
    st.caption("▲ 매수 쪽 신호 · ▼ 주의 신호 · 막대는 수급 점수예요. 마우스를 올리면 신호 이름이 보여요.")

    st.subheader("신호 검증표: 과거에 이 신호가 나온 뒤")
    show = fs.backtest(sig).drop(columns=["key"])
    show["마지막 발생"] = pd.to_datetime(show["마지막 발생"]).dt.strftime("%Y-%m-%d").fillna("—")

    def verdict(r):
        if not r["횟수"] or pd.isna(r["20일 뒤 평균(%)"]) or r["횟수"] < 5:
            return "표본 부족"
        diff = r["20일 뒤 평균(%)"] - r["평소 20일 평균(%)"]
        good = diff > 0.5 if r["종류"] == "매수" else diff < -0.5
        return "✅ 통했음" if good else "❌ 별 차이 없음"
    show["판정"] = show.apply(verdict, axis=1)
    pct = {c: st.column_config.NumberColumn(format="%+.2f") for c in show.columns if "평균" in c}
    prob = {c: st.column_config.NumberColumn(format="%.0f") for c in show.columns if "확률" in c}
    st.dataframe(show, hide_index=True, use_container_width=True, column_config=pct | prob)
    st.caption("판정: 매수 신호는 20일 뒤 평균이 평소보다 0.5%p 넘게 높았으면, 주의 신호는 0.5%p 넘게 낮았으면 '통했음'. "
               "신호가 5번 미만이면 우연일 수 있어 표본 부족으로 둬요.")

    st.subheader("수급 점수 구간별 20일 뒤 결과")
    st.dataframe(fs.score_buckets(sig, 20), hide_index=True, use_container_width=True,
                 column_config={"20일 뒤 평균(%)": st.column_config.NumberColumn(format="%+.2f"),
                                "상승 확률(%)": st.column_config.NumberColumn(format="%.0f")})
    st.caption(f"최근 약 3년({len(sig):,}거래일) 데이터로 계산했어요. 과거 통계는 미래를 보장하지 않아요.")
    cm.source(note)
