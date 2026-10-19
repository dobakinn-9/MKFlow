"""수급: 투자자별 매매 / 신용잔고."""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import common as cm
import data as dt


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


def credit():
    st.title("신용잔고 (빚투)")
    cm.explain("""
- **신용거래융자 잔고**는 투자자가 증권사에서 돈을 빌려 주식을 산 금액이에요.
- 잔고가 빠르게 불어나면 시장이 과열됐다는 신호예요. 이 상태에서 급락이 오면 **반대매매**(담보 부족으로 강제 매도)가 쏟아져 낙폭이 커져요.
- 지수가 내려가는데 잔고가 줄지 않으면 아직 정리가 덜 됐다는 뜻이에요.
""")
    df, note = dt.load_credit_balance()
    if df is None:
        st.info(
            "신용잔고는 무료로 자동 수집할 수 있는 공개 API가 없어요. 대신 아래 방법으로 볼 수 있어요.\n\n"
            "1. 금융투자협회 통계 사이트 [FreeSIS](https://freesis.kofia.or.kr) → 주식 → 신용공여 현황에서 직접 확인\n"
            "2. 저장소의 `market-flow/data/credit_balance.csv`에 `date,코스피,코스닥`(단위 억 원) 형식으로 값을 넣으면 이 화면에 차트가 그려져요. "
            "Claude에게 \"신용잔고 업데이트해줘\"라고 요청하면 최신 수치를 찾아 넣어 드려요."
        )
        return
    fig = go.Figure()
    for col, color in [("코스피", cm.BLUE), ("코스닥", cm.ORANGE)]:
        if col in df:
            fig.add_trace(go.Scatter(x=df.index, y=df[col] / 1e4, name=col, line=dict(color=color, width=2)))
    fig.update_yaxes(title="조 원")
    cm.show(fig, 360)
    total = df.sum(axis=1) / 1e4
    st.metric("전체 신용잔고", f"{total.iloc[-1]:.1f}조 원",
              f"{total.iloc[-1] - total.iloc[-2]:+.2f}조 원 (직전 대비)" if len(total) > 1 else None)
    cm.source(note)
