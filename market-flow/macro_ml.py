"""채권 금리·미국 물가 예측.

1) 채권 금리
   - 방향: 'N거래일 뒤 미 10년물 금리가 지금보다 높을까?' 확률 (로지스틱 회귀 + 그래디언트 부스팅, 워크포워드 검증)
   - 범위: 최근 변동성을 반영한 과거 변화폭 분포로 5·20·60거래일 뒤 예상 범위(10%~90%)
2) 미국 물가 (CPI)
   - 다음 몇 달의 전월비 상승률을 과거 물가 흐름·유가·기대인플레이션으로 예측(릿지 회귀)
   - 전월비를 쌓아 전년비(뉴스에 나오는 'CPI 3.7%') 경로를 계산 — 1년 전 수치가 빠지는 '기저효과' 반영
   - 유가 시나리오(−20% / 그대로 / +20%)별 경로, 과거 성적표(단순 예측 대비 오차)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import ml

# ── 1. 채권 금리 ─────────────────────────────────────────
YIELD_FEATURES = {
    "y_ch5": "금리 1주 변화", "y_ch20": "금리 1개월 변화", "y_ch60": "금리 3개월 변화",
    "y_gap60": "금리 60일 평균과의 차이", "slope": "장단기 금리차(10년−3개월)", "slope_ch": "금리차 1개월 변화",
    "oil": "유가 1개월 변화", "dxy": "달러 1개월 변화", "vix": "VIX 수준", "move": "채권 변동성(MOVE)",
    "spx": "S&P 500 1개월 수익률", "infl": "물가연동채÷국채 1개월 변화 (기대인플레)", "cg": "구리÷금 1개월 변화",
}


def yield_features(prices: pd.DataFrame, col: str = "^TNX") -> pd.DataFrame:
    y = prices[col]
    f = pd.DataFrame(index=prices.index)
    f["y_ch5"], f["y_ch20"], f["y_ch60"] = y.diff(5), y.diff(20), y.diff(60)
    f["y_gap60"] = y - y.rolling(60).mean()
    if "^IRX" in prices:
        sl = y - prices["^IRX"]
        f["slope"], f["slope_ch"] = sl, sl.diff(20)
    pairs = {"oil": "CL=F", "dxy": "DX-Y.NYB", "spx": "^GSPC"}
    for k, t in pairs.items():
        if t in prices:
            f[k] = prices[t].pct_change(20)
    if "^VIX" in prices:
        f["vix"] = prices["^VIX"] / 100
    if "^MOVE" in prices:
        f["move"] = prices["^MOVE"] / 100
    if {"TIP", "IEF"} <= set(prices.columns):
        f["infl"] = (prices["TIP"] / prices["IEF"]).pct_change(20)
    if {"HG=F", "GC=F"} <= set(prices.columns):
        f["cg"] = (prices["HG=F"] / prices["GC=F"]).pct_change(20)
    keep = [c for c in f.columns if f[c].notna().mean() > 0.6]
    return f[keep].replace([np.inf, -np.inf], np.nan)


def yield_direction(prices: pd.DataFrame, fwd: int, col: str = "^TNX", min_train: int = 500, step: int = 21) -> dict:
    if col not in prices or prices[col].notna().sum() < 800:
        return {"ok": False, "reason": "금리 데이터가 부족해요."}
    feats = yield_features(prices, col)
    y = prices[col]
    fut = y.shift(-fwd) - y
    data = feats.copy()
    data["y"] = (fut > 0).astype(float).where(fut.notna())
    data["chg"] = fut
    data = data.dropna(subset=list(feats.columns))
    cols = list(feats.columns)
    X, Y = data[cols].values, data["y"].values
    preds = pd.Series(np.nan, index=data.index)
    for i in range(min_train, len(data), step):
        tr_end = i - fwd
        m = ~np.isnan(Y[:tr_end])
        if m.sum() < 200 or len(np.unique(Y[:tr_end][m])) < 2:
            continue
        te = slice(i, min(i + step, len(data)))
        pr, *_ = ml._fit_predict(X[:tr_end][m], Y[:tr_end][m], X[te])
        preds.iloc[te] = pr
    hist = pd.DataFrame({"prob": preds, "y": data["y"], "chg": data["chg"]}).dropna()
    if len(hist) < 60:
        return {"ok": False, "reason": "검증할 과거 예측이 부족해요."}
    hit = ((hist["prob"] > 0.5) == (hist["y"] == 1)).mean() * 100
    up = hist["y"].mean() * 100
    try:
        from sklearn.metrics import roc_auc_score
        auc = float(roc_auc_score(hist["y"], hist["prob"]))
    except Exception:
        auc = float("nan")
    lab = ~np.isnan(Y)
    last = feats[cols].dropna().iloc[[-1]].values
    prob, lr, p_lr, p_gb = ml._fit_predict(X[lab], Y[lab], last)
    sc, lg = lr.named_steps["standardscaler"], lr.named_steps["logisticregression"]
    contrib = pd.DataFrame({"특성": [YIELD_FEATURES.get(c, c) for c in cols],
                            "기여": lg.coef_[0] * sc.transform(last)[0]}).sort_values("기여", key=abs, ascending=False)
    return {"ok": True, "prob": float(prob[0]), "hit": hit, "naive": max(up, 100 - up), "auc": auc,
            "n": len(hist), "contrib": contrib, "history": hist[["prob"]].join(y.rename("yield"))}


def range_forecast(s: pd.Series, horizons=(5, 20, 60), qs=(0.1, 0.25, 0.5, 0.75, 0.9), kind: str = "diff") -> pd.DataFrame:
    """변동성 조정 과거 변화폭 분포로 만든 예상 범위.

    과거 h일 변화를 '그때의 변동성'으로 나눠 표준화한 뒤, 지금 변동성을 곱해 되돌려요.
    그래서 시장이 출렁일 때는 범위가 넓어지고, 잔잔할 때는 좁아져요.
    """
    s = s.dropna()
    step = s.diff() if kind == "diff" else np.log(s).diff()
    vol = step.rolling(20).std()
    now, vol_now = s.iloc[-1], vol.iloc[-1]
    rows = []
    for h in horizons:
        ch = s.diff(h) if kind == "diff" else np.log(s).diff(h)
        z = (ch / (vol.shift(h) * np.sqrt(h))).replace([np.inf, -np.inf], np.nan).dropna()
        if len(z) < 100:
            continue
        row = {"horizon": h}
        for q in qs:
            move = z.quantile(q) * vol_now * np.sqrt(h)
            row[f"q{int(q * 100)}"] = now + move if kind == "diff" else now * np.exp(move)
        rows.append(row)
    return pd.DataFrame(rows)


# ── 2. 미국 물가 ─────────────────────────────────────────
def _monthly(fred: dict) -> pd.DataFrame:
    df = pd.DataFrame(index=pd.DatetimeIndex([]))
    if "CPIAUCSL" in fred:
        df = fred["CPIAUCSL"].rename("cpi").to_frame()
    if "CPILFESL" in fred:
        df = df.join(fred["CPILFESL"].rename("core"), how="outer")
    for sid, nm in (("DCOILWTICO", "oil"), ("T10YIE", "be10")):
        if sid in fred:
            m = fred[sid].resample("MS").mean()
            df = df.join(m.rename(nm), how="left")
    return df.sort_index()


def _infl_design(m: pd.DataFrame, col: str) -> pd.DataFrame:
    """월 t 정보로 t+1 전월비를 예측하는 설계 행렬."""
    mm = np.log(m[col]).diff()
    X = pd.DataFrame(index=m.index)
    X["mm1"] = mm
    X["mm3"] = mm.rolling(3).mean()
    X["mm6"] = mm.rolling(6).mean()
    X["mm12"] = mm.rolling(12).mean()
    if col == "cpi" and "core" in m:
        X["core3"] = np.log(m["core"]).diff().rolling(3).mean()
    if "oil" in m:
        lo = np.log(m["oil"])
        X["oil1"], X["oil3"] = lo.diff(), lo.diff(3)
    if "be10" in m:
        X["be_ch"] = m["be10"].diff(3)
    return X


def inflation_forecast(fred: dict, months: int = 6, oil_shift: float = 0.0) -> dict:
    """CPI·근원 CPI의 앞으로 months개월 전년비 경로.

    oil_shift: 예측 기간 동안 유가가 지금보다 몇 % 변한다고 가정할지(예: 0.2 = +20%), 기간에 걸쳐 고르게 반영.
    """
    from sklearn.linear_model import Ridge

    m = _monthly(fred)
    if "cpi" not in m or m["cpi"].dropna().shape[0] < 60:
        return {"ok": False, "reason": "물가 데이터가 부족해요."}
    m = m[m["cpi"].notna()].copy()
    if "oil" in m:
        m["oil"] = m["oil"].ffill()
    out = {"ok": True, "last_month": m.index[-1]}
    for col in [c for c in ("cpi", "core") if c in m and m[c].notna().sum() > 60]:
        X = _infl_design(m, col)
        y = np.log(m[col]).diff().shift(-1)  # 다음 달 전월비
        data = X.join(y.rename("y")).dropna()
        cols = list(X.columns)
        model = Ridge(alpha=1e-4).fit(data[cols].values, data["y"].values)
        resid_sd = float(np.std(data["y"].values - model.predict(data[cols].values)))

        # 과거 성적표: 최근 60개월, 그때까지 데이터로만 학습해 다음 달 맞히기 (단순 예측 = 최근 3개월 평균)
        errs, naive = [], []
        idx = data.index
        for k in range(max(60, len(idx) - 60), len(idx)):
            tr = data.iloc[:k - 1]
            if len(tr) < 48:
                continue
            mdl = Ridge(alpha=1e-4).fit(tr[cols].values, tr["y"].values)
            p = mdl.predict(data[cols].iloc[[k]].values)[0]
            errs.append(abs(p - data["y"].iloc[k]))
            naive.append(abs(data["mm3"].iloc[k] - data["y"].iloc[k]))
        mae, mae_naive = (np.mean(errs) * 100, np.mean(naive) * 100) if errs else (np.nan, np.nan)

        # 미래 경로: 한 달씩 예측해 이어 붙이기
        hist = m[[c for c in ("cpi", "core", "oil", "be10") if c in m]].copy()
        level = hist[col].copy()
        oil_path = None
        if "oil" in hist:
            oil_now = hist["oil"].dropna().iloc[-1]
            oil_path = [oil_now * (1 + oil_shift * (i + 1) / months) for i in range(months)]
        sim = hist.copy()
        fut_idx = pd.date_range(m.index[-1] + pd.offsets.MonthBegin(1), periods=months, freq="MS")
        preds_mm = []
        for i, d in enumerate(fut_idx):
            Xi = _infl_design(sim, col).iloc[[-1]][cols]
            mm_hat = float(model.predict(Xi.values)[0])
            preds_mm.append(mm_hat)
            new = {col: sim[col].iloc[-1] * np.exp(mm_hat)}
            if col == "cpi" and "core" in sim:
                new["core"] = sim["core"].iloc[-1] * np.exp(sim["core"].pipe(np.log).diff().tail(3).mean())
            if oil_path is not None:
                new["oil"] = oil_path[i]
            if "be10" in sim:
                new["be10"] = sim["be10"].iloc[-1]
            sim = pd.concat([sim, pd.DataFrame(new, index=[d])])
        lvl = sim[col]
        yoy = (lvl / lvl.shift(12) - 1) * 100
        k = np.arange(1, months + 1)
        band = 1.28 * resid_sd * np.sqrt(k) * 100  # 대략 80% 범위
        fut_yoy = yoy.loc[fut_idx]
        out[col] = {
            "yoy_hist": yoy.loc[:m.index[-1]].dropna(),
            "yoy_fut": fut_yoy, "lo": fut_yoy - band, "hi": fut_yoy + band,
            "mm_fut": pd.Series(np.array(preds_mm) * 100, index=fut_idx),
            "mm_last3": float(np.log(m[col]).diff().tail(3).mean() * 100),
            "ann3": float(((m[col].iloc[-1] / m[col].iloc[-4]) ** 4 - 1) * 100),
            "mae": mae, "mae_naive": mae_naive,
            # 기저효과: 앞으로 빠져나갈 1년 전 전월비
            "base": (np.log(m[col]).diff().iloc[-12:].values[:months] * 100),
        }
    return out
