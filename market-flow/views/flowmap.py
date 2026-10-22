"""흐름을 한눈에: 흐름 연결 지도 / 오늘 바뀐 것 / 업종 순환 지도."""
from __future__ import annotations

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analysis as an
import common as cm
from config import SCORE_TARGETS, US_SECTORS

EOK = 1e8  # 억 원


# ════════════════════════════════════════════════════════
# 공통 계산
# ════════════════════════════════════════════════════════
def _s(p: pd.DataFrame, t: str) -> pd.Series:
    return p[t].dropna() if t in p else pd.Series(dtype=float)


def _chg(s: pd.Series, n: int, diff: bool = False) -> float:
    s = s.dropna()
    if len(s) <= n:
        return float("nan")
    return float(s.iloc[-1] - s.iloc[-1 - n]) if diff else float((s.iloc[-1] / s.iloc[-1 - n] - 1) * 100)


def _foreign() -> pd.Series:
    df, _ = cm.flows("KOSPI")
    if df is None or "외국인" not in df:
        return pd.Series(dtype=float)
    return df["외국인"].dropna()


# 연결 고리 정의: (키, 이름, 아이콘, 티커 또는 'FOREIGN', 차이로 볼지, 단위, 좋은/나쁜 기준(1개월), 코스피에 좋은 방향)
NODES = [
    ("oil", "유가 (WTI)", "🛢️", "CL=F", False, "%", 5.0, "down"),
    ("rate", "미국 10년물 금리", "🏦", "^TNX", True, "%p", 0.15, "down"),
    ("dxy", "달러 가치 (달러인덱스)", "💵", "DX-Y.NYB", False, "%", 1.0, "down"),
    ("krw", "원/달러 환율", "💱", "KRW=X", False, "%", 1.0, "down"),
    ("sox", "미국 반도체 (SOX)", "🔌", "^SOX", False, "%", 3.0, "up"),
    ("foreign", "외국인 코스피 매매", "🌏", "FOREIGN", None, "억", 10000.0, "up"),
    ("kospi", "코스피", "🇰🇷", "^KS11", False, "%", 3.0, "up"),
]

# 고리 사이 연결: (앞, 뒤, 평소 관계 부호, 설명)
LINKS = [
    ("oil", "rate", +1, "유가가 오르면 물가 걱정에 금리가 올라요"),
    ("rate", "dxy", +1, "미국 금리가 오르면 달러로 돈이 몰려 달러가 강해져요"),
    ("dxy", "krw", +1, "달러가 강해지면 원화가 약해져(환율 상승) 외국인에게 한국 주식이 덜 매력적이에요"),
    ("krw", "foreign", -1, "환율이 오르면(원화 약세) 외국인이 팔고, 내리면 사는 경향이 있어요"),
    ("sox", "foreign", +1, "미국 반도체가 오르면 외국인이 삼성전자·SK하이닉스를 사러 와요"),
    ("foreign", "kospi", +1, "외국인 매매가 코스피 방향을 가장 크게 좌우해요"),
]


def _node_series(p: pd.DataFrame, key: str) -> pd.Series:
    t = next(n[3] for n in NODES if n[0] == key)
    if t == "FOREIGN":
        return _foreign()
    return _s(p, t)


def _node_state(p: pd.DataFrame, node, shift: int = 0) -> dict:
    """shift일 전 기준으로 계산 (어제와 비교할 때 shift=1)."""
    key, nm, icon, t, diff, unit, th, good = node
    s = _node_series(p, key)
    if shift:
        s = s.iloc[:-shift]
    if s.empty:
        return {"key": key, "name": nm, "icon": icon, "ok": False}
    if t == "FOREIGN":
        m1 = float(s.tail(20).sum() / EOK)
        w1 = float(s.tail(5).sum() / EOK)
        d1 = float(s.iloc[-1] / EOK)
        now = f"오늘 {d1:+,.0f}억"
        m1_txt, w1_txt = f"{m1:+,.0f}억", f"{w1:+,.0f}억"
    else:
        m1, w1 = _chg(s, 21, diff), _chg(s, 5, diff)
        last = float(s.iloc[-1])
        now = f"{last:.2f}%" if t == "^TNX" else (f"{last:,.1f}원" if t == "KRW=X" else f"{last:,.2f}")
        f = "{:+.2f}" if diff else "{:+.1f}"
        m1_txt = (f.format(m1) + unit) if not np.isnan(m1) else "—"
        w1_txt = (f.format(w1) + unit) if not np.isnan(w1) else "—"
        if diff:  # 금리는 bp로 보기 쉽게
            m1_txt = f"{m1 * 100:+.0f}bp" if not np.isnan(m1) else "—"
            w1_txt = f"{w1 * 100:+.0f}bp" if not np.isnan(w1) else "—"
    sign = 1 if good == "up" else -1
    sc = 0 if np.isnan(m1) else sign * m1 / th  # +면 코스피에 우호, −면 부담
    # 최근 1주가 1개월과 반대 방향이면 '바뀌는 중'
    wsc = 0 if np.isnan(w1) else sign * w1 / (th / 2)
    if sc >= 1:
        sig, color = "🟢 우호", cm.UP
    elif sc <= -1:
        sig, color = "🔴 부담", cm.DOWN
    else:
        sig, color = "🟡 중립", cm.ORANGE
    turning = ""
    if sc <= -0.5 and wsc >= 1:
        turning = "↗ 최근 1주는 좋아지는 중"
    elif sc >= 0.5 and wsc <= -1:
        turning = "↘ 최근 1주는 나빠지는 중"
    return {"key": key, "name": nm, "icon": icon, "ok": True, "now": now, "m1": m1_txt, "w1": w1_txt,
            "score": sc, "wscore": wsc, "sig": sig, "color": color, "turning": turning}


def _link_strength(p: pd.DataFrame, a: str, b: str, sign: int, window: int = 60) -> dict:
    """최근 60거래일, 5일 변화끼리의 상관으로 '이 고리가 지금 작동하나'를 판단."""
    sa, sb = _node_series(p, a), _node_series(p, b)
    if sa.empty or sb.empty:
        return {"txt": "자료 부족", "c": float("nan"), "level": 0}

    def chg5(s, key):
        if key == "foreign":
            return s.rolling(5).sum()
        if key == "rate":
            return s.diff(5)
        return s.pct_change(5)

    df = pd.concat([chg5(sa, a), chg5(sb, b)], axis=1, join="inner").dropna().tail(window)
    if len(df) < 25:
        return {"txt": "자료 부족", "c": float("nan"), "level": 0}
    c = float(df.iloc[:, 0].corr(df.iloc[:, 1]))
    sc = c * sign
    if sc >= 0.35:
        return {"txt": "강하게 작동 중", "c": c, "level": 2}
    if sc >= 0.15:
        return {"txt": "약하게 작동", "c": c, "level": 1}
    if sc <= -0.15:
        return {"txt": "평소와 반대로 움직임", "c": c, "level": -1}
    return {"txt": "지금은 거의 안 이어짐", "c": c, "level": 0}


# ════════════════════════════════════════════════════════
# 1. 흐름 연결 지도
# ════════════════════════════════════════════════════════
_CSS = """
<style>
.fm-wrap{max-width:720px;margin:0 auto}
.fm-node{display:flex;align-items:center;gap:12px;background:var(--secondary-background-color,#141A24);
  border:1px solid rgba(148,163,184,.18);border-left:5px solid var(--c);border-radius:14px;padding:12px 14px}
.fm-ic{font-size:1.5rem;line-height:1}
.fm-main{flex:1;min-width:0}
.fm-nm{font-weight:700;font-size:1rem}
.fm-sub{color:#94A3B8;font-size:.82rem;margin-top:2px}
.fm-turn{color:#F59E0B;font-size:.8rem;margin-top:2px}
.fm-sig{font-weight:700;white-space:nowrap;font-size:.95rem}
.fm-link{display:flex;gap:10px;align-items:flex-start;padding:6px 6px 6px 22px;color:#CBD5E1;font-size:.85rem}
.fm-arrow{font-size:1.2rem;line-height:1;color:var(--lc)}
.fm-lt b{color:var(--lc)}
.fm-side{margin:4px 0 0 0}
</style>
"""


def _node_html(n: dict) -> str:
    if not n.get("ok"):
        return (f"<div class='fm-node' style='--c:#475569'><div class='fm-ic'>{n['icon']}</div>"
                f"<div class='fm-main'><div class='fm-nm'>{html.escape(n['name'])}</div>"
                f"<div class='fm-sub'>자료를 불러오지 못했어요</div></div></div>")
    turn = f"<div class='fm-turn'>{n['turning']}</div>" if n["turning"] else ""
    return (f"<div class='fm-node' style='--c:{n['color']}'><div class='fm-ic'>{n['icon']}</div>"
            f"<div class='fm-main'><div class='fm-nm'>{html.escape(n['name'])}</div>"
            f"<div class='fm-sub'>{html.escape(n['now'])} · 1주 {n['w1']} · 1개월 {n['m1']}</div>{turn}</div>"
            f"<div class='fm-sig'>{n['sig']}</div></div>")


def _link_html(desc: str, ls: dict) -> str:
    col = {2: cm.UP, 1: "#86EFAC", 0: cm.MUTED, -1: cm.ORANGE}[ls["level"]]
    c = "" if np.isnan(ls["c"]) else f" (상관 {ls['c']:+.2f})"
    return (f"<div class='fm-link' style='--lc:{col}'><div class='fm-arrow'>⬇</div>"
            f"<div class='fm-lt'>{html.escape(desc)}<br><b>{ls['txt']}</b>{c}</div></div>")


def chain_state(p: pd.DataFrame, shift: int = 0) -> dict[str, dict]:
    return {n[0]: _node_state(p, n, shift) for n in NODES}


def flow_map():
    st.title("흐름 연결 지도")
    cm.explain("""
- 요즘 한국 시장은 **유가 → 미국 금리 → 달러 → 원/달러 환율 → 외국인 매매 → 코스피** 순서로 영향을 주고받아요. 미국 반도체(SOX)는 외국인 매매로 바로 이어지는 옆길이에요.
- 각 칸의 색은 **최근 1개월 변화가 코스피에 우호적인지(🟢) 부담인지(🔴)**예요. 예를 들어 유가·금리·달러·환율은 **내려야** 🟢, 반도체·외국인 매수·코스피는 **올라야** 🟢이에요.
- 칸 사이 화살표 설명의 **'작동 중/안 이어짐'**은 최근 60거래일 동안 두 지표가 평소 관계대로 함께 움직였는지(5일 변화끼리의 상관계수)로 판단해요. 작동 중인 고리가 시장을 실제로 움직이는 힘이에요.
- **↗/↘ 표시**는 1개월 흐름과 최근 1주 흐름이 엇갈릴 때, 즉 방향이 바뀌고 있을 수 있을 때 붙어요.
""")
    p = cm.prices()
    cm.warn_if_sample(cm.price_note())
    nodes = chain_state(p)
    links = {(a, b): (_link_strength(p, a, b, s), d) for a, b, s, d in LINKS}

    # 요약: 어디가 막혔나
    valid = [n for n in nodes.values() if n.get("ok") and n["key"] != "kospi"]
    bad = sorted([n for n in valid if n["score"] <= -1], key=lambda n: n["score"])
    good = sorted([n for n in valid if n["score"] >= 1], key=lambda n: -n["score"])
    active = [(a, b) for (a, b), (ls, _) in links.items() if ls["level"] == 2]
    lines = []
    if bad:
        lines.append("🔴 **부담 지점**: " + ", ".join(f"{n['name']}({n['m1']})" for n in bad[:3]))
    if good:
        lines.append("🟢 **받쳐주는 힘**: " + ", ".join(f"{n['name']}({n['m1']})" for n in good[:3]))
    if active:
        nm = {n[0]: n[1].split(" (")[0] for n in NODES}
        lines.append("🔗 **지금 강하게 작동하는 고리**: " + ", ".join(f"{nm[a]} → {nm[b]}" for a, b in active))
    turning = [n for n in valid if n["turning"]]
    if turning:
        lines.append("🔄 **방향이 바뀌는 중**: " + ", ".join(f"{n['name']} {n['turning'][:1]}" for n in turning))
    if lines:
        with st.container(border=True):
            st.markdown("**한 줄 요약**  \n" + "  \n".join(lines))

    # 지도 본문 (세로로 쌓아서 휴대폰에서도 그대로 보여요)
    h = [_CSS, "<div class='fm-wrap'>"]
    order = ["oil", "rate", "dxy", "krw", "foreign", "kospi"]
    for i, k in enumerate(order):
        if k == "foreign":  # 반도체 옆길을 외국인 바로 위에 끼워요
            h.append("<div class='fm-side'>" + _node_html(nodes["sox"]) + "</div>")
            ls, d = links[("sox", "foreign")]
            h.append(_link_html("↳ 옆길: " + d, ls))
        h.append(_node_html(nodes[k]))
        if i + 1 < len(order):
            nxt = order[i + 1]
            ls, d = links[(k, nxt)]
            h.append(_link_html(d, ls))
    h.append("</div>")
    st.markdown("".join(h), unsafe_allow_html=True)

    # 고리 강도 표
    with st.expander("고리별 연결 강도 자세히"):
        nm = {n[0]: n[1] for n in NODES}
        rows = [{"고리": f"{nm[a]} → {nm[b]}", "평소 관계": "같은 방향" if s > 0 else "반대 방향",
                 "최근 60일 상관": links[(a, b)][0]["c"], "판단": links[(a, b)][0]["txt"]} for a, b, s, _ in LINKS]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                     column_config={"최근 60일 상관": st.column_config.NumberColumn(format="%+.2f")})
        st.caption("상관계수는 −1~+1. 평소 관계 방향으로 0.35 이상이면 '강하게 작동', 0.15 이상이면 '약하게 작동'으로 봐요. "
                   "외국인 매매 자료는 최근 60거래일까지만 있어 그 고리는 표본이 짧아요.")
    cm.source(cm.price_note() + " · 외국인 매매: " + (cm.flows("KOSPI")[1] or ""))


# ════════════════════════════════════════════════════════
# 2. 업종 순환 지도 (RRG: 상대 강도 × 상대 모멘텀)
# ════════════════════════════════════════════════════════
QUAD = {  # (x≥100, y≥100)
    (True, True): ("주도", cm.UP, "시장보다 강하고 더 강해지는 중"),
    (True, False): ("약해짐", cm.ORANGE, "아직 강하지만 힘이 빠지는 중"),
    (False, False): ("소외", cm.DOWN, "시장보다 약하고 계속 약해지는 중"),
    (False, True): ("살아남", cm.BLUE, "아직 약하지만 힘이 붙는 중"),
}


def rrg(px: pd.DataFrame, bench: pd.Series, ratio_win: int = 21, mom_win: int = 5) -> dict[str, pd.DataFrame]:
    """업종별 (상대강도 x, 상대모멘텀 y) 시계열. 둘 다 100이 시장 평균."""
    out = {}
    for c in px.columns:
        df = pd.concat([px[c], bench], axis=1, join="inner").dropna()
        if len(df) < ratio_win + mom_win + 10:
            continue
        rel = df.iloc[:, 0] / df.iloc[:, 1]
        x = 100 * rel / rel.rolling(ratio_win).mean()
        x = x.ewm(span=3).mean()
        y = 100 + (x - x.shift(mom_win)) * 2  # 변화 속도를 보기 쉽게 키움
        out[c] = pd.DataFrame({"x": x, "y": y}).dropna()
    return out


def quad_of(x: float, y: float):
    return QUAD[(x >= 100, y >= 100)]


def _kr_sector_prices() -> tuple[pd.DataFrame | None, pd.DataFrame | None, str]:
    sec, _, note = cm.sector_flows()
    if sec is None or sec.empty:
        return None, None, note
    r = sec.pivot_table(index="date", columns="sector", values="등락률").sort_index()
    px = (1 + r.fillna(0) / 100).cumprod() * 100
    fo = sec.pivot_table(index="date", columns="sector", values="외국인").sort_index()
    return px, fo, note


def kr_rrg():
    """(업종별 RRG, 외국인 20일 순매수(억), 출처)."""
    px, fo, note = _kr_sector_prices()
    if px is None:
        return None, None, note
    bench = px.mean(axis=1)  # 10개 분야 평균 = 시장
    return rrg(px, bench), (fo.tail(20).sum() / EOK) if fo is not None else None, note


def us_rrg(p: pd.DataFrame):
    cols = [t for t in US_SECTORS if t in p]
    if not cols or "SPY" not in p and "^GSPC" not in p:
        return None
    bench = p["SPY"] if "SPY" in p else p["^GSPC"]
    out = rrg(p[cols].tail(300), bench.tail(300))
    return {US_SECTORS[k]: v for k, v in out.items()}


def _rrg_fig(data: dict[str, pd.DataFrame], tail: int, step: int, extra: dict | None = None) -> go.Figure:
    fig = go.Figure()
    xs, ys = [], []
    for nm, df in data.items():
        pts = df.iloc[::-1].iloc[::step].iloc[::-1].tail(tail)  # 마지막 점을 꼭 포함하면서 step 간격
        xs += list(pts["x"])
        ys += list(pts["y"])
        lab, col, _ = quad_of(pts["x"].iloc[-1], pts["y"].iloc[-1])
        fig.add_trace(go.Scatter(x=pts["x"], y=pts["y"], mode="lines", line=dict(color=col, width=1.5),
                                 opacity=0.55, hoverinfo="skip", showlegend=False))
        hover = f"<b>{nm}</b><br>{lab}<br>상대 강도 {pts['x'].iloc[-1]:.1f} · 모멘텀 {pts['y'].iloc[-1]:.1f}"
        if extra and nm in extra and not pd.isna(extra[nm]):
            hover += f"<br>외국인 20일 {extra[nm]:+,.0f}억"
        fig.add_trace(go.Scatter(x=[pts["x"].iloc[-1]], y=[pts["y"].iloc[-1]], mode="markers+text",
                                 marker=dict(size=13, color=col, line=dict(color="#0B0F17", width=1.5)),
                                 text=[nm], textposition="top center", textfont=dict(size=12),
                                 hovertemplate=hover + "<extra></extra>", showlegend=False))
    dx = max(abs(max(xs, default=101) - 100), abs(min(xs, default=99) - 100), 1.0) * 1.15
    dy = max(abs(max(ys, default=101) - 100), abs(min(ys, default=99) - 100), 1.0) * 1.15
    for (rx, ry), (lab, col, _) in QUAD.items():
        fig.add_shape(type="rect", x0=100, x1=100 + dx if rx else 100 - dx, y0=100, y1=100 + dy if ry else 100 - dy,
                      fillcolor=col, opacity=0.06, line_width=0, layer="below")
        fig.add_annotation(x=100 + (dx * 0.95 if rx else -dx * 0.95), y=100 + (dy * 0.95 if ry else -dy * 0.95),
                           text=f"<b>{lab}</b>", showarrow=False, font=dict(color=col, size=13),
                           xanchor="right" if rx else "left", yanchor="top" if ry else "bottom")
    fig.add_hline(y=100, line_color=cm.MUTED, line_width=1)
    fig.add_vline(x=100, line_color=cm.MUTED, line_width=1)
    fig.update_xaxes(title="상대 강도 (오른쪽 = 시장보다 강함)", range=[100 - dx, 100 + dx], zeroline=False)
    fig.update_yaxes(title="상대 모멘텀 (위 = 힘이 붙는 중)", range=[100 - dy, 100 + dy], zeroline=False)
    fig.update_layout(hovermode="closest")
    return fig


def _rrg_table(data: dict[str, pd.DataFrame], lag: int, extra=None) -> pd.DataFrame:
    rows = []
    for nm, df in data.items():
        x, y = df["x"].iloc[-1], df["y"].iloc[-1]
        lab, _, desc = quad_of(x, y)
        before = quad_of(df["x"].iloc[-1 - lag], df["y"].iloc[-1 - lag])[0] if len(df) > lag else "—"
        move = "그대로" if before == lab else f"{before} → {lab}"
        r = {"업종": nm, "지금 위치": lab, f"{lag}거래일 전 대비": move, "의미": desc, "_o": x + (y - 100)}
        if extra is not None:
            r["외국인 20일(억)"] = extra.get(nm, np.nan)
        rows.append(r)
    order = {"주도": 0, "살아남": 1, "약해짐": 2, "소외": 3}
    df = pd.DataFrame(rows)
    df["_q"] = df["지금 위치"].map(order)
    return df.sort_values(["_q", "_o"], ascending=[True, False]).drop(columns=["_q", "_o"])


def rotation_map():
    st.title("업종 순환 지도")
    cm.explain("""
- 돈이 **어느 업종에서 빠져 어디로 가는지** 한 장으로 보는 지도예요 (전문가들이 쓰는 'RRG' 방식을 쉽게 바꿨어요).
- **가로(상대 강도)**: 오른쪽일수록 시장보다 많이 올랐어요. **세로(상대 모멘텀)**: 위쪽일수록 그 강함이 더 커지는 중이에요.
- 업종은 보통 **시계 방향**으로 돌아요: 🔵 **살아남**(바닥에서 힘 붙음) → 🟢 **주도** → 🟠 **약해짐** → 🔴 **소외** → 다시 살아남.
- 꼬리 선은 최근 몇 주 동안 지나온 길이에요. **꼬리가 어느 쪽으로 향하는지**가 흐름의 방향이에요.
- 한국은 앱에서 추적하는 10개 분야(대표 종목 평균)를 그 10개 분야 평균과 비교해요. 미국은 업종 ETF를 S&P 500과 비교해요.
""")
    tail = st.radio("꼬리 길이", ["2주", "1개월", "2개월"], index=1, horizontal=True, key="rrg_tail")
    tail_n = {"2주": 3, "1개월": 5, "2개월": 9}[tail]
    tab_kr, tab_us = st.tabs(["🇰🇷 한국 분야", "🇺🇸 미국 업종"])

    with tab_kr:
        data, fo, note = kr_rrg()
        if not data:
            st.info(note if data is None else "분야별 자료가 아직 짧아요.")
        else:
            cm.show(_rrg_fig(data, tail_n, 5, fo.to_dict() if fo is not None else None), 520)
            st.dataframe(_rrg_table(data, 5, fo.to_dict() if fo is not None else None), hide_index=True,
                         use_container_width=True,
                         column_config={"외국인 20일(억)": st.column_config.NumberColumn(format="%+,.0f")})
            _rrg_comment(data, fo)
            cm.source(note)

    with tab_us:
        p = cm.prices()
        data = us_rrg(p)
        if not data:
            st.info("미국 업종 ETF 자료가 없어요.")
        else:
            cm.show(_rrg_fig(data, tail_n, 5), 520)
            st.dataframe(_rrg_table(data, 5), hide_index=True, use_container_width=True)
            _rrg_comment(data, None)
            cm.source(cm.price_note())


def _rrg_comment(data, fo):
    lead = [nm for nm, df in data.items() if quad_of(df["x"].iloc[-1], df["y"].iloc[-1])[0] == "주도"]
    rise = [nm for nm, df in data.items() if quad_of(df["x"].iloc[-1], df["y"].iloc[-1])[0] == "살아남"]
    fade = [nm for nm, df in data.items() if quad_of(df["x"].iloc[-1], df["y"].iloc[-1])[0] == "약해짐"]
    parts = []
    if lead:
        parts.append(f"지금 돈이 몰린 곳은 **{', '.join(lead)}**")
    if rise:
        parts.append(f"새로 힘이 붙는 곳은 **{', '.join(rise)}**")
    if fade:
        parts.append(f"힘이 빠지는 곳은 **{', '.join(fade)}**")
    if parts:
        txt = "이에요. ".join(parts) + "이에요."
        if fo is not None and len(fo):
            top = fo.sort_values()
            txt += f" 외국인은 최근 20거래일 **{top.index[-1]}**(+{top.iloc[-1]:,.0f}억)을 가장 많이 사고 **{top.index[0]}**({top.iloc[0]:+,.0f}억)을 가장 많이 팔았어요."
        st.markdown(txt)


# ════════════════════════════════════════════════════════
# 3. 오늘 바뀐 것 (첫 화면 맨 위)
# ════════════════════════════════════════════════════════
def _streak(s: pd.Series) -> int:
    """마지막 값과 같은 부호가 몇 일 연속인지 (마지막 포함)."""
    sg = np.sign(s.dropna().values)
    if not len(sg) or sg[-1] == 0:
        return 0
    n = 0
    for v in sg[::-1]:
        if v != sg[-1]:
            break
        n += 1
    return n


def changes(p: pd.DataFrame) -> list[tuple[float, str]]:
    """(중요도, 문장) 목록. 중요도가 큰 순으로 정렬해서 돌려줘요."""
    out: list[tuple[float, str]] = []

    def add(w, txt):
        if w and not np.isnan(w):
            out.append((float(w), txt))

    # 지수 큰 움직임
    for t, nm, th in [("^KS11", "코스피", 1.2), ("^GSPC", "S&P 500", 1.0), ("^SOX", "미국 반도체(SOX)", 2.0),
                      ("^KQ11", "코스닥", 1.5)]:
        s = _s(p, t)
        if len(s) < 3:
            continue
        d = _chg(s, 1)
        if abs(d) >= th:
            prev = _chg(s.iloc[:-1], 1)
            flip = " — 전날과 반대 방향" if not np.isnan(prev) and np.sign(prev) != np.sign(d) and abs(prev) >= th else ""
            add(abs(d) / th, f"{nm} {d:+.2f}% {'급등' if d > 0 else '급락'}{flip}")
        # 20일선 돌파·이탈
        ma = s.rolling(20).mean()
        if len(ma.dropna()) > 2:
            a0, a1 = s.iloc[-2] > ma.iloc[-2], s.iloc[-1] > ma.iloc[-1]
            if a0 != a1:
                add(1.4, f"{nm}, 20일 평균선 {'위로 돌파' if a1 else '아래로 이탈'} — 단기 흐름 {'개선' if a1 else '약화'}")

    # 외국인 수급 전환·연속
    f = _foreign()
    if len(f) >= 5:
        today_v = f.iloc[-1] / EOK
        st_n = _streak(f)
        prev_n = _streak(f.iloc[:-1])
        if st_n == 1 and prev_n >= 3:
            add(2.2 + min(abs(today_v) / 5000, 1.5),
                f"외국인이 {prev_n}일 연속 {'순매도' if today_v > 0 else '순매수'}를 끝내고 "
                f"{'순매수' if today_v > 0 else '순매도'}({today_v:+,.0f}억)로 돌아섬")
        elif st_n >= 3:
            tot = f.tail(st_n).sum() / EOK
            add(1.2 + st_n * 0.2, f"외국인 {st_n}일 연속 {'순매수' if today_v > 0 else '순매도'} (누적 {tot:+,.0f}억)")
        elif abs(today_v) >= 5000:
            add(abs(today_v) / 4000, f"외국인 하루 {today_v:+,.0f}억 대규모 {'순매수' if today_v > 0 else '순매도'}")

    # 금리·환율·유가·VIX
    s = _s(p, "^TNX")
    if len(s) > 2:
        d = (s.iloc[-1] - s.iloc[-2]) * 100
        if abs(d) >= 5:
            add(abs(d) / 5, f"미국 10년물 금리 {d:+.0f}bp ({s.iloc[-1]:.2f}%) — 주식엔 {'부담' if d > 0 else '숨통'}")
    s = _s(p, "KRW=X")
    if len(s) > 22:
        d = _chg(s, 1)
        hi, lo = s.iloc[-21:-1].max(), s.iloc[-21:-1].min()
        if s.iloc[-1] > hi:
            add(1.6, f"원/달러 {s.iloc[-1]:,.1f}원, 최근 한 달 최고 — 원화 약세")
        elif s.iloc[-1] < lo:
            add(1.6, f"원/달러 {s.iloc[-1]:,.1f}원, 최근 한 달 최저 — 원화 강세")
        elif abs(d) >= 0.5:
            add(abs(d) / 0.5, f"원/달러 {d:+.2f}% ({s.iloc[-1]:,.1f}원)")
    s = _s(p, "CL=F")
    if len(s) > 2:
        d = _chg(s, 1)
        if abs(d) >= 3:
            add(abs(d) / 3, f"유가(WTI) {d:+.1f}% ({s.iloc[-1]:.1f}달러)")
    s = _s(p, "^VIX")
    if len(s) > 2:
        v0, v1 = s.iloc[-2], s.iloc[-1]
        for lv in (20, 25, 30):
            if (v0 < lv) != (v1 < lv):
                add(2.0 if lv >= 25 else 1.5, f"공포지수(VIX) {v1:.1f}, {lv} {'위로 올라섬' if v1 >= lv else '아래로 내려옴'}")
                break
        else:
            d = _chg(s, 1)
            if abs(d) >= 12:
                add(abs(d) / 12, f"공포지수(VIX) {d:+.0f}% ({v1:.1f})")

    # 흐름 점수 국면 변화
    for t, nm in SCORE_TARGETS.items():
        try:
            sc, _ = cm.score_bundle(t, cm.period())
            sc = sc.dropna()
            if len(sc) > 2:
                r0, r1 = an.regime(float(sc.iloc[-2])), an.regime(float(sc.iloc[-1]))
                if r0 != r1:
                    add(2.0, f"{nm} 흐름 점수 국면 변화: {r0} → {r1} ({sc.iloc[-1]:+.1f})")
                elif abs(sc.iloc[-1] - sc.iloc[-2]) >= 2:
                    add(abs(sc.iloc[-1] - sc.iloc[-2]) / 2,
                        f"{nm} 흐름 점수 {sc.iloc[-2]:+.1f} → {sc.iloc[-1]:+.1f}")
        except Exception:
            pass

    # 흐름 연결 지도 신호 변화
    try:
        now, before = chain_state(p), chain_state(p, 1)
        for k, n in now.items():
            b = before.get(k, {})
            if n.get("ok") and b.get("ok") and n["sig"] != b["sig"] and k != "kospi":
                add(1.3, f"흐름 지도: {n['name']} {b['sig']} → {n['sig']}")
    except Exception:
        pass

    # 분야별 수급·업종 순환
    try:
        sec, _, _ = cm.sector_flows()
        if sec is not None and not sec.empty:
            last = sec[sec["date"] == sec["date"].max()].set_index("sector")["외국인"] / EOK
            top, bot = last.idxmax(), last.idxmin()
            if last[top] >= 1000:
                add(last[top] / 2500, f"외국인 돈이 {top}에 집중 ({last[top]:+,.0f}억)")
            if last[bot] <= -1000:
                add(-last[bot] / 2500, f"외국인이 {bot}에서 가장 많이 뺌 ({last[bot]:+,.0f}억)")
        data, _, _ = kr_rrg()
        for nm, df in (data or {}).items():
            if len(df) > 5:
                q0 = quad_of(df["x"].iloc[-6], df["y"].iloc[-6])[0]
                q1 = quad_of(df["x"].iloc[-1], df["y"].iloc[-1])[0]
                if q0 != q1 and q1 in ("주도", "살아남", "약해짐"):
                    add(1.1, f"업종 순환: {nm} '{q0}' → '{q1}' (1주 사이)")
    except Exception:
        pass

    out.sort(key=lambda x: -x[0])
    return out


def changes_card(p: pd.DataFrame):
    try:
        ch = changes(p)
    except Exception as e:  # 첫 화면이 깨지지 않도록
        st.caption(f"오늘 바뀐 것을 계산하지 못했어요 ({e})")
        return
    with st.container(border=True):
        st.markdown("**🆕 어제보다 달라진 것**")
        if not ch:
            st.markdown("눈에 띄게 달라진 흐름은 없어요. 어제 흐름이 그대로 이어지고 있어요.")
            return
        st.markdown("\n".join(f"{i}. {t}" for i, (_, t) in enumerate(ch[:3], 1)))
        if len(ch) > 3:
            with st.expander(f"나머지 {len(ch) - 3}개 더 보기"):
                st.markdown("\n".join(f"- {t}" for _, t in ch[3:]))
