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


# ── 데이터 업데이트 현황 ─────────────────────────────────
def _last_csv(path, col="date"):
    try:
        d = pd.read_csv(path, usecols=[col])[col]
        return pd.to_datetime(d, errors="coerce", utc=col.endswith("utc")).max()
    except Exception:
        return pd.NaT


def _last_json(path, key):
    import json
    try:
        return pd.to_datetime(json.loads(path.read_text(encoding="utf-8")).get(key))
    except Exception:
        return pd.NaT


def status():
    st.title("데이터 업데이트 현황")
    st.caption("앱의 모든 정보가 언제 마지막으로 갱신됐는지 한눈에 보는 곳이에요. 🟢 최신 · 🟡 하루 늦음 · 🔴 확인 필요")
    today = pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None).normalize()
    D, K = dt.DATA_DIR, dt.DATA_DIR / "kr"

    def bday_lag(d):
        if pd.isna(d):
            return None
        return max(len(pd.bdate_range(pd.Timestamp(d).normalize() + pd.Timedelta(days=1), today)) - 1, 0)

    def cal_lag(d):
        return None if pd.isna(d) else (today - pd.Timestamp(d).normalize()).days

    p = cm.prices()
    rows = []
    try:
        fred, _ = dt.load_fred(["ICSA"])
        fred_last = fred["ICSA"].dropna().index.max()
    except Exception:
        fred_last = pd.NaT
    items = [
        # (분류, 이름, 마지막 날짜, 갱신 방식, 늦음 계산, 허용(일))
        ("시세", "세계 지수·금리·환율·원자재 (야후 파이낸스)", p.index.max(), "앱을 열 때마다 (1시간 캐시)", bday_lag, 1),
        ("한국", "투자자별 매매 (코스피·코스닥)", _last_csv(K / "flows_KOSPI.csv"), "평일 09:30·16:00 자동 수집", bday_lag, 1),
        ("한국", "분야별 수급 (반도체·2차전지 등)", _last_csv(K / "sector_flows.csv"), "평일 09:30·16:00 자동 수집", bday_lag, 1),
        ("한국", "업종 등락·상승/하락 종목 수", _last_csv(K / "breadth_ALL.csv"), "평일 09:30·16:00 자동 수집", bday_lag, 1),
        ("한국", "지수 거래대금", _last_csv(K / "index_KOSPI.csv"), "평일 09:30·16:00 자동 수집", bday_lag, 1),
        ("한국", "코스피·코스닥 PER·PBR", _last_csv(K / "valuation_KOSPI.csv"), "평일 09:30·16:00 자동 수집", bday_lag, 1),
        ("한국", "VKOSPI", _last_csv(K / "vkospi.csv"), "해외에서 받을 곳이 없어 실제 변동성으로 대체", bday_lag, 1),
        ("미국", "미국 경제 지표 (FRED)", fred_last, "발표되는 대로 (주간·월간)", cal_lag, 40),
        ("미국", "미국 경제 보고서 확인", _last_json(D / "us_reports_meta.json", "checked"), "매일 08:18 Claude", cal_lag, 0),
        ("AI", "AI 모델 예측 기록·채점", _last_csv(D / "predictions.csv", "created_utc"), "평일 07:40·16:10 자동", bday_lag, 1),
        ("AI", "Claude 시장 전망", _last_json(D / "ai_outlook.json", "asof"), "매일 08:18 Claude", cal_lag, 0),
        ("AI", "뉴스 분위기 점수", _last_csv(D / "news_sentiment.csv"), "매일 08:18 Claude", cal_lag, 0),
        ("보고서", "세계 동향 브리핑", _last_json(D / "world_brief.json", "asof"), "매일 08:18 Claude", cal_lag, 0),
    ]
    for cat, nm, last, how, lagf, ok_lag in items:
        if not pd.isna(last) and getattr(pd.Timestamp(last), "tzinfo", None) is not None:
            last = pd.Timestamp(last).tz_convert("Asia/Seoul").tz_localize(None)
        lag = lagf(last)
        if lag is None and nm == "VKOSPI":
            mark = "🟢 대체 표시 (코스피 실제 변동성, 매일 계산)"
        elif lag is None:
            mark = "⚪ 자료 없음"
        elif lag <= ok_lag:
            mark = "🟢 최신"
        elif lag <= ok_lag + 1:
            mark = "🟡 하루 늦음"
        else:
            mark = "🔴 확인 필요"
        rows.append({"분류": cat, "정보": nm, "마지막 기준일": "—" if pd.isna(last) else pd.Timestamp(last).strftime("%Y-%m-%d"),
                     "상태": mark, "갱신 방식": how})
    ev, _ = dt.load_events()
    if ev is not None:
        n = int((ev["date"] >= today).sum())
        rows.append({"분류": "일정", "정보": "이벤트 캘린더", "마지막 기준일": f"앞으로 일정 {n}개",
                     "상태": "🟢 최신" if n >= 3 else "🔴 확인 필요", "갱신 방식": "매일 08:18 Claude"})
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)
    bad = df[df["상태"].str.startswith("🔴")]
    if len(bad):
        st.warning("확인이 필요한 항목: " + ", ".join(bad["정보"]))
    else:
        st.success("모든 정보가 정상적으로 갱신되고 있어요.")
    st.caption("한국·AI 예측 자료는 장이 열리는 평일 기준이라 주말·공휴일에는 직전 거래일 값이 최신이에요. "
               "미국 경제 지표는 기관 발표 주기(주간·월간)를 따라요. 시세는 휴장일엔 직전 거래일이 마지막이에요.")
    try:
        st.markdown("**한국 자동 수집 마지막 실행 기록**")
        st.code((K / "status.txt").read_text(encoding="utf-8")[-1500:], language=None)
    except Exception:
        pass
