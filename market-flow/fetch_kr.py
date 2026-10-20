"""한국 시장 데이터를 미리 받아 data/kr/ 에 저장해요.

Streamlit Cloud(해외 서버)와 GitHub 서버에서는 한국거래소(pykrx) 응답이 비어 있어서,
네이버 증권 모바일 API로 받아요. GitHub Actions가 평일마다 실행하고 앱은 저장된 파일을 읽어요.

저장 파일
- flows_KOSPI.csv / flows_KOSDAQ.csv : 날짜별 개인·외국인·기관 순매수 (원) — 최근 약 3년
- index_KOSPI.csv / index_KOSDAQ.csv : 날짜별 종가, 거래대금(원) — 거래대금은 수집한 날부터 쌓여요
- breadth_ALL.csv                    : 날짜별 상승·하락·보합 종목 수 (전체 업종 합계) — 수집한 날부터 쌓여요
- sectors.csv                        : 최근 거래일 업종별 등락률
- status.txt                         : 마지막 실행 결과

직접 실행:  cd market-flow && python fetch_kr.py
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

OUT = Path(__file__).parent / "data" / "kr"
OUT.mkdir(parents=True, exist_ok=True)
API = "https://m.stock.naver.com/api"
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
      "Referer": "https://m.stock.naver.com/"}
FLOW_DAYS = 750
log: list[str] = []
S = requests.Session()
S.headers.update(UA)


def say(msg: str):
    print(msg, flush=True)
    log.append(msg)


def num(x) -> float:
    if x is None:
        return float("nan")
    s = str(x).replace(",", "").replace("+", "").strip()
    for unit in ("천주", "백만", "억", "%"):
        s = s.replace(unit, "")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def get(path: str, **params):
    for k in range(3):
        try:
            r = S.get(f"{API}/{path}", params=params, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(0.5 * (k + 1))
    return None


def read(name: str) -> pd.DataFrame:
    f = OUT / f"{name}.csv"
    if not f.exists():
        return pd.DataFrame()
    return pd.read_csv(f, parse_dates=["date"]).set_index("date")


def write(df: pd.DataFrame, name: str):
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.index.name = "date"
    df.to_csv(OUT / f"{name}.csv")
    return df


# ── 지수 일별 시세 (거래일 목록도 여기서 얻어요) ──────────
def prices(code: str, n: int) -> pd.Series:
    rows, page = [], 1
    while len(rows) < n and page <= 40:
        data = get(f"index/{code}/price", pageSize=60, page=page)
        if not data:
            break
        rows += data
        if len(data) < 60:
            break
        page += 1
        time.sleep(0.1)
    s = pd.Series({pd.Timestamp(r["localTradedAt"]): num(r["closePrice"]) for r in rows}).sort_index()
    return s.tail(n)


# ── 투자자별 순매수 ──────────────────────────────────────
def update_flows(code: str, trade_days: pd.DatetimeIndex) -> pd.DataFrame:
    name = f"flows_{code}"
    old = read(name)
    have = set(old.index) if len(old) else set()
    # 최근 3거래일은 잠정치가 확정치로 바뀔 수 있어 다시 받아요.
    recent = set(trade_days[-3:])
    todo = [d for d in trade_days if d not in have or d in recent]
    rows = {}
    for i, d in enumerate(todo):
        data = get(f"index/{code}/trend", bizdate=d.strftime("%Y%m%d"))
        if data and data.get("bizdate") == d.strftime("%Y%m%d"):
            rows[d] = {"개인": num(data.get("personalValue")) * 1e8, "외국인": num(data.get("foreignValue")) * 1e8,
                       "기관": num(data.get("institutionalValue")) * 1e8}
        if i % 100 == 99:
            say(f"    … {code} 수급 {i + 1}/{len(todo)}일")
        time.sleep(0.08)
    new = pd.DataFrame.from_dict(rows, orient="index")
    df = pd.concat([old, new]) if len(old) else new
    df = write(df.tail(FLOW_DAYS + 50), name)
    say(f"  ✓ {name}: 새로 {len(rows)}일 · 전체 {len(df)}일 ({df.index.min():%Y-%m-%d} ~ {df.index.max():%Y-%m-%d})")
    return df


# ── 거래대금 (오늘 값만 제공돼서 날마다 쌓아요) ───────────
def update_index(code: str, px: pd.Series):
    name = f"index_{code}"
    old = read(name)
    df = old.copy() if len(old) else pd.DataFrame(columns=["종가", "거래대금"], dtype=float)
    df = df.reindex(df.index.union(px.index))
    df["종가"] = px.reindex(df.index).fillna(df["종가"])
    info = get(f"index/{code}/integration")
    if info:
        vals = {x.get("code"): x.get("value") for x in info.get("totalInfos", [])}
        tv = num(vals.get("accumulatedTradingValue")) * 1e6  # 백만 원 → 원
        if pd.notna(tv) and tv > 0:
            df.loc[px.index[-1], "거래대금"] = tv
    df = write(df, name)
    say(f"  ✓ {name}: 종가 {len(df)}일 · 거래대금 {int(df['거래대금'].notna().sum())}일치")


# ── 업종 등락·상승/하락 종목 수 ──────────────────────────
def update_sectors_breadth(day: pd.Timestamp):
    groups, page = [], 1
    while page <= 10:
        data = get("stocks/industry", page=page, pageSize=100)
        if not data or not data.get("groups"):
            break
        groups += data["groups"]
        if len(groups) >= data.get("totalCount", 0):
            break
        page += 1
    if not groups:
        say("  ✗ 업종 데이터를 받지 못했어요")
        return
    sec = pd.DataFrame([{"업종": g["name"], "등락률": num(g.get("changeRate")), "종목 수": g.get("totalCount"),
                         "상승": g.get("riseCount"), "하락": g.get("fallCount")} for g in groups])
    sec.to_csv(OUT / "sectors.csv", index=False)
    br = read("breadth_ALL")
    row = pd.DataFrame({"상승": [int(sec["상승"].sum())], "하락": [int(sec["하락"].sum())],
                        "보합": [int(sum(g.get("steadyCount", 0) for g in groups))]}, index=[day])
    br = write(pd.concat([br, row]) if len(br) else row, "breadth_ALL")
    say(f"  ✓ sectors: {len(sec)}개 업종 · breadth_ALL: {len(br)}일치 (최근 상승 {row['상승'].iat[0]} / 하락 {row['하락'].iat[0]})")


def probe_stock():
    for path, params in [("stock/005930/trend", {"pageSize": 3}), ("stock/005930/trend", {}),
                         ("stock/005930/price", {"pageSize": 2}), ("stock/005930/integration", {}),
                         ("stocks/industry/278", {"page": 1, "pageSize": 3})]:
        try:
            r = S.get(f"{API}/{path}", params=params, timeout=15)
            say(f"  [probe] {path} {params}: HTTP {r.status_code} · {r.text[:700]!r}")
        except Exception as e:
            say(f"  [probe] {path}: {e}")


def main():
    probe_stock()
    say(f"한국 데이터 받기 시작 ({date.today()}) · 출처: 네이버 증권")
    ok = 0
    for code in ("KOSPI", "KOSDAQ"):
        try:
            px = prices(code, FLOW_DAYS)
            if px.empty:
                raise RuntimeError("시세 응답 없음")
            say(f"  · {code} 시세 {len(px)}일 ({px.index.min():%Y-%m-%d} ~ {px.index.max():%Y-%m-%d})")
            update_flows(code, px.index)
            update_index(code, px)
            ok += 1
        except Exception as e:
            say(f"  ✗ {code} 실패: {type(e).__name__}: {str(e)[:160]}")
    try:
        update_sectors_breadth(read("index_KOSPI").index.max())
    except Exception as e:
        say(f"  ✗ 업종·종목 수 실패: {type(e).__name__}: {str(e)[:160]}")
    (OUT / "probe_naver.html").unlink(missing_ok=True)
    (OUT / "status.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    say(f"완료: 시장 {ok}/2")
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
