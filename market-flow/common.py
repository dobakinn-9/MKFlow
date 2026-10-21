"""여러 페이지가 함께 쓰는 데이터 캐시·차트 도우미."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analysis as an
import data as dt
from config import CACHE_TTL, FORWARD_DAYS, SCORE_TARGETS

# 다크 배경에서 잘 보이도록 밝은 색을 써요.
UP, DOWN, MUTED, BLUE, ORANGE = "#22C55E", "#EF4444", "#94A3B8", "#3B82F6", "#F59E0B"
SPAN = {"1개월": 21, "3개월": 63, "6개월": 126, "1년": 252, "3년": 756}


# ── 설정값 (사이드바에서 정한 값) ─────────────────────────
def target() -> str:
    return st.session_state.get("target", "^KS11")


def target_name() -> str:
    return SCORE_TARGETS[target()]


def fwd() -> int:
    return st.session_state.get("fwd", FORWARD_DAYS)


def period() -> str:
    return st.session_state.get("period", "6y")


# ── 캐시된 데이터 ────────────────────────────────────────
@st.cache_data(ttl=CACHE_TTL, show_spinner="시장 데이터를 불러오는 중…")
def _prices(p: str):
    return dt.load_prices(p)


def prices() -> pd.DataFrame:
    return _prices(period())[0]


def volumes() -> pd.DataFrame:
    return _prices(period())[1]


def price_note() -> str:
    return _prices(period())[2]


@st.cache_data(ttl=CACHE_TTL, show_spinner="투자자별 수급을 불러오는 중…")
def flows(market: str):
    return dt.load_investor_flows(market)


@st.cache_data(ttl=1800)
def sector_flows():
    return dt.load_sector_flows()


@st.cache_data(ttl=3600 * 3, show_spinner="3년치 투자자별 매매를 불러오는 중… (처음엔 10~20초 걸려요)")
def flows_long(market: str):
    return dt.load_investor_flows(market, days=750)


@st.cache_data(ttl=3600, show_spinner="상승·하락 종목 수를 세는 중… (처음엔 30초 정도 걸려요)")
def kr_breadth(market: str):
    return dt.load_kr_breadth(market)


@st.cache_data(ttl=CACHE_TTL, show_spinner="거래대금을 불러오는 중…")
def kr_index(name: str):
    return dt.load_kr_index(name)


@st.cache_data(ttl=CACHE_TTL, show_spinner="업종 등락을 불러오는 중…")
def kr_sectors(days: int):
    return dt.load_kr_sectors(days)


@st.cache_data(ttl=3600 * 6, show_spinner="PER·PBR을 불러오는 중…")
def kr_fundamental(name: str):
    return dt.load_kr_fundamental(name)


@st.cache_data(ttl=CACHE_TTL, show_spinner="VKOSPI를 불러오는 중…")
def vkospi():
    return dt.load_vkospi()


@st.cache_data(ttl=CACHE_TTL)
def score_bundle(t: str, p: str):
    """(요인 목록 → 직렬화 어려워서) 점수 시계열과 요인별 최신 정보."""
    pr = _prices(p)[0]
    facs = an.build_factors(pr, t)
    sc = an.flow_score(facs)
    last = len(pr) - 1
    rows = []
    for f in facs:
        v = f.series.iloc[last]
        sig = 0.0 if pd.isna(v) else float(v)
        rows.append({"요인": f.label, "기여": sig * f.weight, "설명": f.explain(last)})
    return sc, pd.DataFrame(rows)


# ── 표시 도우미 ──────────────────────────────────────────
def warn_if_sample(note: str):
    if "샘플" in note:
        st.warning(note)


def source(note: str):
    st.caption(f"출처: {note}")


def fmt_change(v: float, unit: str = "%") -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:+.2f}{unit}"


def layout(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=36, b=8),
                      legend=dict(orientation="h", y=-0.18, x=0), hovermode="x unified")
    return fig


def show(fig: go.Figure, height: int = 360):
    st.plotly_chart(layout(fig, height), use_container_width=True)


def hbar(labels, values, fmt="{:+.1f}", height=None, xrange=None) -> go.Figure:
    colors = [UP if v > 0 else DOWN if v < 0 else MUTED for v in values]
    fig = go.Figure(go.Bar(x=list(values), y=list(labels), orientation="h", marker_color=colors,
                           text=[fmt.format(v) for v in values], textposition="outside"))
    fig.update_layout(yaxis=dict(autorange="reversed"), hovermode=False)
    if xrange:
        fig.update_xaxes(range=xrange)
    fig.update_layout(height=height or (60 + 34 * len(labels)), margin=dict(l=10, r=50, t=36, b=10))
    return fig


def span_picker(key: str, default: str = "1년") -> int:
    label = st.radio("기간", list(SPAN), index=list(SPAN).index(default), horizontal=True, key=key)
    return SPAN[label]


def explain(text: str):
    """페이지 맨 위 '이 지표를 어떻게 읽나요' 안내."""
    with st.expander("이 지표는 어떻게 읽나요?", expanded=False):
        st.markdown(text)
