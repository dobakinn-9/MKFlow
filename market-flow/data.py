"""데이터 수집.

- 지수·환율·금리·유가: yfinance (무료, 회원가입 없음)
- 한국 투자자별 순매수: pykrx (선택. 실패해도 앱은 동작)
- 인터넷이 안 되거나 MARKET_FLOW_DEMO=1 이면 샘플 데이터로 동작해요.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import numpy as np
import pandas as pd

from config import TICKERS


def demo_mode() -> bool:
    return os.environ.get("MARKET_FLOW_DEMO") == "1"


def _synthetic_prices(years: int = 6, seed: int = 7) -> pd.DataFrame:
    """테스트용 가짜 시세. 실제 시장과 무관해요."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=252 * years)
    start = {"^KS11": 2500, "^KQ11": 800, "^GSPC": 4500, "^IXIC": 14000, "^DJI": 35000,
             "^RUT": 2000, "^SOX": 3500, "^VIX": 18, "^TNX": 4.0, "KRW=X": 1300,
             "DX-Y.NYB": 102, "CL=F": 75}
    common = rng.normal(0.0003, 0.01, len(idx))
    out = {}
    for t, s0 in start.items():
        if t in ("^VIX",):
            x = 18 + np.cumsum(rng.normal(0, 0.6, len(idx)))
            out[t] = np.clip(18 + (x - 18) * 0.15 - common.cumsum() * 30, 10, 60)
        elif t in ("^TNX",):
            out[t] = np.clip(s0 + np.cumsum(rng.normal(0, 0.03, len(idx))), 1, 7)
        else:
            beta = {"^SOX": 1.6, "^IXIC": 1.2, "^KQ11": 1.3, "KRW=X": -0.3, "DX-Y.NYB": -0.2, "CL=F": 0.5}.get(t, 1.0)
            r = beta * common + rng.normal(0, 0.007, len(idx))
            out[t] = s0 * np.exp(np.cumsum(r))
    return pd.DataFrame(out, index=idx)


def load_prices(period: str = "6y") -> tuple[pd.DataFrame, str]:
    """종가 표(열=티커)와 데이터 출처 설명을 돌려줘요."""
    if demo_mode():
        return _synthetic_prices(), "샘플 데이터 (데모 모드)"
    try:
        import yfinance as yf

        raw = yf.download(list(TICKERS), period=period, interval="1d",
                          auto_adjust=False, progress=False, threads=True)
        if raw is None or raw.empty:
            raise RuntimeError("빈 응답")
        close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        close = close.dropna(how="all")
        close.index = pd.to_datetime(close.index).tz_localize(None)
        # 한국·미국 휴장일이 달라서 생기는 빈칸은 직전 값으로 채워요.
        close = close.ffill()
        # 예전 야후 데이터는 10년물 금리를 10배(예: 45.0 = 4.5%)로 주기도 해서 보정해요.
        if "^TNX" in close and close["^TNX"].median() > 20:
            close["^TNX"] = close["^TNX"] / 10
        missing = [t for t in TICKERS if t not in close.columns or close[t].dropna().empty]
        note = "야후 파이낸스 (yfinance)"
        if missing:
            note += f" · 불러오지 못한 지표: {', '.join(missing)}"
        return close, note
    except Exception as e:  # 네트워크 문제 등
        return _synthetic_prices(), f"실제 데이터를 불러오지 못해 샘플 데이터를 표시해요 ({e})"


def load_investor_flows(days: int = 60) -> tuple[pd.DataFrame | None, str]:
    """코스피 투자자별 순매수 금액(원). pykrx가 없거나 실패하면 None."""
    if demo_mode():
        idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
        rng = np.random.default_rng(3)
        f = rng.normal(-2e11, 6e11, days)
        i = rng.normal(5e10, 4e11, days)
        return pd.DataFrame({"외국인": f, "기관": i, "개인": -(f + i)}, index=idx), "샘플 데이터 (데모 모드)"
    try:
        from pykrx import stock

        end = date.today()
        start = end - timedelta(days=int(days * 1.6))
        df = stock.get_market_trading_value_by_date(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), "KOSPI")
        cols = {c: c for c in df.columns}
        keep = {}
        for want, cands in {"외국인": ["외국인합계", "외국인"], "기관": ["기관합계", "기관"], "개인": ["개인"]}.items():
            for c in cands:
                if c in cols:
                    keep[want] = df[c]
                    break
        if not keep:
            raise RuntimeError("열 이름을 찾지 못함")
        out = pd.DataFrame(keep).tail(days)
        out.index = pd.to_datetime(out.index)
        return out, "한국거래소 (pykrx)"
    except Exception as e:
        return None, f"투자자별 수급을 불러오지 못했어요 ({e})"
