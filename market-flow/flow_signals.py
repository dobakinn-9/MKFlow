"""수급 타이밍 신호.

외국인·기관·개인 순매수 흐름에서 '흐름이 바뀌는 순간'을 찾아 신호로 만들고,
과거에 같은 신호가 나온 뒤 지수가 실제로 어떻게 움직였는지 검증해요.

※ 과거 통계를 보여주는 참고 자료이며 매매 권유가 아니에요.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 신호 정의: (키, 이름, 종류, 설명)
SIGNALS = [
    ("foreign_turn", "외국인 매수 전환", "매수",
     "최근 20일은 순매도였는데 최근 5일 합계가 순매수로 돌아선 첫날. 외국인이 다시 사기 시작했다는 신호예요."),
    ("joint_buy", "외국인·기관 동반 매수", "매수",
     "외국인과 기관이 3일 연속 함께 순매수. 큰손 두 주체가 같은 방향이면 힘이 실려요."),
    ("bottom_div", "바닥 다이버전스", "매수",
     "지수는 20일간 3% 넘게 빠졌는데 외국인은 그동안 순매수. 가격은 약한데 큰손은 모으는 중이에요."),
    ("foreign_dump", "외국인 연속 매도", "주의",
     "외국인이 5일 연속 순매도하면서 지수도 하락. 매도 압력이 이어지는 구간이에요."),
    ("retail_alone", "개인 홀로 매수", "주의",
     "외국인·기관 모두 팔고 개인만 3일 연속 받아내는 장. 하락이 길어지는 경우가 많아요."),
    ("top_div", "고점 다이버전스", "주의",
     "지수는 20일간 3% 넘게 올랐는데 외국인은 그동안 순매도. 가격만 오르고 큰손은 빠지는 중이에요."),
]
SIG_INFO = {k: {"name": n, "kind": t, "desc": d} for k, n, t, d in SIGNALS}


def _run_len(cond: pd.Series) -> pd.Series:
    """조건이 며칠째 연속으로 참인지."""
    grp = (~cond).cumsum()
    return cond.astype(int).groupby(grp).cumsum()


def compute(flows: pd.DataFrame, price: pd.Series) -> pd.DataFrame:
    """날짜별 수급 지표와 신호(True/False). flows 단위는 원."""
    f = (flows / 1e8).copy()  # 억 원
    px = price.reindex(f.index).ffill()
    out = pd.DataFrame(index=f.index)
    out["price"] = px
    fo = f.get("외국인", pd.Series(0, index=f.index))
    ins = f.get("기관", pd.Series(0, index=f.index))
    ret = f.get("개인", pd.Series(0, index=f.index))
    out["f5"], out["f20"] = fo.rolling(5).sum(), fo.rolling(20).sum()
    out["i5"], out["i20"] = ins.rolling(5).sum(), ins.rolling(20).sum()
    out["px20"] = px.pct_change(20) * 100
    out["px5"] = px.pct_change(5) * 100

    f_sell_streak = _run_len(fo < 0)
    joint = _run_len((fo > 0) & (ins > 0))
    alone = _run_len((ret > 0) & (fo < 0) & (ins < 0))

    turn = (out["f20"] < 0) & (out["f5"] > 0)
    out["foreign_turn"] = turn & ~turn.shift(1, fill_value=False)
    out["joint_buy"] = joint == 3
    bd = (out["px20"] < -3) & (out["f20"] > 0)
    out["bottom_div"] = bd & ~bd.shift(1, fill_value=False)
    out["foreign_dump"] = (f_sell_streak == 5) & (out["px5"] < 0)
    out["retail_alone"] = alone == 3
    td = (out["px20"] > 3) & (out["f20"] < 0)
    out["top_div"] = td & ~td.shift(1, fill_value=False)

    # 수급 점수 (−100 ~ +100): 외국인·기관의 단기·중기 흐름을 각자의 과거 변동폭으로 표준화해 합산
    def z(s, w=250):
        return (s - s.rolling(w, min_periods=60).mean()) / s.rolling(w, min_periods=60).std()
    raw = 0.35 * z(out["f5"]) + 0.30 * z(out["f20"]) + 0.20 * z(out["i5"]) + 0.15 * z(out["i20"])
    out["score"] = (np.tanh(raw / 1.5) * 100).round(0)
    out["f_streak"] = np.where(fo > 0, _run_len(fo > 0), -f_sell_streak)
    return out


def score_label(v: float) -> str:
    if pd.isna(v):
        return "판단 보류"
    if v >= 50:
        return "강한 매수 우위"
    if v >= 15:
        return "매수 우위"
    if v > -15:
        return "중립"
    if v > -50:
        return "매도 우위"
    return "강한 매도 우위"


def backtest(sig: pd.DataFrame, horizons=(5, 20), gap: int = 5) -> pd.DataFrame:
    """신호별 과거 성적: 신호 다음 날부터 h거래일 뒤 수익률."""
    px = sig["price"]
    rows = []
    base = {h: (px.shift(-h) / px - 1).dropna() * 100 for h in horizons}
    for key, nm, kind, _ in SIGNALS:
        days = sig.index[sig[key].fillna(False)]
        kept, last = [], None
        for d in days:  # 연달아 나온 신호는 하나로
            if last is None or sig.index.get_loc(d) - sig.index.get_loc(last) >= gap:
                kept.append(d)
                last = d
        row = {"key": key, "신호": nm, "종류": kind, "횟수": len(kept)}
        for h in horizons:
            r = base[h].reindex(kept).dropna()
            row[f"{h}일 뒤 평균(%)"] = r.mean() if len(r) else np.nan
            row[f"{h}일 뒤 상승 확률(%)"] = (r > 0).mean() * 100 if len(r) else np.nan
            row[f"평소 {h}일 평균(%)"] = base[h].mean()
        row["마지막 발생"] = kept[-1] if kept else pd.NaT
        rows.append(row)
    return pd.DataFrame(rows)


def score_buckets(sig: pd.DataFrame, h: int = 20) -> pd.DataFrame:
    """수급 점수 구간별 이후 수익률."""
    fr = (sig["price"].shift(-h) / sig["price"] - 1) * 100
    d = pd.DataFrame({"s": sig["score"], "r": fr}).dropna()
    labels = ["강한 매도 우위", "매도 우위", "중립", "매수 우위", "강한 매수 우위"]
    d["구간"] = pd.cut(d["s"], [-101, -50, -15, 15, 50, 101], labels=labels)
    g = d.groupby("구간", observed=False)["r"]
    return pd.DataFrame({"일수": g.size(), f"{h}일 뒤 평균(%)": g.mean(),
                         "상승 확률(%)": g.apply(lambda x: (x > 0).mean() * 100 if len(x) else np.nan)}).reset_index()


def active_now(sig: pd.DataFrame, lookback: int = 5) -> list[dict]:
    """최근 lookback거래일 안에 나온 신호."""
    recent = sig.tail(lookback)
    out = []
    for key, nm, kind, desc in SIGNALS:
        hits = recent.index[recent[key].fillna(False)]
        if len(hits):
            out.append({"key": key, "name": nm, "kind": kind, "desc": desc, "date": hits[-1]})
    return out
