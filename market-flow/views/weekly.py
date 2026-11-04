"""주간 흐름 리포트: 한 주 동안 무엇이 바뀌었고 다음 주 무엇을 볼지."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import streamlit as st

import analysis as an
import common as cm
import data as dt
from config import SCORE_TARGETS

WEEK_TICKERS = [("^KS11", "코스피", "%"), ("^KQ11", "코스닥", "%"), ("^GSPC", "S&P 500", "%"), ("^IXIC", "나스닥", "%"),
                ("^SOX", "미국 반도체 (SOX)", "%"), ("^TNX", "미 10년물 금리", "bp"), ("KRW=X", "원/달러", "%"),
                ("DX-Y.NYB", "달러인덱스", "%"), ("CL=F", "WTI 유가", "%"), ("GC=F", "금", "%"), ("^VIX", "VIX", "p")]


def _reports() -> list[dict]:
    d = dt.DATA_DIR / "weekly"
    out = []
    for f in sorted(d.glob("*.json"), reverse=True) if d.exists() else []:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def week_numbers(p: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """그 주 직전 종가 → 그 주 마지막 종가 변화."""
    rows = []
    for t, nm, unit in WEEK_TICKERS:
        if t not in p:
            continue
        s = p[t].dropna()
        before, within = s[s.index < start], s[(s.index >= start) & (s.index <= end + pd.Timedelta(hours=23))]
        if before.empty or within.empty:
            continue
        a, b = float(before.iloc[-1]), float(within.iloc[-1])
        ch = (b - a) * 100 if unit == "bp" else (b - a) if unit == "p" else (b / a - 1) * 100
        rows.append({"지표": nm, "주간 변화": ch, "단위": unit, "주말 값": b,
                     "주중 고점": float(within.max()), "주중 저점": float(within.min())})
    return pd.DataFrame(rows)


def _fmt(v, unit):
    return f"{v:+.0f}bp" if unit == "bp" else f"{v:+.2f}p" if unit == "p" else f"{v:+.2f}%"


def _auto_section(p: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp):
    wk = week_numbers(p, start, end)
    if not wk.empty:
        show = wk.copy()
        show["주간 변화"] = [_fmt(v, u) for v, u in zip(show["주간 변화"], show["단위"])]
        st.dataframe(show.drop(columns=["단위"]), hide_index=True, use_container_width=True,
                     column_config={c: st.column_config.NumberColumn(format="%,.2f") for c in ("주말 값", "주중 고점", "주중 저점")})
    # 수급
    lines = []
    f, _ = cm.flows("KOSPI")
    if f is not None and len(f):
        w = f[(f.index >= start) & (f.index <= end)].sum() / 1e8
        if len(w):
            lines.append(f"**코스피 수급 (주간 합계)**: 외국인 {w['외국인']:+,.0f}억 · 기관 {w['기관']:+,.0f}억 · 개인 {w['개인']:+,.0f}억")
    sec, _, _ = cm.sector_flows()
    if sec is not None and len(sec):
        s = sec[(sec["date"] >= start) & (sec["date"] <= end)]
        if len(s):
            g = s.groupby("sector")["외국인"].sum().sort_values() / 1e8
            r = s.groupby("sector")["등락률"].apply(lambda x: ((1 + x.fillna(0) / 100).prod() - 1) * 100).sort_values()
            lines.append(f"**외국인이 가장 많이 산 분야**: {g.index[-1]} ({g.iloc[-1]:+,.0f}억) · **가장 많이 판 분야**: {g.index[0]} ({g.iloc[0]:+,.0f}억)")
            lines.append(f"**가장 강한 분야**: {r.index[-1]} ({r.iloc[-1]:+.1f}%) · **가장 약한 분야**: {r.index[0]} ({r.iloc[0]:+.1f}%)")
    # 게이지·흐름 점수
    try:
        from views import riskgauge as rg
        gdf = rg.gauge_frame(p)
        if len(gdf):
            gs = gdf["종합"]
            a, b = gs[gs.index < start], gs[gs.index <= end + pd.Timedelta(hours=23)]
            if len(a) and len(b):
                lines.append(f"**위험선호 게이지**: {a.iloc[-1]:.0f} ({rg.label(a.iloc[-1])[0]}) → {b.iloc[-1]:.0f} ({rg.label(b.iloc[-1])[0]})")
    except Exception:
        pass
    for t, nm in SCORE_TARGETS.items():
        try:
            sc, _ = cm.score_bundle(t, cm.period())
            sc = sc.dropna()
            a, b = sc[sc.index < start], sc[sc.index <= end + pd.Timedelta(hours=23)]
            if len(a) and len(b):
                lines.append(f"**{nm} 흐름 점수**: {a.iloc[-1]:+.1f} → {b.iloc[-1]:+.1f} ({an.regime(float(b.iloc[-1]))})")
        except Exception:
            pass
    if lines:
        st.markdown("  \n".join(lines))


def page():
    st.title("주간 흐름 리포트")
    cm.explain("""
- 매주 월요일 아침 Claude가 **지난주 무엇이 바뀌었고, 이번 주 무엇을 볼지** 한 페이지로 정리해 쌓아요.
- 위쪽 **숫자 요약**은 앱이 자료로 직접 계산해요(지수·금리·환율·수급·분야·게이지·흐름 점수).
- 지난 리포트도 골라 볼 수 있어서, 흐름이 어떻게 이어져 왔는지 되짚어 보기 좋아요.
""")
    p = cm.prices()
    reps = _reports()
    today = pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None).normalize()
    mon = today - pd.Timedelta(days=today.weekday())

    opts = ["이번 주 (진행 중)"] + [f"{r['week_start'][5:].replace('-', '/')}~{r['week_end'][5:].replace('-', '/')} · {r['title']}" for r in reps]
    pick = st.selectbox("어느 주를 볼까요?", range(len(opts)), format_func=lambda i: opts[i], index=1 if reps else 0, key="wk_pick")

    if pick == 0:
        st.subheader(f"이번 주 지금까지 ({mon:%m/%d}~)")
        _auto_section(p, mon, today)
        ev, _ = dt.load_events()
        if ev is not None:
            left = ev[(ev["date"] >= today) & (ev["date"] <= mon + pd.Timedelta(days=6))]
            if len(left):
                st.markdown("**이번 주 남은 일정**")
                st.dataframe(left[["when", "title", "importance", "note"]].rename(
                    columns={"when": "언제", "title": "일정", "importance": "중요도", "note": "의미"}),
                    hide_index=True, use_container_width=True)
        st.caption("이번 주 리포트는 다음 주 월요일 아침에 Claude가 정리해 올려요.")
        cm.source(cm.price_note())
        return

    r = reps[pick - 1]
    start, end = pd.Timestamp(r["week_start"]), pd.Timestamp(r["week_end"])
    st.subheader(r["title"])
    st.caption(f"{r['week_start']} ~ {r['week_end']} · {r.get('report_date', '')} 작성 · {r.get('author', 'Claude')}")
    with st.container(border=True):
        st.markdown(r["headline"])

    st.markdown("#### 📌 지난주 무엇이 바뀌었나")
    st.markdown("\n".join(f"{i}. {x}" for i, x in enumerate(r.get("changed", []), 1)))

    st.markdown("#### 🔢 숫자로 본 한 주")
    _auto_section(p, start, end)

    if r.get("markets"):
        st.markdown("#### 🗺️ 시장별 정리")
        for m in r["markets"]:
            st.markdown(f"- **{m['name']}**: {m['summary']}")

    if r.get("next_week"):
        st.markdown("#### 📅 이번 주(리포트 다음 주) 볼 것")
        st.dataframe(pd.DataFrame(r["next_week"]).rename(columns={"date": "날짜", "what": "일정", "why": "왜 중요한가"}),
                     hide_index=True, use_container_width=True)
    if r.get("watch"):
        st.markdown("#### 👀 흐름이 바뀌는 신호")
        st.markdown("\n".join(f"- {x}" for x in r["watch"]))
    st.caption("투자 권유가 아닌 참고용 정리예요.")
    cm.source(cm.price_note() + " · 리포트: data/weekly/")
