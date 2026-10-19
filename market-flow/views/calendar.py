"""일정: 이벤트 캘린더."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import common as cm
import data as dt


def events():
    st.title("이벤트 캘린더")
    cm.explain("""
- 실적 발표, FOMC, 물가·고용 지표, 선거 같은 일정 전후로 변동성이 커져요.
- **중요도 '상'** 일정이 다가오면 큰 방향 베팅보다 결과를 확인하는 게 안전해요.
- 일정은 저장소의 `market-flow/data/events.csv` 파일에서 읽어요. Claude에게 "일정 업데이트해줘"라고 하면 최신 일정으로 고쳐 드려요.
""")
    ev, note = dt.load_events()
    if ev is None:
        st.info(note)
        return
    today = pd.Timestamp.today().normalize()
    up = ev[ev["date"] >= today].copy()
    past = ev[ev["date"] < today].copy()

    st.subheader("다가오는 일정")
    if up.empty:
        st.info("등록된 앞으로의 일정이 없어요.")
    for _, r in up.iterrows():
        d = (r["date"] - today).days
        badge = {"상": "🔴", "중": "🟠"}.get(r["importance"], "⚪")
        with st.container(border=True):
            a, b = st.columns([1, 4])
            a.metric("남은 날", "오늘" if d == 0 else f"D-{d}")
            b.markdown(f"**{badge} {r['title']}** · {r['category']}\n\n{r['when']} — {r['note']}")

    if not past.empty:
        with st.expander("지난 일정"):
            st.dataframe(past[["when", "title", "category", "note"]].rename(
                columns={"when": "시기", "title": "일정", "category": "분류", "note": "메모"}),
                hide_index=True, use_container_width=True)
    cm.source(note)
