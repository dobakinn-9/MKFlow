"""사건 표시 차트: 지수가 왜 움직였는지 차트 위에 사건과 그날 뉴스를 함께 보여줘요."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import common as cm
import data as dt

INDICES = {"^KS11": ("코스피", "KR", 2.0), "^GSPC": ("S&P 500", "US", 1.5), "^IXIC": ("나스닥", "US", 2.0),
           "^SOX": ("미국 반도체 (SOX)", "US", 3.0), "^KQ11": ("코스닥", "KR", 2.5)}
CAT_STYLE = {"통화정책": ("🏦", "#F59E0B", "diamond"), "경제지표": ("📊", "#A78BFA", "square"),
             "실적": ("💼", "#14B8A6", "triangle-up"), "정치": ("🗳️", "#EC4899", "star"),
             "지정학": ("🌍", "#F97316", "star-diamond")}


def _news_for(day: pd.Timestamp, news: pd.DataFrame | None) -> str:
    """그날 장 움직임을 설명하는 뉴스 요약: 다음 날(최대 3일 뒤) 아침에 쓴 요약을 찾아요."""
    if news is None or news.empty:
        return ""
    after = news[(news["date"] > day) & (news["date"] <= day + pd.Timedelta(days=3))]
    if after.empty:
        same = news[news["date"] == day]
        return str(same["summary"].iloc[0]) if len(same) else ""
    return str(after["summary"].iloc[0])


def _wrap(t: str, n: int = 38) -> str:
    out, line = [], ""
    for w in str(t).split(" "):
        if len(line) + len(w) > n:
            out.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    out.append(line)
    return "<br>".join(out)


def page():
    st.title("사건 표시 차트")
    cm.explain("""
- 지수 차트 위에 **그날 있었던 사건**(중앙은행 회의, 경제지표, 대형 실적, 선거 등)과 **크게 움직인 날**을 함께 표시해요.
- 점에 손가락을 대거나 마우스를 올리면 **무슨 일이 있었는지**와 **그날 뉴스 요약**이 나와요.
- ▲ 빨강 = 크게 오른 날, ▼ 파랑 = 크게 내린 날 (코스피 ±2%, S&P 500 ±1.5% 등 지수별 기준).
- 사건 기록은 매일 아침 Claude가 전날 시장을 움직인 일을 덧붙여 쌓아요.
""")
    p = cm.prices()
    cm.warn_if_sample(cm.price_note())
    c1, c2 = st.columns(2)
    with c1:
        t = st.selectbox("지수", [k for k in INDICES if k in p], format_func=lambda k: INDICES[k][0], key="ev_idx")
    with c2:
        span = st.radio("기간", ["1개월", "3개월", "6개월", "1년"], index=1, horizontal=True, key="ev_span")
    n = {"1개월": 22, "3개월": 66, "6개월": 130, "1년": 252}[span]
    nm, mk, th = INDICES[t]
    s = p[t].dropna().tail(n)
    ret = s.pct_change() * 100
    log, _ = dt.load_event_log()
    news, _ = dt.load_news_sentiment()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s, name=nm, line=dict(color=cm.BLUE, width=2),
                             hovertemplate="%{x|%m/%d} %{y:,.2f}<extra></extra>"))

    # 큰 움직임
    big = ret[ret.abs() >= th]
    for up in (True, False):
        b = big[big > 0] if up else big[big < 0]
        if b.empty:
            continue
        txt = [f"<b>{d:%m/%d} {r:+.2f}%</b><br>{_wrap(_news_for(d, news)) or '뉴스 요약 없음'}" for d, r in b.items()]
        fig.add_trace(go.Scatter(x=b.index, y=s.reindex(b.index), mode="markers", name="크게 오른 날" if up else "크게 내린 날",
                                 marker=dict(symbol="triangle-up" if up else "triangle-down", size=13,
                                             color=cm.UP if up else cm.DOWN, line=dict(color="#0B0F17", width=1)),
                                 hovertext=txt, hoverinfo="text"))

    # 사건
    if log is not None and len(log):
        ev = log[(log["date"] >= s.index.min()) & (log["date"] <= s.index.max() + pd.Timedelta(days=3))]
        ev = ev[ev["market"].isin([mk, "ALL"]) | (ev["importance"] == "상")]
        for cat, g in ev.groupby("category"):
            icon, col, sym = CAT_STYLE.get(cat, ("📌", cm.MUTED, "circle"))
            # 휴장일 사건은 다음 거래일에 표시
            xs = [s.index[s.index >= d][0] if (s.index >= d).any() else s.index[-1] for d in g["date"]]
            ys = [float(s.loc[x]) * 1.012 for x in xs]
            txt = [f"<b>{icon} {r['title']}</b> ({r['date']:%m/%d})<br>{_wrap(r['note'])}" for _, r in g.iterrows()]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers", name=f"{icon} {cat}",
                                     marker=dict(symbol=sym, size=11, color=col, line=dict(color="#0B0F17", width=1)),
                                     hovertext=txt, hoverinfo="text"))
    fig.update_layout(hovermode="closest", hoverlabel=dict(align="left"))
    cm.show(fig, 460)

    # 표: 큰 움직임과 이유
    st.subheader("크게 움직인 날과 그 이유")
    rows = []
    for d, r in big.sort_index(ascending=False).items():
        evs = ""
        if log is not None and len(log):
            same = log[(log["date"] <= d) & (log["date"] >= d - pd.Timedelta(days=2))]
            same = same[same["market"].isin([mk, "ALL"]) | (same["importance"] == "상")]
            evs = " · ".join(same["title"])
        rows.append({"날짜": d.strftime("%Y-%m-%d"), "등락": r, "같은 무렵 사건": evs or "—",
                     "그날 뉴스 요약": _news_for(d, news) or "—"})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                     column_config={"등락": st.column_config.NumberColumn(format="%+.2f%%")})
    else:
        st.info(f"이 기간에는 {nm}이(가) ±{th}% 넘게 움직인 날이 없어요.")
    with st.expander("사건 기록 전체 보기"):
        if log is not None and len(log):
            show = log.sort_values("date", ascending=False).copy()
            show["date"] = show["date"].dt.strftime("%Y-%m-%d")
            st.dataframe(show.rename(columns={"date": "날짜", "market": "시장", "title": "사건", "category": "분류",
                                              "importance": "중요도", "note": "결과·의미"}),
                         hide_index=True, use_container_width=True)
        else:
            st.info("사건 기록이 아직 없어요.")
    st.caption("뉴스 요약은 다음 날 아침 Claude가 쓴 '뉴스 분위기 점수' 요약이에요. 2026-10-21부터 쌓였어요.")
    cm.source(cm.price_note() + " · 사건: data/event_log.csv")
