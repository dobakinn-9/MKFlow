"""시장 흐름 분석.

핵심 아이디어
1) 여러 요인(추세·모멘텀·변동성·금리·유가·환율·반도체)을 매일 +/− 신호로 바꿔 합산 → '흐름 점수'(−10~+10)
2) 과거에 지금과 비슷한 점수였던 날들을 모아, 그 뒤 N거래일 수익률이 어땠는지 통계로 보여줌 → '전망'

전망은 과거 통계일 뿐 미래를 보장하지 않아요.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from config import name

RATE_TICKERS = {"^TNX"}  # 퍼센트 단위라 등락을 %p로 표시


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def change_table(prices: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """최신값과 1일·1주·1개월·3개월 변화."""
    rows = []
    for t in tickers:
        if t not in prices or prices[t].dropna().empty:
            continue
        s = prices[t].dropna()
        last = s.iloc[-1]
        row = {"티커": t, "지표": name(t), "현재": last, "기준일": s.index[-1].date()}
        for label, n in [("1일", 1), ("1주", 5), ("1개월", 21), ("3개월", 63)]:
            if len(s) > n:
                prev = s.iloc[-1 - n]
                row[label] = (last - prev) if t in RATE_TICKERS else (last / prev - 1) * 100
            else:
                row[label] = np.nan
        row["단위"] = "%p" if t in RATE_TICKERS else "%"
        rows.append(row)
    return pd.DataFrame(rows)


@dataclass
class Factor:
    key: str
    label: str
    weight: float
    series: pd.Series  # 날짜별 신호(−1~+1)
    explain: callable  # 최신 날짜 기준 설명 문장


def _pct(s: pd.Series, n: int) -> pd.Series:
    return s / s.shift(n) - 1


def build_factors(prices: pd.DataFrame, target: str) -> list[Factor]:
    p = prices[target]
    ma20, ma60 = p.rolling(20).mean(), p.rolling(60).mean()
    r = rsi(p)
    ret20 = _pct(p, 20)
    fx = []

    trend = np.sign(p - ma60)
    fx.append(Factor("trend", "추세 (60일선 위/아래)", 2, trend,
                     lambda i: f"{name(target)} 종가가 60일 평균선 {'위' if trend.iloc[i] > 0 else '아래'}에 있어요 "
                               f"(현재 {p.iloc[i]:,.0f} / 60일선 {ma60.iloc[i]:,.0f})."))

    cross = np.sign(ma20 - ma60)
    fx.append(Factor("cross", "단기 vs 중기 평균선", 1, cross,
                     lambda i: f"20일선이 60일선 {'위(상승 배열)' if cross.iloc[i] > 0 else '아래(하락 배열)'}예요."))

    mom = np.sign(ret20)
    fx.append(Factor("mom", "한 달 모멘텀", 1, mom,
                     lambda i: f"최근 20거래일 수익률 {ret20.iloc[i] * 100:+.1f}%."))

    rsi_sig = pd.Series(np.select([r < 30, r > 70], [1, -1], 0), index=p.index, dtype=float)
    fx.append(Factor("rsi", "과열/과매도 (RSI)", 1, rsi_sig,
                     lambda i: f"RSI {r.iloc[i]:.0f} → "
                               + ("과매도 구간이라 반등 여지가 있어요." if r.iloc[i] < 30
                                  else "과열 구간이라 숨 고르기 가능성이 있어요." if r.iloc[i] > 70
                                  else "중립 구간이에요.")))

    if "^VIX" in prices:
        v = prices["^VIX"]
        vix_sig = pd.Series(np.select([v > 30, v > 22, v < 15], [-1, -0.5, 1], 0), index=p.index, dtype=float)
        fx.append(Factor("vix", "공포 지수 (VIX)", 1.5, vix_sig,
                         lambda i: f"VIX {v.iloc[i]:.1f} → "
                                   + ("공포 국면이에요." if v.iloc[i] > 30 else "불안이 커지는 국면이에요." if v.iloc[i] > 22
                                      else "낙관 국면이에요." if v.iloc[i] < 15 else "보통 수준이에요.")))

    if "^TNX" in prices:
        y = prices["^TNX"]
        dy = y - y.shift(20)
        rate_sig = pd.Series(np.select([dy > 0.25, dy < -0.25], [-1, 1], 0), index=p.index, dtype=float)
        fx.append(Factor("rate", "미국 금리 방향", 1.5, rate_sig,
                         lambda i: f"미 10년물 금리 {y.iloc[i]:.2f}%, 한 달 새 {dy.iloc[i]:+.2f}%p "
                                   + ("급등 → 주식에 부담." if dy.iloc[i] > 0.25 else "하락 → 주식에 우호적." if dy.iloc[i] < -0.25 else "큰 변화 없음.")))

    if "CL=F" in prices:
        o = prices["CL=F"]
        do = _pct(o, 20)
        oil_sig = pd.Series(np.select([do > 0.10, do < -0.10], [-1, 1], 0), index=p.index, dtype=float)
        fx.append(Factor("oil", "유가 (인플레 압력)", 1, oil_sig,
                         lambda i: f"WTI ${o.iloc[i]:.1f}, 한 달 새 {do.iloc[i] * 100:+.1f}% "
                                   + ("급등 → 물가·금리 부담." if do.iloc[i] > 0.10 else "급락 → 물가 부담 완화." if do.iloc[i] < -0.10 else "안정적.")))

    fx_t = "KRW=X" if target in ("^KS11", "^KQ11") else "DX-Y.NYB"
    if fx_t in prices:
        f = prices[fx_t]
        df_ = _pct(f, 20)
        th = 0.02
        fx_sig = pd.Series(np.select([df_ > th, df_ < -th], [-1, 1], 0), index=p.index, dtype=float)
        lbl = "원/달러 환율" if fx_t == "KRW=X" else "달러 강세"
        fx.append(Factor("fx", lbl, 1, fx_sig,
                         lambda i: f"{name(fx_t)} 한 달 새 {df_.iloc[i] * 100:+.1f}% "
                                   + ("→ 달러 강세, 외국인 자금 이탈 압력." if df_.iloc[i] > th
                                      else "→ 달러 약세, 위험자산에 우호적." if df_.iloc[i] < -th else "→ 큰 변화 없음.")))

    if "^SOX" in prices and target != "^SOX":
        sx = prices["^SOX"]
        sx60 = sx.rolling(60).mean()
        sox_sig = np.sign(sx - sx60)
        w = 2 if target in ("^KS11", "^KQ11") else 1
        fx.append(Factor("sox", "반도체 업황 (SOX)", w, sox_sig,
                         lambda i: f"미국 반도체 지수가 60일선 {'위' if sox_sig.iloc[i] > 0 else '아래'} "
                                   f"({_pct(sx, 20).iloc[i] * 100:+.1f}% / 1개월)."))
    return fx


def flow_score(factors: list[Factor]) -> pd.Series:
    """요인 신호 × 가중치 합을 −10~+10으로 맞춘 점수."""
    total = sum(f.series.fillna(0) * f.weight for f in factors)
    max_abs = sum(f.weight for f in factors)
    return (total / max_abs * 10).round(1)


def regime(score: float) -> str:
    if score <= -6:
        return "강한 약세"
    if score <= -2:
        return "약세·경계"
    if score < 2:
        return "중립·방향 탐색"
    if score < 6:
        return "완만한 강세"
    return "강한 강세"


def outlook(price: pd.Series, score: pd.Series, fwd: int, band: float = 2.0) -> dict:
    """지금 점수와 비슷했던 과거 날들의 'fwd 거래일 뒤 수익률' 통계."""
    fwd_ret = (price.shift(-fwd) / price - 1) * 100
    hist = pd.DataFrame({"score": score, "fwd": fwd_ret}).dropna()
    hist = hist.iloc[60:]  # 이동평균이 안정되기 전 구간 제외
    now = score.dropna().iloc[-1]
    sim = hist[(hist["score"] - now).abs() <= band]["fwd"]
    base = hist["fwd"]

    def stats(x: pd.Series) -> dict:
        if x.empty:
            return {"n": 0}
        return {"n": int(len(x)), "mean": x.mean(), "median": x.median(), "up": (x > 0).mean() * 100,
                "p10": x.quantile(0.10), "p90": x.quantile(0.90)}

    return {"now": now, "similar": stats(sim), "base": stats(base), "dist": sim}


def score_buckets(price: pd.Series, score: pd.Series, fwd: int) -> pd.DataFrame:
    """점수 구간별 평균 이후 수익률 — 점수가 실제로 의미가 있었는지 확인용."""
    fwd_ret = (price.shift(-fwd) / price - 1) * 100
    d = pd.DataFrame({"score": score, "fwd": fwd_ret}).dropna().iloc[60:]
    bins = [-10.01, -6, -2, 2, 6, 10.01]
    labels = ["강한 약세", "약세·경계", "중립", "완만한 강세", "강한 강세"]
    d["구간"] = pd.cut(d["score"], bins=bins, labels=labels)
    g = d.groupby("구간", observed=False)["fwd"]
    return pd.DataFrame({"일수": g.size(), "평균 수익률(%)": g.mean(), "상승 확률(%)": g.apply(lambda x: (x > 0).mean() * 100 if len(x) else np.nan)}).reset_index()


def rolling_corr(prices: pd.DataFrame, base: str, others: list[str], window: int = 60) -> pd.DataFrame:
    ret = prices.pct_change()
    out = {}
    for t in others:
        if t in ret and t != base:
            out[name(t)] = ret[base].rolling(window).corr(ret[t])
    return pd.DataFrame(out).dropna(how="all")


def realized_vol(s: pd.Series, window: int = 20) -> pd.Series:
    """최근 window일 일간 수익률의 연율화 표준편차(%). VIX·VKOSPI가 없을 때 대체 지표."""
    return s.pct_change().rolling(window).std() * np.sqrt(252) * 100


def period_returns(prices: pd.DataFrame, tickers: list[str], periods: dict[str, int]) -> pd.DataFrame:
    """티커별 여러 기간 수익률(%)."""
    rows = []
    for t in tickers:
        if t not in prices or prices[t].dropna().empty:
            continue
        s = prices[t].dropna()
        row = {"티커": t, "이름": name(t)}
        for label, n in periods.items():
            row[label] = (s.iloc[-1] / s.iloc[-1 - n] - 1) * 100 if len(s) > n else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def share_above_ma(prices: pd.DataFrame, tickers: list[str], window: int = 50) -> pd.Series:
    """여러 티커 중 window일 이동평균 위에 있는 비율(%) — 시장의 폭 지표."""
    sub = prices[[t for t in tickers if t in prices]].dropna(how="all")
    above = sub > sub.rolling(window).mean()
    valid = sub.rolling(window).mean().notna()
    return (above & valid).sum(axis=1) / valid.sum(axis=1).replace(0, np.nan) * 100


def ratio(a: pd.Series, b: pd.Series) -> pd.Series:
    """두 가격의 비율을 시작점=100으로 맞춘 값. 오르면 a가 b보다 강하다는 뜻."""
    r = (a / b).dropna()
    return r / r.iloc[0] * 100 if not r.empty else r


def ad_line(breadth: pd.DataFrame) -> pd.Series:
    """상승-하락 종목 수 누적선(ADL)."""
    return (breadth["상승"] - breadth["하락"]).cumsum()


def percentile_rank(s: pd.Series) -> float:
    """현재 값이 과거 분포에서 몇 % 위치인지(0~100)."""
    s = s.dropna()
    if s.empty:
        return np.nan
    return float((s < s.iloc[-1]).mean() * 100)


# ── 공포·탐욕 지수 ───────────────────────────────────────
def rolling_pct(s: pd.Series, window: int = 252) -> pd.Series:
    """각 날짜의 값이 직전 window일 중 몇 % 위치였는지(0~100). 1년 기준 '상대적 높이'."""
    return s.rolling(window, min_periods=window // 2).apply(lambda x: (x[:-1] < x[-1]).mean() * 100, raw=True)


def fear_greed(prices: pd.DataFrame, market: str) -> pd.DataFrame:
    """시장별 공포·탐욕 구성요소(각 0~100)와 종합 지수.

    0에 가까울수록 공포, 100에 가까울수록 탐욕. 구성요소는 각자의 1년 분포 안에서 위치로 환산해요.
    market: "US" 또는 "KR"
    """
    comp: dict[str, pd.Series] = {}

    def has(*ts):
        return all(t in prices and prices[t].notna().mean() > 0.5 for t in ts)

    if market == "US":
        if has("^GSPC"):
            sp = prices["^GSPC"]
            comp["주가 모멘텀 (125일선 대비)"] = rolling_pct(sp / sp.rolling(125).mean())
        if has("^VIX"):
            v = prices["^VIX"]
            comp["변동성 (VIX, 낮을수록 탐욕)"] = 100 - rolling_pct(v / v.rolling(50).mean())
        if has("HYG", "IEF"):
            comp["정크본드 수요 (하이일드÷국채)"] = rolling_pct((prices["HYG"] / prices["IEF"]).pct_change(20))
        if has("SPY", "IEF"):
            comp["안전자산 회피 (주식−국채 수익률)"] = rolling_pct(prices["SPY"].pct_change(20) - prices["IEF"].pct_change(20))
        if has("RSP", "SPY"):
            comp["시장의 폭 (동일가중÷시총가중)"] = rolling_pct((prices["RSP"] / prices["SPY"]).pct_change(20))
        sectors = [t for t in ("XLK", "XLC", "XLY", "XLF", "XLI", "XLE", "XLB", "XLV", "XLP", "XLU", "XLRE") if t in prices]
        if len(sectors) >= 5:
            comp["주가 강도 (업종 50일선 위 비율)"] = share_above_ma(prices, sectors, 50)
    else:
        if has("^KS11"):
            k = prices["^KS11"]
            comp["주가 모멘텀 (125일선 대비)"] = rolling_pct(k / k.rolling(125).mean())
            comp["변동성 (실제 변동성, 낮을수록 탐욕)"] = 100 - rolling_pct(realized_vol(k))
            comp["과열 (RSI)"] = rsi(k)
        if has("KRW=X"):
            comp["환율 (원화 강세일수록 탐욕)"] = 100 - rolling_pct(prices["KRW=X"].pct_change(20))
        if has("EEM", "SPY"):
            comp["신흥국 자금 (신흥국÷미국)"] = rolling_pct((prices["EEM"] / prices["SPY"]).pct_change(20))
        if has("^SOX"):
            sx = prices["^SOX"]
            comp["반도체 심리 (SOX 125일선 대비)"] = rolling_pct(sx / sx.rolling(125).mean())

    df = pd.DataFrame(comp)
    if df.empty:
        return df
    df["종합"] = df.mean(axis=1, skipna=True)
    return df.dropna(subset=["종합"])


def fg_label(v: float) -> str:
    if v < 25:
        return "극단적 공포"
    if v < 45:
        return "공포"
    if v <= 55:
        return "중립"
    if v <= 75:
        return "탐욕"
    return "극단적 탐욕"


def fg_buckets(price: pd.Series, fg: pd.Series, fwd: int) -> pd.DataFrame:
    """공포·탐욕 구간별 이후 fwd거래일 평균 수익률 — '공포에 사라'가 실제로 통했는지."""
    fr = (price.shift(-fwd) / price - 1) * 100
    d = pd.DataFrame({"fg": fg, "fwd": fr}).dropna()
    labels = ["극단적 공포", "공포", "중립", "탐욕", "극단적 탐욕"]
    d["구간"] = pd.cut(d["fg"], bins=[-0.01, 25, 45, 55, 75, 100.01], labels=labels)
    g = d.groupby("구간", observed=False)["fwd"]
    return pd.DataFrame({"일수": g.size(), "평균 수익률(%)": g.mean(),
                         "상승 확률(%)": g.apply(lambda x: (x > 0).mean() * 100 if len(x) else np.nan)}).reset_index()


def stretch_table(prices: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """과열 판단표: 이격도, 52주 고점·저점 대비, 연속 상승·하락일, RSI."""
    rows = []
    for t in tickers:
        if t not in prices or prices[t].dropna().empty:
            continue
        s = prices[t].dropna()
        last = s.iloc[-1]
        y = s.tail(252)
        ch = np.sign(s.diff()).dropna()
        streak = 0
        if len(ch):
            lastsign = ch.iloc[-1]
            for v in reversed(ch.tolist()):
                if v == lastsign and v != 0:
                    streak += 1
                else:
                    break
            streak *= int(lastsign)
        rows.append({
            "지표": name(t),
            "이격도 20일": last / s.rolling(20).mean().iloc[-1] * 100,
            "이격도 60일": last / s.rolling(60).mean().iloc[-1] * 100,
            "52주 고점 대비(%)": (last / y.max() - 1) * 100,
            "52주 저점 대비(%)": (last / y.min() - 1) * 100,
            "연속(일)": streak,
            "RSI": rsi(s).iloc[-1],
        })
    return pd.DataFrame(rows)


def price_position(prices: pd.DataFrame, tickers: list[str], years: int = 5) -> pd.DataFrame:
    """PER을 못 구할 때 쓰는 대체 지표: 5년 가격 범위 중 위치, 200일선 대비 거리."""
    rows = []
    for t in tickers:
        if t not in prices or prices[t].dropna().empty:
            continue
        s = prices[t].dropna().tail(252 * years)
        ma200 = s.rolling(200).mean().iloc[-1]
        rows.append({"지표": name(t),
                     "5년 범위 중 위치(%)": (s.iloc[-1] - s.min()) / (s.max() - s.min()) * 100 if s.max() > s.min() else np.nan,
                     "200일선 대비(%)": (s.iloc[-1] / ma200 - 1) * 100 if pd.notna(ma200) else np.nan})
    return pd.DataFrame(rows)
