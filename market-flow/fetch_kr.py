"""한국 시장 데이터를 미리 받아 data/kr/ 에 저장해요.

Streamlit Cloud(해외 서버)와 GitHub 서버에서는 한국거래소(pykrx) 응답이 비어 있어서,
네이버 증권 모바일 API로 받아요. GitHub Actions가 평일마다 실행하고 앱은 저장된 파일을 읽어요.

저장 파일
- flows_KOSPI.csv / flows_KOSDAQ.csv : 날짜별 개인·외국인·기관 순매수 (원) — 최근 약 3년
- index_KOSPI.csv / index_KOSDAQ.csv : 날짜별 종가, 거래대금(원) — 거래대금은 수집한 날부터 쌓여요
- breadth_ALL.csv                    : 날짜별 상승·하락·보합 종목 수 (전체 업종 합계) — 수집한 날부터 쌓여요
- sectors.csv                        : 최근 거래일 업종별 등락률
- stock_flows.csv / sector_flows.csv : 분야(반도체·2차전지 등) 대표 종목의 순매수와 분야 합계 — 최근 약 130거래일
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
    if int(sec["상승"].sum()) + int(sec["하락"].sum()) == 0:
        say("  · 장 시작 전이라 상승·하락 종목 수는 건너뛰어요")
        return
    br = read("breadth_ALL")
    row = pd.DataFrame({"상승": [int(sec["상승"].sum())], "하락": [int(sec["하락"].sum())],
                        "보합": [int(sum(g.get("steadyCount", 0) for g in groups))]}, index=[day])
    br = write(pd.concat([br, row]) if len(br) else row, "breadth_ALL")
    say(f"  ✓ sectors: {len(sec)}개 업종 · breadth_ALL: {len(br)}일치 (최근 상승 {row['상승'].iat[0]} / 하락 {row['하락'].iat[0]})")


# ── 분야별 수급: 분야 대표 종목의 외국인·기관·개인 순매수 합계 ─────
SECTORS = {
    "반도체": {"005930": "삼성전자", "000660": "SK하이닉스", "042700": "한미반도체", "403870": "HPSP",
             "240810": "원익IPS", "039030": "이오테크닉스"},
    "2차전지": {"373220": "LG에너지솔루션", "006400": "삼성SDI", "003670": "포스코퓨처엠", "247540": "에코프로비엠",
              "086520": "에코프로", "066970": "엘앤에프"},
    "에너지·전력": {"096770": "SK이노베이션", "010950": "S-Oil", "015760": "한국전력", "034020": "두산에너빌리티",
               "267260": "HD현대일렉트릭", "010120": "LS ELECTRIC"},
    "자동차": {"005380": "현대차", "000270": "기아", "012330": "현대모비스"},
    "바이오": {"207940": "삼성바이오로직스", "068270": "셀트리온", "196170": "알테오젠", "000100": "유한양행"},
    "금융": {"105560": "KB금융", "055550": "신한지주", "086790": "하나금융지주", "316140": "우리금융지주"},
    "조선": {"009540": "HD한국조선해양", "042660": "한화오션", "010140": "삼성중공업", "329180": "HD현대중공업"},
    "방산": {"012450": "한화에어로스페이스", "079550": "LIG넥스원", "064350": "현대로템", "047810": "한국항공우주"},
    "인터넷·게임": {"035420": "NAVER", "035720": "카카오", "259960": "크래프톤"},
    "철강·화학": {"005490": "POSCO홀딩스", "051910": "LG화학", "011170": "롯데케미칼"},
}
STOCK_DAYS = 130


def _trend_rows(code: str, **params) -> list[dict]:
    data = get(f"stock/{code}/trend", pageSize=60, **params) or []
    rows = []
    for r in data:
        try:
            close = num(r.get("closePrice"))
            rows.append({"date": pd.Timestamp(r["bizdate"]), "code": code, "close": close,
                         "f_qty": num(r.get("foreignerPureBuyQuant")), "i_qty": num(r.get("organPureBuyQuant")),
                         "p_qty": num(r.get("individualPureBuyQuant")), "f_hold": num(r.get("foreignerHoldRatio"))})
        except Exception:
            continue
    return rows


def update_sector_flows():
    f = OUT / "stock_flows.csv"
    old = pd.read_csv(f, parse_dates=["date"], dtype={"code": str}) if f.exists() else pd.DataFrame()
    rows, bad = [], []
    for sector, stocks in SECTORS.items():
        for code, name in stocks.items():
            got = _trend_rows(code)
            have = old[old["code"] == code] if len(old) else old
            if got and (len(have) == 0 or have["date"].min() > min(r["date"] for r in got) - pd.Timedelta(days=1)):
                # 처음이면 그 이전 60일도 받아 약 120거래일을 채워요.
                oldest = min(r["date"] for r in got)
                got += _trend_rows(code, bizdate=oldest.strftime("%Y%m%d"))
            if not got:
                bad.append(f"{name}({code})")
            for r in got:
                r.update({"name": name, "sector": sector})
            rows += got
            time.sleep(0.08)
    new = pd.DataFrame(rows)
    df = pd.concat([old, new]) if len(old) else new
    if df.empty:
        say("  ✗ 분야별 수급: 받은 데이터가 없어요")
        return
    df = df.drop_duplicates(["date", "code"], keep="last").sort_values(["date", "code"])
    keep_from = df["date"].drop_duplicates().nlargest(STOCK_DAYS).min()
    df = df[df["date"] >= keep_from]
    for k, q in (("외국인", "f_qty"), ("기관", "i_qty"), ("개인", "p_qty")):
        df[k] = df[q] * df["close"]  # 순매수 수량 × 종가 ≈ 순매수 금액(원)
    df.to_csv(f, index=False)
    # 분야 합계와 분야 수익률(종목 평균)
    df = df.sort_values(["code", "date"])
    df["ret"] = df.groupby("code")["close"].pct_change() * 100
    agg = df.groupby(["date", "sector"]).agg(외국인=("외국인", "sum"), 기관=("기관", "sum"), 개인=("개인", "sum"),
                                             등락률=("ret", "mean"), 종목수=("code", "nunique")).reset_index()
    agg.to_csv(OUT / "sector_flows.csv", index=False)
    say(f"  ✓ 분야별 수급: {len(SECTORS)}개 분야 · {df['code'].nunique()}종목 · {df['date'].nunique()}거래일"
        + (f" · 못 받은 종목: {', '.join(bad)}" if bad else ""))


# ── 지수 PER·PBR (시가총액 상위 종목으로 직접 계산) ───────
VAL_TOP = {"KOSPI": 200, "KOSDAQ": 150}


def update_valuation(code: str, day: pd.Timestamp):
    """한국거래소 지수 PER은 해외 서버에서 막혀서, 시총 상위 종목의 PER·PBR로 시총가중 값을 계산해요.
    지수 PER = 시가총액 합 ÷ 순이익 합 (적자 기업 제외, 한국거래소 방식과 같아요)."""
    stocks = []
    for page in range(1, VAL_TOP[code] // 100 + 2):
        js = get(f"stocks/marketValue/{code}", page=page, pageSize=100) or {}
        stocks += js.get("stocks", [])
        if len(stocks) >= VAL_TOP[code]:
            break
    stocks = [x for x in stocks if x.get("stockEndType") == "stock"][:VAL_TOP[code]]
    if not stocks:
        raise RuntimeError("시가총액 순위 응답 없음")
    rows, seen = [], set()
    for x in stocks:
        cd = x.get("itemCode")
        info = get(f"stock/{cd}/integration") or {}
        vals = {i.get("code"): i.get("value") for i in info.get("totalInfos", [])}
        seen |= set(vals)
        rows.append({"cap": num(x.get("marketValue")), "per": num(str(vals.get("per", "")).replace("배", "")),
                     "pbr": num(str(vals.get("pbr", "")).replace("배", "")),
                     "fper": num(str(vals.get("cnsPer", "")).replace("배", "")),
                     "dy": num(vals.get("dividendYieldRatio"))})
        time.sleep(0.05)
    d = pd.DataFrame(rows).dropna(subset=["cap"])
    tot = d["cap"].sum()

    def agg(col):
        v = d[(d[col] > 0)]
        return float(v["cap"].sum() / (v["cap"] / v[col]).sum()) if len(v) else float("nan")

    dy = d.dropna(subset=["dy"])
    out = {"PER": agg("per"), "PBR": agg("pbr"), "추정PER": agg("fper"),
           "배당수익률": float((dy["dy"] * dy["cap"]).sum() / dy["cap"].sum()) if len(dy) else float("nan"),
           "흑자기업 비중(%)": float(d.loc[d["per"] > 0, "cap"].sum() / tot * 100), "종목수": len(d)}
    name = f"valuation_{code}"
    old = read(name)
    df = old.copy() if len(old) else pd.DataFrame(columns=list(out), dtype=float)
    for k, v in out.items():
        df.loc[day, k] = v
    df = write(df, name)
    say(f"  ✓ {name}: PER {out['PER']:.2f} · PBR {out['PBR']:.2f} · 추정PER {out['추정PER']:.2f} · "
        f"배당 {out['배당수익률']:.2f}% · {len(d)}종목 · {len(df)}일치"
        + ("" if "dividendYieldRatio" in seen else f" · (배당 항목 없음: {sorted(seen)[:30]})"))


def main():
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
    try:
        update_sector_flows()
    except Exception as e:
        say(f"  ✗ 분야별 수급 실패: {type(e).__name__}: {str(e)[:160]}")
    for code in ("KOSPI", "KOSDAQ"):
        try:
            update_valuation(code, read(f"index_{code}").index.max())
        except Exception as e:
            say(f"  ✗ {code} PER·PBR 실패: {type(e).__name__}: {str(e)[:160]}")
    (OUT / "probe_naver.html").unlink(missing_ok=True)
    (OUT / "probe.txt").unlink(missing_ok=True)
    (OUT / "status.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    say(f"완료: 시장 {ok}/2")
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
