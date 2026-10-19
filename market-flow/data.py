"""데이터 수집.

- 지수·금리·환율·유가·업종 ETF: yfinance (무료, 회원가입 없음)
- 한국 수급·시장 폭·거래대금·업종·PER·VKOSPI: pykrx (실패해도 앱은 동작)
- 일정·미국 경제 보고서: 저장소의 data/ 폴더 파일
- 인터넷이 안 되거나 MARKET_FLOW_DEMO=1 이면 샘플 데이터로 동작해요.

모든 함수는 (데이터 또는 None, 출처 설명) 을 돌려줘요.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from config import ALL_YF, KRX_INDEX

DATA_DIR = Path(__file__).parent / "data"
SAMPLE = "샘플 데이터 (데모 모드)"


def demo_mode() -> bool:
    return os.environ.get("MARKET_FLOW_DEMO") == "1"


def _bdays(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)


def _krx_dates(days: int) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=int(days * 1.6) + 7)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


# ── 가격 (yfinance) ──────────────────────────────────────
def _synthetic_prices(years: int = 6, seed: int = 7) -> pd.DataFrame:
    """테스트용 가짜 시세. 실제 시장과 무관해요."""
    rng = np.random.default_rng(seed)
    idx = _bdays(252 * years)
    common = rng.normal(0.0003, 0.01, len(idx))
    start = {"^KS11": 2500, "^KQ11": 800, "^GSPC": 4500, "^IXIC": 14000, "^DJI": 35000,
             "^RUT": 2000, "^SOX": 3500, "KRW=X": 1300, "DX-Y.NYB": 102, "CL=F": 75, "GC=F": 1900,
             "^MOVE": 100, "JPY=X": 150, "BTC-USD": 60000, "HG=F": 4}
    beta = {"^SOX": 1.6, "^IXIC": 1.2, "^KQ11": 1.3, "KRW=X": -0.3, "DX-Y.NYB": -0.2, "CL=F": 0.5,
            "GC=F": -0.1, "^MOVE": -0.8, "JPY=X": 0.3, "BTC-USD": 2.0, "HYG": 0.3, "IEF": -0.1, "XLK": 1.3, "XLU": 0.4, "XLP": 0.5, "XLE": 0.8, "RSP": 0.9}
    out = {}
    for t in ALL_YF:
        if t == "^VIX":
            out[t] = np.clip(18 - common.cumsum() * 25 + np.cumsum(rng.normal(0, 0.3, len(idx))) * 0.2, 10, 60)
        elif t in ("^TNX", "^IRX", "^FVX", "^TYX"):
            base = {"^TNX": 4.0, "^IRX": 4.5, "^FVX": 3.9, "^TYX": 4.3}[t]
            out[t] = np.clip(base + np.cumsum(rng.normal(0, 0.03, len(idx))), 0.5, 7)
        else:
            r = beta.get(t, 1.0) * common + rng.normal(0, 0.007, len(idx))
            out[t] = start.get(t, 100) * np.exp(np.cumsum(r))
    df = pd.DataFrame(out, index=idx)
    return df


def _synthetic_volume(prices: pd.DataFrame, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = {}
    for t, base in {"^KS11": 5e8, "^GSPC": 4e9}.items():
        out[t] = base * np.exp(rng.normal(0, 0.25, len(prices)))
    return pd.DataFrame(out, index=prices.index)


def load_prices(period: str = "6y") -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """(종가 표, 거래량 표, 출처 설명). 열 = 티커."""
    if demo_mode():
        p = _synthetic_prices()
        return p, _synthetic_volume(p), SAMPLE
    try:
        import yfinance as yf

        raw = yf.download(ALL_YF, period=period, interval="1d",
                          auto_adjust=False, progress=False, threads=True)
        if raw is None or raw.empty:
            raise RuntimeError("빈 응답")
        close = raw["Close"].copy()
        vol = raw["Volume"].copy() if "Volume" in raw.columns.get_level_values(0) else pd.DataFrame(index=close.index)
        for df in (close, vol):
            df.index = pd.to_datetime(df.index).tz_localize(None)
        close = close.dropna(how="all")
        # 비트코인처럼 주말에도 거래되는 자산 때문에 생긴 토·일요일 행은 빼요.
        close = close[close.index.dayofweek < 5].ffill()
        vol = vol.reindex(close.index)
        # 예전 야후 데이터는 금리를 10배(예: 45.0 = 4.5%)로 주기도 해서 보정해요.
        for t in ("^TNX", "^IRX", "^FVX", "^TYX"):
            if t in close and close[t].median() > 20:
                close[t] = close[t] / 10
        missing = [t for t in ALL_YF if t not in close.columns or close[t].dropna().empty]
        note = "야후 파이낸스 (yfinance)"
        if missing:
            note += f" · 불러오지 못한 지표: {', '.join(missing)}"
        return close, vol, note
    except Exception as e:  # 네트워크 문제 등
        p = _synthetic_prices()
        return p, _synthetic_volume(p), f"실제 데이터를 불러오지 못해 샘플 데이터를 표시해요 ({e})"


# ── 한국: 투자자별 순매수 ────────────────────────────────
def load_investor_flows(market: str = "KOSPI", days: int = 60):
    """투자자별 순매수 금액(원). 열: 외국인, 기관, 개인."""
    if demo_mode():
        rng = np.random.default_rng(3 if market == "KOSPI" else 4)
        f, i = rng.normal(-2e11, 6e11, days), rng.normal(5e10, 4e11, days)
        return pd.DataFrame({"외국인": f, "기관": i, "개인": -(f + i)}, index=_bdays(days)), SAMPLE
    try:
        from pykrx import stock

        s, e = _krx_dates(days)
        df = stock.get_market_trading_value_by_date(s, e, market)
        keep = {}
        for want, cands in {"외국인": ["외국인합계", "외국인"], "기관": ["기관합계", "기관"], "개인": ["개인"]}.items():
            for c in cands:
                if c in df.columns:
                    keep[want] = df[c]
                    break
        if not keep:
            raise RuntimeError("열 이름을 찾지 못함")
        out = pd.DataFrame(keep).tail(days)
        out.index = pd.to_datetime(out.index)
        return out, "한국거래소 (pykrx)"
    except Exception as e:
        return None, f"투자자별 수급을 불러오지 못했어요 ({e})"


# ── 한국: 시장의 폭 (상승·하락 종목 수) ──────────────────
def load_kr_breadth(market: str = "KOSPI", days: int = 20):
    """날짜별 상승·하락·보합 종목 수. 하루씩 조회해서 시간이 조금 걸려요."""
    if demo_mode():
        rng = np.random.default_rng(5)
        up = rng.integers(200, 700, days)
        down = 900 - up - rng.integers(20, 60, days)
        return pd.DataFrame({"상승": up, "하락": down, "보합": 900 - up - down}, index=_bdays(days)), SAMPLE
    try:
        from pykrx import stock

        rows = {}
        d = date.today()
        tries = 0
        while len(rows) < days and tries < days * 2 + 10:
            tries += 1
            if d.weekday() < 5:
                df = stock.get_market_ohlcv(d.strftime("%Y%m%d"), market=market)
                if df is not None and not df.empty and "등락률" in df and df["거래량"].sum() > 0:
                    ch = df["등락률"]
                    rows[pd.Timestamp(d)] = {"상승": int((ch > 0).sum()), "하락": int((ch < 0).sum()),
                                             "보합": int((ch == 0).sum())}
            d -= timedelta(days=1)
        if not rows:
            raise RuntimeError("데이터 없음")
        return pd.DataFrame(rows).T.sort_index(), "한국거래소 (pykrx)"
    except Exception as e:
        return None, f"상승·하락 종목 수를 불러오지 못했어요 ({e})"


# ── 한국: 지수 OHLCV (거래대금) ──────────────────────────
def load_kr_index(name: str = "코스피", days: int = 250):
    """한국 지수의 종가·거래대금(원)."""
    if demo_mode():
        rng = np.random.default_rng(6)
        idx = _bdays(days)
        close = 2500 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, days)))
        val = 1.2e13 * np.exp(rng.normal(0, 0.25, days))
        return pd.DataFrame({"종가": close, "거래대금": val}, index=idx), SAMPLE
    try:
        from pykrx import stock

        s, e = _krx_dates(days)
        df = stock.get_index_ohlcv(s, e, KRX_INDEX[name])
        df.index = pd.to_datetime(df.index)
        cols = [c for c in ("종가", "거래대금", "거래량") if c in df]
        return df[cols].tail(days), "한국거래소 (pykrx)"
    except Exception as e:
        return None, f"{name} 거래대금을 불러오지 못했어요 ({e})"


# ── 한국: 업종별 등락 ────────────────────────────────────
def load_kr_sectors(days: int = 20):
    """코스피 업종지수의 기간 등락률(%)."""
    if demo_mode():
        rng = np.random.default_rng(8)
        names = ["전기전자", "운수장비", "화학", "금융업", "의약품", "철강금속", "건설업", "유통업", "통신업", "음식료품", "기계", "보험"]
        return pd.DataFrame({"업종": names, "등락률": rng.normal(0, 4, len(names))}), SAMPLE
    try:
        from pykrx import stock

        s, e = _krx_dates(days)
        df = stock.get_index_price_change(s, e, "KOSPI")
        df = df.reset_index()
        name_col = df.columns[0]
        out = df[[name_col, "등락률"]].rename(columns={name_col: "업종"})
        drop = ("코스피", "코스피 200", "코스피 100", "코스피 50", "코스피 대형주", "코스피 중형주", "코스피 소형주")
        out = out[~out["업종"].isin(drop)]
        return out, "한국거래소 (pykrx)"
    except Exception as e:
        return None, f"한국 업종 등락을 불러오지 못했어요 ({e})"


# ── 한국: PER·PBR ────────────────────────────────────────
def load_kr_fundamental(name: str = "코스피", days: int = 1250):
    """지수 PER·PBR·배당수익률."""
    if demo_mode():
        rng = np.random.default_rng(9)
        idx = _bdays(days)
        per = np.clip(12 + np.cumsum(rng.normal(0, 0.08, days)), 7, 25)
        pbr = per / 12
        return pd.DataFrame({"PER": per, "PBR": pbr, "배당수익률": 2 + rng.normal(0, 0.1, days)}, index=idx), SAMPLE
    try:
        from pykrx import stock

        s, e = _krx_dates(days)
        df = stock.get_index_fundamental(s, e, KRX_INDEX[name])
        df.index = pd.to_datetime(df.index)
        cols = [c for c in ("PER", "PBR", "배당수익률") if c in df]
        df = df[cols].replace(0, np.nan).dropna(how="all")
        return df, "한국거래소 (pykrx)"
    except Exception as e:
        return None, f"{name} PER·PBR을 불러오지 못했어요 ({e})"


# ── 한국: VKOSPI ─────────────────────────────────────────
def load_vkospi(days: int = 500):
    """코스피200 변동성지수(VKOSPI). 찾지 못하면 None."""
    if demo_mode():
        rng = np.random.default_rng(10)
        return pd.Series(np.clip(20 + np.cumsum(rng.normal(0, 0.6, days)) * 0.3, 10, 60), index=_bdays(days), name="VKOSPI"), SAMPLE
    try:
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
            raise RuntimeError("VKOSPI 지수 코드를 찾지 못함")
        s, e = _krx_dates(days)
        df = stock.get_index_ohlcv(s, e, code)
        ser = df["종가"].astype(float)
        ser.index = pd.to_datetime(ser.index)
        return ser.rename("VKOSPI"), "한국거래소 (pykrx)"
    except Exception as e:
        return None, f"VKOSPI를 불러오지 못했어요 ({e})"


# ── 저장소 data/ 폴더 파일 ───────────────────────────────
def load_events() -> tuple[pd.DataFrame | None, str]:
    """data/events.csv (열: date, when, title, category, importance, note)."""
    f = DATA_DIR / "events.csv"
    if not f.exists():
        return None, "data/events.csv 파일이 없어요"
    df = pd.read_csv(f, parse_dates=["date"]).sort_values("date")
    return df, "공개 일정 보도를 정리한 파일 (data/events.csv)"


def load_world_brief() -> tuple[list | None, str]:
    """data/world_brief.json — 지역별 세계 동향 한국어 브리핑."""
    f = DATA_DIR / "world_brief.json"
    if not f.exists():
        return None, "data/world_brief.json 파일이 없어요"
    return json.loads(f.read_text(encoding="utf-8")), "뉴스·공식 발표를 조사해 정리한 브리핑 (data/world_brief.json)"


def load_us_reports() -> tuple[list | None, str]:
    """data/us_reports.json — 미국 경제 보고서 한국어 요약."""
    f = DATA_DIR / "us_reports.json"
    if not f.exists():
        return None, "data/us_reports.json 파일이 없어요"
    return json.loads(f.read_text(encoding="utf-8")), "BLS·연준·BEA 등 공식 보고서 요약 (data/us_reports.json)"


# ── 미국 물가: FRED (세인트루이스 연은 공개 통계, 키 없이 CSV로 받기) ─────
def _synthetic_fred() -> dict[str, pd.Series]:
    rng = np.random.default_rng(21)
    m = pd.date_range("2012-01-01", pd.Timestamp.today().normalize() - pd.offsets.MonthBegin(1), freq="MS")
    oil_m = 70 * np.exp(np.cumsum(rng.normal(0, 0.06, len(m))))
    oil_ch = np.r_[0, np.diff(np.log(oil_m))]
    core_mm = 0.0025 + 0.0006 * np.sin(np.arange(len(m)) / 9) + rng.normal(0, 0.0012, len(m))
    head_mm = core_mm + 0.05 * oil_ch + rng.normal(0, 0.0015, len(m))
    d = pd.bdate_range(m[0], pd.Timestamp.today().normalize())
    oil_d = pd.Series(oil_m, index=m).reindex(d, method="ffill") * np.exp(rng.normal(0, 0.01, len(d)))
    be = 2.3 + pd.Series(np.cumsum(rng.normal(0, 0.01, len(d))), index=d) * 0.3
    return {
        "CPIAUCSL": pd.Series(250 * np.exp(np.cumsum(head_mm)), index=m),
        "CPILFESL": pd.Series(255 * np.exp(np.cumsum(core_mm)), index=m),
        "PCEPILFE": pd.Series(110 * np.exp(np.cumsum(core_mm * 0.85)), index=m),
        "T10YIE": be, "T5YIE": be + 0.1,
        "MICH": pd.Series(3 + rng.normal(0, 0.3, len(m)), index=m),
        "DCOILWTICO": oil_d,
    }


def load_fred(series: list[str]) -> tuple[dict[str, pd.Series], str]:
    """FRED 시계열 여러 개. 실패한 것은 빠져요. (값, 출처 설명)"""
    if demo_mode():
        syn = _synthetic_fred()
        return {k: syn[k] for k in series if k in syn}, SAMPLE
    out, failed = {}, []
    try:
        import io
        import requests

        for sid in series:
            try:
                r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": sid},
                                 headers={"User-Agent": "Mozilla/5.0 market-flow"}, timeout=20)
                r.raise_for_status()
                df = pd.read_csv(io.StringIO(r.text))
                date_col = df.columns[0]
                s = pd.to_numeric(df[sid], errors="coerce")
                s.index = pd.to_datetime(df[date_col])
                out[sid] = s.dropna()
            except Exception:
                failed.append(sid)
    except Exception as e:
        failed = series
        note = f"FRED 접속 실패 ({e})"
    if not out:
        syn = _synthetic_fred()
        return {k: syn[k] for k in series if k in syn}, "FRED에 접속하지 못해 샘플 데이터를 표시해요"
    note = "미국 노동통계국·경제분석국 통계 (FRED, 세인트루이스 연은)"
    if failed:
        note += f" · 불러오지 못한 항목: {', '.join(failed)}"
    return out, note
