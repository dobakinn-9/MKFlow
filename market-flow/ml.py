"""AI(머신러닝) 예측 엔진.

목표: '앞으로 N거래일 뒤 지수가 오늘보다 높을까?'의 확률을 추정해요.

방법
- 특성(feature): 지수 수익률·이동평균 거리·RSI·변동성·VIX·금리·유가·환율·반도체·신용·구리/금·흐름 점수
- 모델 두 개를 평균(앙상블)
    1) 로지스틱 회귀  — 단순하고 해석이 쉬움
    2) 그래디언트 부스팅 — 비선형 관계를 잡음
- 워크포워드 검증: 과거 시점에 '그때까지의 데이터'로만 학습하고 그 뒤를 예측해
  실제로 맞혔는지 기록해요. 미래 정보를 쓰지 않아서 성적표가 정직해요.

주의: 주가 예측은 본질적으로 어렵고, 50%를 조금 넘기기도 쉽지 않아요.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import analysis as an

FEATURE_NAMES = {
    "ret5": "1주 수익률",
    "ret20": "1개월 수익률",
    "ret60": "3개월 수익률",
    "ma60_gap": "60일선과의 거리",
    "ma_cross": "20일선 − 60일선",
    "rsi": "RSI(과열·과매도)",
    "rvol": "실제 변동성",
    "vix": "VIX 수준",
    "vix_ch": "VIX 1개월 변화",
    "rate_ch": "미 10년물 1개월 변화",
    "oil_ch": "유가 1개월 변화",
    "fx_ch": "환율·달러 1개월 변화",
    "sox_ch": "반도체 1개월 수익률",
    "sox_gap": "반도체 60일선 거리",
    "credit_ch": "하이일드÷국채 1개월 변화",
    "cg_ch": "구리÷금 1개월 변화",
    "score": "흐름 점수",
}


def _pct(s: pd.Series, n: int) -> pd.Series:
    return s / s.shift(n) - 1


def build_features(prices: pd.DataFrame, target: str, score: pd.Series) -> pd.DataFrame:
    p = prices[target]
    f = pd.DataFrame(index=prices.index)
    f["ret5"], f["ret20"], f["ret60"] = _pct(p, 5), _pct(p, 20), _pct(p, 60)
    ma20, ma60 = p.rolling(20).mean(), p.rolling(60).mean()
    f["ma60_gap"] = p / ma60 - 1
    f["ma_cross"] = ma20 / ma60 - 1
    f["rsi"] = an.rsi(p) / 100
    f["rvol"] = an.realized_vol(p) / 100
    if "^VIX" in prices:
        f["vix"] = prices["^VIX"] / 100
        f["vix_ch"] = _pct(prices["^VIX"], 20)
    if "^TNX" in prices:
        f["rate_ch"] = prices["^TNX"] - prices["^TNX"].shift(20)
    if "CL=F" in prices:
        f["oil_ch"] = _pct(prices["CL=F"], 20)
    fx = "KRW=X" if target in ("^KS11", "^KQ11") else "DX-Y.NYB"
    if fx in prices:
        f["fx_ch"] = _pct(prices[fx], 20)
    if "^SOX" in prices:
        f["sox_ch"] = _pct(prices["^SOX"], 20)
        f["sox_gap"] = prices["^SOX"] / prices["^SOX"].rolling(60).mean() - 1
    if {"HYG", "IEF"} <= set(prices.columns):
        f["credit_ch"] = _pct(prices["HYG"] / prices["IEF"], 20)
    if {"HG=F", "GC=F"} <= set(prices.columns):
        f["cg_ch"] = _pct(prices["HG=F"] / prices["GC=F"], 20)
    f["score"] = score / 10
    # 데이터가 거의 없는 열(불러오기 실패)은 빼요.
    keep = [c for c in f.columns if f[c].notna().mean() > 0.6]
    return f[keep].replace([np.inf, -np.inf], np.nan)


def _models():
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    lr = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=500))
    gb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150,
                                        min_samples_leaf=40, l2_regularization=1.0, random_state=0)
    return lr, gb


def _fit_predict(X_tr, y_tr, X_te, w_lr: float = 0.5):
    """두 모델을 학습하고 가중 평균 확률을 돌려줘요. (앙상블 확률, 로지스틱 모델, 로지스틱 확률, 부스팅 확률)"""
    lr, gb = _models()
    lr.fit(X_tr, y_tr)
    gb.fit(X_tr, y_tr)
    p_lr, p_gb = lr.predict_proba(X_te)[:, 1], gb.predict_proba(X_te)[:, 1]
    return w_lr * p_lr + (1 - w_lr) * p_gb, lr, p_lr, p_gb


def _labeled(prices: pd.DataFrame, target: str, score: pd.Series, fwd: int):
    feats = build_features(prices, target, score)
    p = prices[target]
    fwd_ret = p.shift(-fwd) / p - 1
    data = feats.copy()
    data["y"] = (fwd_ret > 0).astype(float).where(fwd_ret.notna())
    data["fwd_ret"] = fwd_ret
    return feats, data.dropna(subset=list(feats.columns))


def predict_today(prices: pd.DataFrame, target: str, score: pd.Series, fwd: int) -> dict | None:
    """정답이 확정된 전체 데이터로 학습해 오늘의 두 모델 확률을 따로 돌려줘요 (예측 일기장용)."""
    feats, data = _labeled(prices, target, score, fwd)
    cols = list(feats.columns)
    lab = data["y"].notna().values
    if lab.sum() < 300:
        return None
    X, y = data[cols].values, data["y"].values
    last = feats[cols].dropna()
    _, _, p_lr, p_gb = _fit_predict(X[lab], y[lab], last.iloc[[-1]].values)
    return {"asof": last.index[-1], "p_lr": float(p_lr[0]), "p_gb": float(p_gb[0])}


def run(prices: pd.DataFrame, target: str, score: pd.Series, fwd: int,
        min_train: int = 500, step: int = 21, w_lr: float = 0.5) -> dict:
    """워크포워드 검증 + 오늘 예측. 결과는 dict로 돌려줘요.

    w_lr: 오늘 예측에서 로지스틱 회귀에 줄 가중치(나머지는 부스팅). 실전 성적으로 정해져요.
    """
    feats, data = _labeled(prices, target, score, fwd)
    p = prices[target]
    if len(data) < min_train + step + fwd:
        return {"ok": False, "reason": f"학습할 데이터가 부족해요 ({len(data)}일). 사이드바에서 불러올 기간을 늘려 보세요."}

    cols = list(feats.columns)
    X, y = data[cols].values, data["y"].values
    idx = data.index
    preds = pd.Series(np.nan, index=idx)

    # 워크포워드: i 시점 예측에는 i-fwd 이전까지 '정답이 확정된' 데이터만 사용
    for i in range(min_train, len(data), step):
        tr_end = i - fwd
        mask = ~np.isnan(y[:tr_end])
        if mask.sum() < 200 or len(np.unique(y[:tr_end][mask])) < 2:
            continue
        te = slice(i, min(i + step, len(data)))
        pr, *_ = _fit_predict(X[:tr_end][mask], y[:tr_end][mask], X[te])
        preds.iloc[te] = pr

    hist = pd.DataFrame({"prob": preds, "y": data["y"], "fwd_ret": data["fwd_ret"]}).dropna()
    if len(hist) < 60:
        return {"ok": False, "reason": "검증할 수 있는 과거 예측이 부족해요."}

    hit = ((hist["prob"] > 0.5) == (hist["y"] == 1)).mean() * 100
    base_up = hist["y"].mean() * 100
    naive = max(base_up, 100 - base_up)  # 늘 '오른다'(또는 늘 '내린다')고 찍었을 때
    brier = float(((hist["prob"] - hist["y"]) ** 2).mean())
    try:
        from sklearn.metrics import roc_auc_score
        auc = float(roc_auc_score(hist["y"], hist["prob"]))
    except Exception:
        auc = float("nan")

    # 확률 구간별 실제 결과 (보정표)
    bins = [0, 0.4, 0.5, 0.6, 1.0]
    labels = ["40% 미만", "40~50%", "50~60%", "60% 이상"]
    hist["구간"] = pd.cut(hist["prob"], bins=bins, labels=labels, include_lowest=True)
    g = hist.groupby("구간", observed=False)
    calib = pd.DataFrame({"일수": g.size(), "실제 상승 비율(%)": g["y"].mean() * 100,
                          "평균 수익률(%)": g["fwd_ret"].mean() * 100}).reset_index()

    # 오늘 예측: 정답이 확정된 전체 데이터로 학습
    lab = ~np.isnan(y)
    last_x = feats[cols].dropna().iloc[[-1]].values
    today_prob, lr_model, p_lr, p_gb = _fit_predict(X[lab], y[lab], last_x, w_lr)
    today_prob = float(today_prob[0])

    # 오늘 예측에 각 특성이 기여한 방향 (로지스틱 회귀 계수 × 표준화 값)
    scaler, logit = lr_model.named_steps["standardscaler"], lr_model.named_steps["logisticregression"]
    z = scaler.transform(last_x)[0]
    contrib = pd.DataFrame({"특성": [FEATURE_NAMES.get(c, c) for c in cols],
                            "기여": logit.coef_[0] * z}).sort_values("기여", key=abs, ascending=False)

    return {
        "ok": True, "prob": today_prob, "p_lr": float(p_lr[0]), "p_gb": float(p_gb[0]), "w_lr": w_lr,
        "asof": feats[cols].dropna().index[-1],
        "hit": hit, "naive": naive, "base_up": base_up, "brier": brier, "auc": auc,
        "n_oos": int(len(hist)), "calib": calib, "contrib": contrib,
        "history": hist[["prob"]].join(p.rename("price")),
        "features": [FEATURE_NAMES.get(c, c) for c in cols],
    }


def confidence(res: dict) -> str:
    """모델 성적표를 보고 이 예측을 얼마나 믿을지 한 줄로."""
    edge = res["hit"] - res["naive"]
    auc = res["auc"]
    if np.isnan(auc) or auc < 0.52 or edge < 0:
        return "낮음 — 과거 성적이 '늘 같은 쪽으로 찍기'보다 낫지 않아요. 참고만 하세요."
    if auc < 0.56 or edge < 2:
        return "보통 — 과거에 약간의 예측력이 있었어요."
    return "비교적 높음 — 과거 검증에서 의미 있는 예측력을 보였어요(그래도 틀릴 수 있어요)."
