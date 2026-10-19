"""AI 예측 일기장: 매일 예측을 기록하고, 만기가 되면 채점하고, 잘 맞힌 모델에 가중치를 더 줘요.

GitHub Actions가 평일마다 이 파일을 실행해요 (.github/workflows/daily_predict.yml).
직접 실행:  cd market-flow && python tracker.py

기록 파일 (저장소에 저장돼서 서버가 재시작돼도 남아요)
- data/predictions.csv  : AI 모델의 매일 예측과 채점 결과
- data/outlook_log.csv  : Claude 시장 전망의 시나리오 확률과 채점 결과
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import analysis as an
import data as dt
import ml
from config import SCORE_TARGETS

PRED_FILE = dt.DATA_DIR / "predictions.csv"
OUTLOOK_FILE = dt.DATA_DIR / "outlook_log.csv"
HORIZONS = [5, 20]  # 1주, 1개월
OUTLOOK_TICKERS = {"kospi": "^KS11", "spx": "^GSPC"}
OUTLOOK_DAYS = 21   # Claude 전망은 약 1개월(21거래일) 뒤 채점
OUTLOOK_BAND = 3.0  # ±3% 이내면 '기본(박스권)' 시나리오가 맞은 것으로 봐요

PRED_COLS = ["asof", "target", "horizon", "p_lr", "p_gb", "w_lr", "prob", "price", "score", "regime",
             "created_utc", "due_price", "ret_pct", "actual_up", "hit", "hit_lr", "hit_gb", "graded_on"]
OUTLOOK_COLS = ["asof", "market", "stance", "p_up", "p_base", "p_down", "start_price",
                "end_price", "ret_pct", "outcome", "prob_on_outcome", "top_hit", "graded_on"]


# ── 파일 읽고 쓰기 ───────────────────────────────────────
def load_predictions() -> pd.DataFrame:
    if not PRED_FILE.exists():
        return pd.DataFrame(columns=PRED_COLS)
    df = pd.read_csv(PRED_FILE, parse_dates=["asof"])
    return df


def load_outlook_log() -> pd.DataFrame:
    if not OUTLOOK_FILE.exists():
        return pd.DataFrame(columns=OUTLOOK_COLS)
    return pd.read_csv(OUTLOOK_FILE, parse_dates=["asof"])


def _save(df: pd.DataFrame, path, cols):
    df = df.reindex(columns=cols)
    df["asof"] = pd.to_datetime(df["asof"]).dt.strftime("%Y-%m-%d")
    df.sort_values([c for c in ("asof", "target", "horizon", "market") if c in df.columns]).to_csv(path, index=False)


# ── 가중치: 최근 실전 성적이 좋은 모델에 더 귀 기울이기 ────
def live_weights(preds: pd.DataFrame, target: str, horizon: int, window: int = 60) -> dict:
    """최근 채점된 예측의 브라이어 점수(낮을수록 정확)로 로지스틱 회귀 가중치를 정해요.

    채점된 표본이 적을 때는 0.5(반반)에 가깝게 두고, 표본이 쌓일수록 성적 차이를 더 반영해요.
    """
    g = preds[(preds["target"] == target) & (preds["horizon"] == horizon) & preds["actual_up"].notna()]
    g = g.sort_values("asof").tail(window)
    n = len(g)
    if n < 10:
        return {"w_lr": 0.5, "n": n, "brier_lr": np.nan, "brier_gb": np.nan}
    y = g["actual_up"].astype(float)
    b_lr = float(((g["p_lr"] - y) ** 2).mean())
    b_gb = float(((g["p_gb"] - y) ** 2).mean())
    inv_lr, inv_gb = 1 / max(b_lr, 1e-6), 1 / max(b_gb, 1e-6)
    raw = inv_lr / (inv_lr + inv_gb)
    trust = min(1.0, n / window)          # 표본이 많을수록 성적을 더 믿어요
    w = 0.5 + (raw - 0.5) * trust * 3     # 차이를 조금 키워서 반영
    return {"w_lr": float(np.clip(w, 0.2, 0.8)), "n": n, "brier_lr": b_lr, "brier_gb": b_gb}


def live_report(preds: pd.DataFrame, target: str, horizon: int) -> dict:
    """실전 성적 요약."""
    g = preds[(preds["target"] == target) & (preds["horizon"] == horizon)]
    graded = g[g["actual_up"].notna()]
    out = {"n_total": len(g), "n_graded": len(graded), "n_pending": len(g) - len(graded)}
    if len(graded):
        up_rate = graded["actual_up"].mean() * 100
        out.update({
            "hit": graded["hit"].mean() * 100, "hit_lr": graded["hit_lr"].mean() * 100,
            "hit_gb": graded["hit_gb"].mean() * 100, "naive": max(up_rate, 100 - up_rate),
            "recent_hit": graded.sort_values("asof").tail(20)["hit"].mean() * 100,
        })
    return out


# ── 채점 ─────────────────────────────────────────────────
def _due(prices: pd.Series, asof: pd.Timestamp, n: int):
    """asof 이후 n거래일째 가격. 아직 그날이 안 왔으면 None."""
    s = prices.dropna()
    after = s[s.index > asof]
    if len(after) < n:
        return None
    return after.iloc[n - 1]


def grade_predictions(preds: pd.DataFrame, prices: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    graded = 0
    for i, r in preds[preds["actual_up"].isna()].iterrows():
        if r["target"] not in prices:
            continue
        due = _due(prices[r["target"]], pd.Timestamp(r["asof"]), int(r["horizon"]))
        if due is None:
            continue
        up = float(due > r["price"])
        preds.loc[i, ["due_price", "ret_pct", "actual_up", "graded_on"]] = [due, (due / r["price"] - 1) * 100, up, today]
        preds.loc[i, "hit"] = float((r["prob"] > 0.5) == bool(up))
        preds.loc[i, "hit_lr"] = float((r["p_lr"] > 0.5) == bool(up))
        preds.loc[i, "hit_gb"] = float((r["p_gb"] > 0.5) == bool(up))
        graded += 1
    return preds, graded


# ── 오늘 예측 기록 ───────────────────────────────────────
def record_predictions(preds: pd.DataFrame, prices: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    added = 0
    rows = []
    for t in SCORE_TARGETS:
        if t not in prices or prices[t].dropna().empty:
            continue
        score = an.flow_score(an.build_factors(prices, t))
        for h in HORIZONS:
            res = ml.predict_today(prices, t, score, h)
            if res is None:
                continue
            asof = pd.Timestamp(res["asof"]).normalize()
            dup = (preds["target"] == t) & (preds["horizon"] == h) & (pd.to_datetime(preds["asof"]) == asof)
            if dup.any():
                continue
            w = live_weights(preds, t, h)["w_lr"]
            prob = w * res["p_lr"] + (1 - w) * res["p_gb"]
            sc = float(score.loc[:asof].dropna().iloc[-1])
            rows.append({"asof": asof, "target": t, "horizon": h, "p_lr": round(res["p_lr"], 4),
                         "p_gb": round(res["p_gb"], 4), "w_lr": round(w, 3), "prob": round(prob, 4),
                         "price": round(float(prices[t].loc[:asof].dropna().iloc[-1]), 4), "score": sc,
                         "regime": an.regime(sc), "created_utc": datetime.now(timezone.utc).isoformat(timespec="minutes")})
            added += 1
    if rows:
        preds = pd.concat([preds, pd.DataFrame(rows)], ignore_index=True)
    return preds, added


# ── Claude 전망 기록·채점 ────────────────────────────────
def record_and_grade_outlook(log: pd.DataFrame, prices: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    added = graded = 0
    f = dt.DATA_DIR / "ai_outlook.json"
    if f.exists():
        o = json.loads(f.read_text(encoding="utf-8"))
        asof = pd.Timestamp(o["asof"])
        for m in o["markets"]:
            tk = OUTLOOK_TICKERS.get(m["id"])
            if not tk or tk not in prices:
                continue
            if ((log["market"] == m["id"]) & (pd.to_datetime(log["asof"]) == asof)).any():
                continue
            probs = {"긍정": 0, "중립": 0, "부정": 0}
            for s in m["scenarios"]:
                probs[s["tone"]] += s["prob"]
            start = prices[tk].loc[:asof].dropna()
            if start.empty:
                continue
            log = pd.concat([log, pd.DataFrame([{
                "asof": asof, "market": m["id"], "stance": m["stance"], "p_up": probs["긍정"],
                "p_base": probs["중립"], "p_down": probs["부정"], "start_price": float(start.iloc[-1])}])], ignore_index=True)
            added += 1

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for i, r in log[log["outcome"].isna()].iterrows():
        tk = OUTLOOK_TICKERS.get(r["market"])
        end = _due(prices[tk], pd.Timestamp(r["asof"]), OUTLOOK_DAYS) if tk in prices else None
        if end is None:
            continue
        ret = (end / r["start_price"] - 1) * 100
        outcome = "상승" if ret > OUTLOOK_BAND else "하락" if ret < -OUTLOOK_BAND else "기본"
        p_on = {"상승": r["p_up"], "기본": r["p_base"], "하락": r["p_down"]}[outcome]
        top = max([("상승", r["p_up"]), ("기본", r["p_base"]), ("하락", r["p_down"])], key=lambda x: x[1])[0]
        log.loc[i, ["end_price", "ret_pct", "outcome", "prob_on_outcome", "top_hit", "graded_on"]] = \
            [end, ret, outcome, p_on, float(top == outcome), today]
        graded += 1
    return log, added, graded


def main():
    prices, _, note = dt.load_prices("6y")
    if "샘플" in note and not dt.demo_mode():
        raise SystemExit(f"실제 시세를 불러오지 못해 기록을 건너뛰어요: {note}")
    preds = load_predictions()
    preds, n_graded = grade_predictions(preds, prices)
    preds, n_added = record_predictions(preds, prices)
    _save(preds, PRED_FILE, PRED_COLS)

    log = load_outlook_log()
    log, o_added, o_graded = record_and_grade_outlook(log, prices)
    _save(log, OUTLOOK_FILE, OUTLOOK_COLS)

    print(f"AI 예측: 새 기록 {n_added}건, 채점 {n_graded}건 · Claude 전망: 새 기록 {o_added}건, 채점 {o_graded}건")
    for t in SCORE_TARGETS:
        for h in HORIZONS:
            w = live_weights(preds, t, h)
            print(f"  {t} {h}일: 로지스틱 가중치 {w['w_lr']:.2f} (채점 {w['n']}건)")


if __name__ == "__main__":
    main()
