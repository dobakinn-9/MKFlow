"""AI 예측·분석 도구 모음.

- crash_risk      : 앞으로 1주 안 급락(코스피 −5%, S&P −3%) 확률 — 워크포워드 검증
- flow_compare    : 수급(외국인·기관) 특성을 넣었을 때와 뺐을 때 AI 모델 성적 비교
- fx_forecast     : 원/달러 방향 확률 + 예상 범위
- recession_prob  : 장단기 금리차로 본 12개월 안 미국 경기침체 확률 (뉴욕 연은 방식)
- analogs         : 지금과 시장 상황이 가장 닮은 과거 시기와 그 뒤의 흐름
- sensitivity     : 유가·금리·환율·반도체·미국 증시 변화에 대한 지수 민감도 (시나리오 계산기)
- event_study     : FOMC·고용보고서 발표일 전후 평균 움직임
- sector_rank     : 분야별 수급·모멘텀 점수 순위

※ 모든 결과는 과거 통계에 기반한 참고 자료예요.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import analysis as an
import ml
from macro_ml import range_forecast


# ── 공통: 워크포워드 분류 ─────────────────────────────────
def walk_forward(X: pd.DataFrame, y: pd.Series, fwd: int, min_train: int = 500, step: int = 21,
                 names: dict | None = None) -> dict:
    """X(특성), y(0/1, 미래 미확정은 NaN)로 과거 시점마다 학습→예측하고 오늘 확률을 계산해요."""
    data = X.join(y.rename("y")).dropna(subset=list(X.columns))
    cols = list(X.columns)
    if len(data) < min_train + step + fwd:
        return {"ok": False, "reason": f"학습할 데이터가 부족해요 ({len(data)}일)."}
    Xv, Y = data[cols].values, data["y"].values
    preds = pd.Series(np.nan, index=data.index)
    for i in range(min_train, len(data), step):
        tr_end = i - fwd
        m = ~np.isnan(Y[:tr_end])
        if m.sum() < 150 or len(np.unique(Y[:tr_end][m])) < 2:
            continue
        te = slice(i, min(i + step, len(data)))
        pr, *_ = ml._fit_predict(Xv[:tr_end][m], Y[:tr_end][m], Xv[te])
        preds.iloc[te] = pr
    hist = pd.DataFrame({"prob": preds, "y": data["y"]}).dropna()
    if len(hist) < 40 or hist["y"].nunique() < 2:
        return {"ok": False, "reason": "검증할 과거 예측이 부족해요."}
    try:
        from sklearn.metrics import roc_auc_score
        auc = float(roc_auc_score(hist["y"], hist["prob"]))
    except Exception:
        auc = float("nan")
    lab = ~np.isnan(Y)
    last = X[cols].dropna().iloc[[-1]].values
    prob, lr, *_ = ml._fit_predict(Xv[lab], Y[lab], last)
    sc, lg = lr.named_steps["standardscaler"], lr.named_steps["logisticregression"]
    contrib = pd.DataFrame({"특성": [(names or {}).get(c, c) for c in cols],
                            "기여": lg.coef_[0] * sc.transform(last)[0]}).sort_values("기여", key=abs, ascending=False)
    base = float(hist["y"].mean())
    hit = float(((hist["prob"] > 0.5) == (hist["y"] == 1)).mean() * 100)
    brier = float(((hist["prob"] - hist["y"]) ** 2).mean())
    brier_base = float(((base - hist["y"]) ** 2).mean())
    return {"ok": True, "prob": float(prob[0]), "auc": auc, "hit": hit, "base": base, "brier": brier,
            "brier_base": brier_base, "n": len(hist), "hist": hist, "contrib": contrib,
            "asof": X[cols].dropna().index[-1]}


# ── 수급 특성 ────────────────────────────────────────────
FLOW_NAMES = {"fl_f5": "외국인 5일 순매수", "fl_f20": "외국인 20일 순매수", "fl_i5": "기관 5일 순매수",
              "fl_i20": "기관 20일 순매수", "fl_score": "수급 점수", "fl_streak": "외국인 연속 매매일"}


def flow_features(flows: pd.DataFrame | None, index: pd.DatetimeIndex) -> pd.DataFrame:
    if flows is None or len(flows) < 80:
        return pd.DataFrame(index=index)
    import flow_signals as fs
    f = flows.reindex(index)
    px = pd.Series(1.0, index=index)
    sig = fs.compute(f.dropna(how="all"), px)

    def z(s, w=250):
        return (s - s.rolling(w, min_periods=60).mean()) / s.rolling(w, min_periods=60).std()
    out = pd.DataFrame(index=sig.index)
    out["fl_f5"], out["fl_f20"] = z(sig["f5"]), z(sig["f20"])
    out["fl_i5"], out["fl_i20"] = z(sig["i5"]), z(sig["i20"])
    out["fl_score"] = sig["score"] / 100
    out["fl_streak"] = sig["f_streak"].clip(-10, 10) / 10
    return out.reindex(index)


# ── 1. 급락 위험 ─────────────────────────────────────────
CRASH_NAMES = dict(ml.FEATURE_NAMES) | FLOW_NAMES | {"dd20": "20일 고점 대비 하락폭", "vol_ch": "변동성 1주 변화",
                                                     "absret5": "최근 5일 큰 움직임"}


def crash_risk(prices: pd.DataFrame, target: str, score: pd.Series, flows=None, fwd: int = 5,
               thr: float | None = None) -> dict:
    """앞으로 fwd거래일 안에 종가가 오늘보다 thr% 이상 낮아지는 날이 있을 확률."""
    thr = thr if thr is not None else (5.0 if target in ("^KS11", "^KQ11") else 3.0)
    p = prices[target]
    X = ml.build_features(prices, target, score)
    X["dd20"] = p / p.rolling(20).max() - 1
    rv = an.realized_vol(p, 10)
    X["vol_ch"] = rv / rv.shift(5) - 1
    X["absret5"] = p.pct_change().abs().rolling(5).mean() * 100
    fl = flow_features(flows, X.index)
    for c in fl.columns:
        if fl[c].notna().mean() > 0.6:
            X[c] = fl[c]
    X = X.replace([np.inf, -np.inf], np.nan)
    future_min = pd.concat([p.shift(-k) for k in range(1, fwd + 1)], axis=1).min(axis=1)
    y = ((future_min / p - 1) * 100 <= -thr).astype(float).where(p.shift(-fwd).notna())
    res = walk_forward(X, y, fwd, names=CRASH_NAMES)
    if res.get("ok"):
        res["thr"] = thr
        ratio = res["prob"] / max(res["base"], 1e-6)
        res["ratio"] = ratio
        res["level"] = "🔴 폭풍 경보" if ratio >= 2.5 else "🟠 주의" if ratio >= 1.5 else "🟢 평온"
        h = res["hist"]
        top = h[h["prob"] >= h["prob"].quantile(0.8)]
        low = h[h["prob"] <= h["prob"].quantile(0.5)]
        res["top_rate"] = float(top["y"].mean())
        res["low_rate"] = float(low["y"].mean())
    return res


# ── 2. 수급 반영 효과 ─────────────────────────────────────
def flow_compare(prices: pd.DataFrame, target: str, score: pd.Series, flows, fwd: int) -> dict:
    """수급 데이터가 있는 기간에서 '수급 없이' vs '수급 포함' 모델을 같은 조건으로 비교해요."""
    if flows is None or len(flows) < 300:
        return {"ok": False, "reason": "수급 데이터가 부족해요."}
    start = flows.index.min()
    base_X = ml.build_features(prices, target, score)
    fl = flow_features(flows, base_X.index)
    p = prices[target]
    fr = p.shift(-fwd) / p - 1
    y = (fr > 0).astype(float).where(fr.notna())
    # 이동평균 등이 안정되도록 수급 시작 60일 뒤부터
    span = base_X.index >= start + pd.Timedelta(days=90)
    Xa = base_X[span]
    Xb = Xa.join(fl[span])
    names = dict(ml.FEATURE_NAMES) | FLOW_NAMES
    a = walk_forward(Xa, y, fwd, min_train=250, step=10, names=names)
    b = walk_forward(Xb, y, fwd, min_train=250, step=10, names=names)
    if not (a.get("ok") and b.get("ok")):
        return {"ok": False, "reason": a.get("reason") or b.get("reason")}
    return {"ok": True, "without": a, "with": b, "start": Xa.dropna().index.min()}


# ── 3. 환율 ──────────────────────────────────────────────
FX_NAMES = {"fx5": "환율 1주 변화", "fx20": "환율 1개월 변화", "fx_gap": "환율 60일 평균과의 차이",
            "dxy20": "달러인덱스 1개월 변화", "us10": "미 10년물 1개월 변화", "ks20": "코스피 1개월 수익률",
            "sox20": "반도체 1개월 수익률", "oil20": "유가 1개월 변화", "vix": "VIX 수준", "jpy20": "엔/달러 1개월 변화"} | FLOW_NAMES


def fx_forecast(prices: pd.DataFrame, flows=None, fwd: int = 20) -> dict:
    if "KRW=X" not in prices:
        return {"ok": False, "reason": "환율 데이터가 없어요."}
    fx = prices["KRW=X"]
    X = pd.DataFrame(index=prices.index)
    X["fx5"], X["fx20"] = fx.pct_change(5), fx.pct_change(20)
    X["fx_gap"] = fx / fx.rolling(60).mean() - 1
    for k, t in (("dxy20", "DX-Y.NYB"), ("ks20", "^KS11"), ("sox20", "^SOX"), ("oil20", "CL=F"), ("jpy20", "JPY=X")):
        if t in prices:
            X[k] = prices[t].pct_change(20)
    if "^TNX" in prices:
        X["us10"] = prices["^TNX"].diff(20)
    if "^VIX" in prices:
        X["vix"] = prices["^VIX"] / 100
    X = X[[c for c in X.columns if X[c].notna().mean() > 0.6]].replace([np.inf, -np.inf], np.nan)
    fr = fx.shift(-fwd) / fx - 1
    y = (fr > 0).astype(float).where(fr.notna())
    res = walk_forward(X, y, fwd, names=FX_NAMES)
    res["range"] = range_forecast(fx, kind="pct")
    return res


# ── 4. 경기침체 확률 (뉴욕 연은 방식) ─────────────────────
def recession_prob(prices: pd.DataFrame) -> pd.DataFrame:
    """월평균 장단기 금리차(10년−3개월)로 12개월 뒤 경기침체 확률.

    뉴욕 연은 모형: P = Φ(−0.5333 − 0.6330 × 금리차). 금리차는 3개월물을 채권 수익률 기준으로 바꿔야 정확하지만,
    여기서는 단순 차이를 써서 근사해요.
    """
    from scipy.stats import norm
    if not {"^TNX", "^IRX"} <= set(prices.columns):
        return pd.DataFrame()
    spread = (prices["^TNX"] - prices["^IRX"]).resample("MS").mean().dropna()
    prob = pd.Series(norm.cdf(-0.5333 - 0.6330 * spread), index=spread.index) * 100
    out = pd.DataFrame({"spread": spread, "prob": prob})
    out["target_month"] = out.index + pd.DateOffset(months=12)
    return out


# ── 5. 닮은 과거 ─────────────────────────────────────────
ANALOG_FEATS = {"ret20": "1개월 수익률", "ret60": "3개월 수익률", "gap120": "120일선과의 거리", "rvol": "변동성",
                "vix": "VIX", "rate": "미 10년물 수준", "rate20": "금리 1개월 변화", "oil20": "유가 1개월 변화",
                "fx20": "환율·달러 1개월 변화", "sox60": "반도체 3개월 수익률"}


def analog_state(prices: pd.DataFrame, target: str) -> pd.DataFrame:
    p = prices[target]
    f = pd.DataFrame(index=prices.index)
    f["ret20"], f["ret60"] = p.pct_change(20), p.pct_change(60)
    f["gap120"] = p / p.rolling(120).mean() - 1
    f["rvol"] = an.realized_vol(p)
    if "^VIX" in prices:
        f["vix"] = prices["^VIX"]
    if "^TNX" in prices:
        f["rate"], f["rate20"] = prices["^TNX"], prices["^TNX"].diff(20)
    if "CL=F" in prices:
        f["oil20"] = prices["CL=F"].pct_change(20)
    fx = "KRW=X" if target in ("^KS11", "^KQ11") else "DX-Y.NYB"
    if fx in prices:
        f["fx20"] = prices[fx].pct_change(20)
    if "^SOX" in prices:
        f["sox60"] = prices["^SOX"].pct_change(60)
    keep = [c for c in f.columns if f[c].notna().mean() > 0.6]
    return f[keep].replace([np.inf, -np.inf], np.nan).dropna()


def analogs(prices: pd.DataFrame, target: str, k: int = 5, horizon: int = 60, gap: int = 60) -> dict:
    st = analog_state(prices, target)
    if len(st) < 400:
        return {"ok": False, "reason": "비교할 과거 데이터가 부족해요. 불러올 기간을 늘려 보세요."}
    z = (st - st.mean()) / st.std()
    now = z.iloc[-1]
    cand = z.iloc[:-(horizon + 5)]
    dist = np.sqrt(((cand - now) ** 2).mean(axis=1))
    picks = []
    for d in dist.sort_values().index:
        if all(abs((d - q).days) > gap * 1.4 for q in picks):
            picks.append(d)
        if len(picks) == k:
            break
    p = prices[target].dropna()
    paths, rows = {}, []
    for d in picks:
        i = p.index.get_indexer([d])[0]
        seg = p.iloc[i:i + horizon + 1]
        path = (seg / seg.iloc[0] - 1).values * 100
        paths[d] = path
        sim = float(np.exp(-dist[d]) * 100)
        rows.append({"날짜": d, "닮은 정도(%)": sim,
                     "20일 뒤(%)": path[20] if len(path) > 20 else np.nan,
                     f"{horizon}일 뒤(%)": path[-1] if len(path) > horizon else np.nan,
                     "그 사이 최저(%)": float(np.min(path))})
    diff = (z.loc[picks].mean() - now).abs().sort_values()
    return {"ok": True, "picks": picks, "paths": paths, "table": pd.DataFrame(rows),
            "now": st.iloc[-1], "closest_feats": [ANALOG_FEATS.get(c, c) for c in diff.index[:3]],
            "state_hist": st}


# ── 6. 시나리오 계산기 (민감도 회귀) ───────────────────────
SENS = {"oil": ("CL=F", "pct", "유가"), "rate": ("^TNX", "diff", "미 10년물 금리"),
        "fx": ("KRW=X", "pct", "원/달러 환율"), "sox": ("^SOX", "pct", "미국 반도체 지수"),
        "spx": ("^GSPC", "pct", "S&P 500"), "vix": ("^VIX", "diff", "VIX")}


def sensitivity(prices: pd.DataFrame, target: str, horizon: int = 20, years: int = 3) -> dict:
    """target의 horizon일 수익률 ~ 각 요인의 horizon일 변화. 최근 years년, 겹치지 않는 구간으로 추정."""
    from sklearn.linear_model import Ridge
    p = prices.tail(252 * years)
    y = p[target].pct_change(horizon) * 100
    X = pd.DataFrame(index=p.index)
    for k, (t, kind, _) in SENS.items():
        if t == target or t not in p:
            continue
        X[k] = (p[t].pct_change(horizon) * 100) if kind == "pct" else p[t].diff(horizon)
    d = X.join(y.rename("y")).dropna().iloc[::5]  # 5일 간격으로 겹침 줄이기
    if len(d) < 60:
        return {"ok": False, "reason": "데이터가 부족해요."}
    cols = list(X.columns)
    m = Ridge(alpha=1.0).fit(d[cols].values, d["y"].values)
    resid = d["y"].values - m.predict(d[cols].values)
    r2 = 1 - resid.var() / d["y"].var()
    return {"ok": True, "coef": dict(zip(cols, m.coef_)), "intercept": float(m.intercept_), "resid_sd": float(resid.std()),
            "r2": float(r2), "cols": cols, "n": len(d), "now": float(p[target].dropna().iloc[-1])}


# ── 7. 이벤트 영향 ───────────────────────────────────────
FOMC_DATES = [  # 미국 FOMC 금리 결정일 (회의 둘째 날, 미국 시간)
    "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10", "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]


def first_fridays(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    """미국 고용보고서는 대체로 매월 첫 금요일에 나와요 (일부 예외 있음)."""
    out = []
    for m in pd.date_range(start.replace(day=1), end, freq="MS"):
        d = m + pd.Timedelta(days=(4 - m.weekday()) % 7)
        out.append(d)
    return out


def event_study(price: pd.Series, dates: list, window: int = 5, lag: int = 0) -> dict:
    """이벤트일 기준 −window ~ +window 거래일 누적 수익률(이벤트 전날 = 0)과 이벤트 반응일 변동폭."""
    p = price.dropna()
    ret = p.pct_change() * 100
    paths, react = [], []
    for d in pd.to_datetime(dates):
        pos = p.index.searchsorted(d)
        pos += lag
        if pos - window - 1 < 0 or pos + window >= len(p):
            continue
        base = p.iloc[pos - 1]
        seg = p.iloc[pos - window - 1:pos + window + 1] / base * 100 - 100
        paths.append(seg.values)
        react.append(abs(ret.iloc[pos]))
    if not paths:
        return {"ok": False}
    arr = np.vstack(paths)
    x = np.arange(-window - 1, window + 1)
    return {"ok": True, "x": x, "mean": arr.mean(axis=0), "q25": np.percentile(arr, 25, axis=0),
            "q75": np.percentile(arr, 75, axis=0), "n": len(paths),
            "react_abs": float(np.mean(react)), "normal_abs": float(ret.abs().mean()),
            "up_rate": float((arr[:, window + 1] > 0).mean() * 100),
            "after_mean": float(np.mean(arr[:, -1] - arr[:, window + 1]))}


# ── 8. 분야별 순위 ────────────────────────────────────────
def sector_rank(sec: pd.DataFrame) -> dict:
    """분야 점수 = 큰손 수급(5·20일, 각 분야의 평소 수준 대비) + 가격 모멘텀(20일) + 반전 보정(5일 과열).

    최근 기간에서 점수가 높았던 분야가 실제로 다음 10일에 더 강했는지(순위 상관)도 계산해요.
    """
    d = sec.sort_values("date").copy()
    d["big"] = (d["외국인"] + d["기관"]) / 1e8
    piv_big = d.pivot_table(index="date", columns="sector", values="big", aggfunc="sum")
    piv_ret = (d.pivot_table(index="date", columns="sector", values="등락률", aggfunc="mean", dropna=False)
               .reindex(index=piv_big.index, columns=piv_big.columns).fillna(0))
    idx = (1 + piv_ret / 100).cumprod()

    def zc(df):  # 각 날짜에서 분야 간 표준화
        return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)

    def zt(df, w=60):  # 분야별 평소 수준 대비
        return (df - df.rolling(w, min_periods=20).mean()) / df.rolling(w, min_periods=20).std()
    f5, f20 = piv_big.rolling(5).sum(), piv_big.rolling(20).sum()
    m20, m5 = idx.pct_change(20) * 100, idx.pct_change(5) * 100
    parts = {"수급 5일": zc(zt(f5)), "수급 20일": zc(zt(f20)), "모멘텀 20일": zc(m20), "단기 과열(5일)": -zc(m5) * 0.5}
    score = sum(w * parts[k] for k, w in (("수급 5일", 0.35), ("수급 20일", 0.30), ("모멘텀 20일", 0.25), ("단기 과열(5일)", 0.20)))
    fwd10 = idx.shift(-10) / idx - 1
    ics = []
    for dt_ in score.index:
        s, r = score.loc[dt_], fwd10.loc[dt_]
        ok = s.notna() & r.notna()
        if ok.sum() >= 6:
            ics.append(s[ok].rank().corr(r[ok].rank()))
    last = score.dropna(how="all").iloc[-1].sort_values(ascending=False)
    table = pd.DataFrame({"점수": last})
    for k, v in parts.items():
        table[k] = v.iloc[-1].reindex(last.index)
    table["20일 수익률(%)"] = m20.iloc[-1].reindex(last.index)
    table["큰손 20일(억)"] = f20.iloc[-1].reindex(last.index)
    return {"table": table, "ic_mean": float(np.nanmean(ics)) if ics else np.nan, "ic_n": len(ics),
            "ic_hit": float(np.mean([i > 0 for i in ics]) * 100) if ics else np.nan,
            "asof": score.dropna(how="all").index[-1], "history": score}
