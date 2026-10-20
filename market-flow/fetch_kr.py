"""한국 시장 데이터를 미리 받아 data/kr/ 에 저장해요.

Streamlit Cloud(해외 서버)에서는 한국거래소 접속이 막힐 때가 많아서,
GitHub Actions가 이 스크립트를 돌려 CSV로 저장해 두고 앱은 그 파일을 읽어요.

1순위: pykrx(한국거래소)  →  실패하면 2순위: 네이버 금융
직접 실행:  cd market-flow && python fetch_kr.py
"""
from __future__ import annotations

import io
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent / "data" / "kr"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Referer": "https://finance.naver.com/"}
INDEX_CODE = {"코스피": "1001", "코스닥": "2001"}
log: list[str] = []


def say(msg: str):
    print(msg, flush=True)
    log.append(msg)


def save(df: pd.DataFrame, name: str, src: str):
    df = df.sort_index()
    df.index.name = "date"
    df.to_csv(OUT / f"{name}.csv")
    say(f"  ✓ {name}: {len(df)}행 ({df.index.min():%Y-%m-%d} ~ {df.index.max():%Y-%m-%d}) · {src}")


def dates(days: int):
    end = date.today()
    return (end - timedelta(days=int(days * 1.6) + 7)).strftime("%Y%m%d"), end.strftime("%Y%m%d")


# ── 투자자별 순매수 ──────────────────────────────────────
def flows_pykrx(market: str, days: int = 750) -> pd.DataFrame:
    from pykrx import stock
    s, e = dates(days)
    df = stock.get_market_trading_value_by_date(s, e, market)
    if df is None or df.empty:
        raise RuntimeError("빈 응답")
    keep = {}
    for want, cands in {"외국인": ["외국인합계", "외국인"], "기관": ["기관합계", "기관"], "개인": ["개인"]}.items():
        for c in cands:
            if c in df.columns:
                keep[want] = df[c]
                break
    out = pd.DataFrame(keep)
    out.index = pd.to_datetime(out.index)
    return out  # 원


def flows_naver(market: str, pages: int = 60) -> pd.DataFrame:
    """네이버 금융 '투자자별 매매동향(일별)'. 단위 억 원 → 원으로 변환."""
    import requests
    sosok = "01" if market == "KOSPI" else "02"
    frames = []
    bizdate = date.today().strftime("%Y%m%d")
    for page in range(1, pages + 1):
        r = requests.get("https://finance.naver.com/sise/investorDealTrendDay.naver",
                         params={"bizdate": bizdate, "sosok": sosok, "page": page}, headers=UA, timeout=15)
        r.encoding = "euc-kr"
        tbls = pd.read_html(io.StringIO(r.text))
        t = next((x for x in tbls if x.shape[1] >= 4), None)
        if t is None:
            break
        t.columns = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in t.columns]
        t = t.dropna(how="all")
        date_col = t.columns[0]
        t = t[t[date_col].astype(str).str.match(r"\d{2}\.\d{2}\.\d{2}")]
        if t.empty:
            break
        frames.append(t)
        time.sleep(0.15)
    if not frames:
        raise RuntimeError("표를 찾지 못함")
    t = pd.concat(frames)
    cols = list(t.columns)

    def pick(word):
        return next(c for c in cols if word in c)
    out = pd.DataFrame({"개인": t[pick("개인")], "외국인": t[pick("외국인")], "기관": t[pick("기관계")]})
    out = out.apply(lambda s: pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce")) * 1e8
    out.index = pd.to_datetime(t[cols[0]].astype(str), format="%y.%m.%d")
    return out[~out.index.duplicated()].dropna(how="all")


# ── 지수 거래대금·PER·VKOSPI·업종·시장 폭 (pykrx) ───────
def index_pykrx(name: str, days: int = 400) -> pd.DataFrame:
    from pykrx import stock
    s, e = dates(days)
    df = stock.get_index_ohlcv(s, e, INDEX_CODE[name])
    df.index = pd.to_datetime(df.index)
    return df[[c for c in ("종가", "거래대금", "거래량") if c in df]]


def fundamental_pykrx(name: str, days: int = 1250) -> pd.DataFrame:
    from pykrx import stock
    s, e = dates(days)
    df = stock.get_index_fundamental(s, e, INDEX_CODE[name])
    df.index = pd.to_datetime(df.index)
    return df[[c for c in ("PER", "PBR", "배당수익률") if c in df]]


def vkospi_pykrx(days: int = 600) -> pd.DataFrame:
    from pykrx import stock
    code = None
    for mkt in ("KRX", "KOSPI", "테마"):
        try:
            for t in stock.get_index_ticker_list(market=mkt):
                if "변동성" in stock.get_index_ticker_name(t):
                    code = t
                    break
        except Exception:
            continue
        if code:
            break
    if not code:
        raise RuntimeError("VKOSPI 코드 없음")
    s, e = dates(days)
    df = stock.get_index_ohlcv(s, e, code)
    df.index = pd.to_datetime(df.index)
    return df[["종가"]].rename(columns={"종가": "VKOSPI"})


def sectors_pykrx() -> pd.DataFrame:
    from pykrx import stock
    rows = {}
    for label, d in (("1주", 7), ("1개월", 31), ("3개월", 92)):
        e = date.today()
        df = stock.get_index_price_change((e - timedelta(days=d)).strftime("%Y%m%d"), e.strftime("%Y%m%d"), "KOSPI")
        df = df.reset_index()
        rows[label] = df.set_index(df.columns[0])["등락률"]
    out = pd.DataFrame(rows)
    out.index.name = "업종"
    return out


def breadth_pykrx(market: str, days: int = 60) -> pd.DataFrame:
    from pykrx import stock
    rows, d, tries = {}, date.today(), 0
    while len(rows) < days and tries < days * 2 + 10:
        tries += 1
        if d.weekday() < 5:
            df = stock.get_market_ohlcv(d.strftime("%Y%m%d"), market=market)
            if df is not None and not df.empty and "등락률" in df and df["거래량"].sum() > 0:
                ch = df["등락률"]
                rows[pd.Timestamp(d)] = {"상승": int((ch > 0).sum()), "하락": int((ch < 0).sum()), "보합": int((ch == 0).sum())}
        d -= timedelta(days=1)
    if not rows:
        raise RuntimeError("데이터 없음")
    return pd.DataFrame(rows).T


def attempt(name: str, fns):
    for src, fn in fns:
        try:
            df = fn()
            if df is None or len(df) == 0:
                raise RuntimeError("빈 결과")
            if name == "sectors":
                df.to_csv(OUT / f"{name}.csv")
                say(f"  ✓ {name}: {len(df)}개 업종 · {src}")
            else:
                save(df, name, src)
            return True
        except Exception as e:
            say(f"  ✗ {name} [{src}] 실패: {type(e).__name__}: {str(e)[:160]}")
    return False


def probe():
    """진단: 후보 주소들의 응답 상태를 기록해요."""
    import re
    import requests
    urls = [
        ("naver_investor_day", "https://finance.naver.com/sise/investorDealTrendDay.naver",
         {"bizdate": date.today().strftime("%Y%m%d"), "sosok": "01", "page": 1}),
        ("naver_m_kospi_trend", "https://m.stock.naver.com/api/index/KOSPI/trend", {}),
        ("naver_m_kospi_basic", "https://m.stock.naver.com/api/index/KOSPI/basic", {}),
        ("naver_m_investor", "https://m.stock.naver.com/api/index/KOSPI/investor", {}),
        ("naver_m_investor_trend", "https://m.stock.naver.com/front-api/marketIndex/investorTrend", {"category": "KOSPI"}),
        ("krx_data", "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd", {}),
    ]
    for name, url, params in urls:
        try:
            r = requests.get(url, params=params, headers=UA, timeout=15)
            body = r.content[:20000]
            try:
                txt = body.decode("euc-kr")
            except Exception:
                txt = body.decode("utf-8", "ignore")
            title = re.search(r"<title>(.*?)</title>", txt, re.S)
            ntab = txt.count("<table")
            say(f"  [probe] {name}: HTTP {r.status_code} · {len(r.content)}B · tables={ntab} · "
                f"title={title.group(1).strip()[:60] if title else '-'} · head={txt[:200].strip()!r}")
            if name == "naver_investor_day":
                (OUT / "probe_naver.html").write_bytes(r.content[:200000])
        except Exception as e:
            say(f"  [probe] {name}: 실패 {type(e).__name__}: {str(e)[:120]}")


def main():
    say(f"한국 데이터 받기 시작 ({date.today()})")
    probe()
    ok = {}
    for mkt in ("KOSPI", "KOSDAQ"):
        ok[f"flows_{mkt}"] = attempt(f"flows_{mkt}", [("한국거래소(pykrx)", lambda m=mkt: flows_pykrx(m)),
                                                       ("네이버 금융", lambda m=mkt: flows_naver(m))])
    for nm, key in (("코스피", "KOSPI"), ("코스닥", "KOSDAQ")):
        ok[f"index_{key}"] = attempt(f"index_{key}", [("한국거래소(pykrx)", lambda n=nm: index_pykrx(n))])
        ok[f"fund_{key}"] = attempt(f"fund_{key}", [("한국거래소(pykrx)", lambda n=nm: fundamental_pykrx(n))])
        ok[f"breadth_{key}"] = attempt(f"breadth_{key}", [("한국거래소(pykrx)", lambda k=key: breadth_pykrx(k, 30))])
    ok["vkospi"] = attempt("vkospi", [("한국거래소(pykrx)", vkospi_pykrx)])
    ok["sectors"] = attempt("sectors", [("한국거래소(pykrx)", sectors_pykrx)])
    (OUT / "status.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    n = sum(ok.values())
    say(f"완료: {n}/{len(ok)}개 성공")
    if n == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
