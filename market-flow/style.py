"""앱 전체 디자인: 깔끔한 금융앱 스타일(다크) + 휴대폰 맞춤 배치.

app.py에서 inject()를 한 번 부르면 모든 화면에 적용돼요.
- 글꼴: Pretendard (한글이 또렷한 무료 글꼴)
- 숫자 카드: 둥근 카드, 큰 숫자, 휴대폰에서는 한 줄에 2개씩
- 차트: 투명 배경, 옅은 격자, 범례는 아래, 오른쪽 위에 확대·축소·이동·초기화·저장 버튼
- 휴대폰(폭 640px 이하): 여백·제목 축소, 표 글자 축소, 탭·선택 버튼 가로 스크롤
"""
from __future__ import annotations

import streamlit as st

BG, CARD, CARD2, LINE = "#0B0F17", "#141A24", "#1B2330", "rgba(255,255,255,0.07)"
TEXT, SUB, ACCENT = "#E8ECF2", "#8B95A5", "#3B82F6"
FONT = "Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif"

CSS = f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');

html, body, .stApp, p, li, label, h1, h2, h3, h4, h5, h6, td, th, input, select, textarea,
[data-testid="stMarkdownContainer"], [data-testid="stMetricValue"], [data-testid="stMetricLabel"],
[data-testid="stMetricDelta"] div, [data-testid="stPageLink-NavLink"] p, summary p {{
  font-family: {FONT} !important;
}}
/* 아이콘(화살표 등)은 원래 아이콘 글꼴을 그대로 써야 그림으로 보여요 */
[data-testid="stIconMaterial"], span[class*="material-symbols"], .material-symbols-rounded,
[data-testid="stExpanderToggleIcon"], [data-testid="stSidebarCollapseButton"] span,
[data-testid="stExpandSidebarButton"] span, [data-testid="collapsedControl"] span {{
  font-family: "Material Symbols Rounded" !important;
}}
.stApp {{ background: {BG}; }}

/* ── 본문 여백 ───────────────────────── */
.block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1280px; }}
h1 {{ font-weight: 800 !important; letter-spacing: -0.02em; font-size: 1.9rem !important; }}
h2, h3 {{ font-weight: 700 !important; letter-spacing: -0.01em; }}
h3 {{ margin-top: 1.4rem !important; }}
[data-testid="stCaptionContainer"], .stCaption {{ color: {SUB} !important; }}
hr {{ border-color: {LINE} !important; }}

/* ── 숫자 카드 ───────────────────────── */
[data-testid="stMetric"] {{
  background: {CARD}; border: 1px solid {LINE}; border-radius: 16px;
  padding: 14px 16px 12px; height: 100%;
}}
[data-testid="stMetricLabel"] p {{ color: {SUB} !important; font-size: 0.82rem !important; font-weight: 500; }}
[data-testid="stMetricValue"] {{ font-size: 1.55rem !important; font-weight: 700; letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums; }}
[data-testid="stMetricDelta"] {{ font-size: 0.8rem !important; font-weight: 600; }}

/* ── 테두리 상자·펼침·알림을 카드처럼 ─────── */
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 18px !important; border-color: {LINE} !important;
  background: {CARD}; }}
[data-testid="stExpander"] details {{ border-radius: 14px !important; border-color: {LINE} !important; background: {CARD}; }}
[data-testid="stAlert"] {{ border-radius: 14px !important; }}

/* ── 차트: 카드 배경, 도구 막대 숨김 ─────── */
[data-testid="stPlotlyChart"] {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 16px; padding: 8px 6px 2px; }}
/* 차트 도구 막대: 확대·축소·이동·초기화 버튼을 오른쪽 위에 항상 표시 */
[data-testid="stPlotlyChart"] .modebar-container {{ top: 6px !important; right: 8px !important; }}
[data-testid="stPlotlyChart"] .modebar {{ display: flex !important; opacity: 0.92 !important; background: transparent !important; }}
[data-testid="stPlotlyChart"] .modebar-group {{ background: {CARD2} !important; border: 1px solid {LINE}; border-radius: 10px;
  padding: 2px 4px !important; margin-left: 4px; }}
[data-testid="stPlotlyChart"] .modebar-btn {{ padding: 4px 5px !important; }}
[data-testid="stPlotlyChart"] .modebar-btn path {{ fill: {SUB} !important; }}
[data-testid="stPlotlyChart"] .modebar-btn:hover path, [data-testid="stPlotlyChart"] .modebar-btn.active path {{ fill: {ACCENT} !important; }}

/* ── 표 ─────────────────────────────── */
[data-testid="stDataFrame"] {{ border-radius: 14px; overflow: hidden; border: 1px solid {LINE}; }}

/* ── 가로 선택 버튼을 알약 모양으로 ───────── */
[data-testid="stRadio"] div[role="radiogroup"] {{ gap: 6px; flex-wrap: wrap; }}
[data-testid="stRadio"] div[role="radiogroup"] > label {{
  background: {CARD2}; border: 1px solid {LINE}; border-radius: 999px; padding: 4px 12px; margin: 0 !important;
}}
[data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) {{
  background: {ACCENT}; border-color: {ACCENT};
}}
[data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) p {{ color: #fff !important; font-weight: 600; }}
[data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child {{ display: none; }}

/* ── 탭 ─────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; overflow-x: auto; scrollbar-width: none; }}
.stTabs [data-baseweb="tab"] {{ border-radius: 10px 10px 0 0; padding: 6px 12px; white-space: nowrap; }}

/* ── 사이드바 ────────────────────────── */
[data-testid="stSidebar"] {{ background: #0E131C; border-right: 1px solid {LINE}; }}
[data-testid="stSidebarNav"] a {{ border-radius: 10px; }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{ background: rgba(59,130,246,0.16); }}

/* ── 사이드바 메뉴 (화살표 펼침) ───────── */
[data-testid="stSidebar"] [data-testid="stExpander"] details {{ background: transparent; border: none !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {{ padding: 6px 8px; border-radius: 10px; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {{ background: rgba(255,255,255,0.04); }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary p {{ font-weight: 700; font-size: 0.95rem; }}
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] {{ padding: 0 0 4px 6px; }}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {{ border-radius: 10px; padding: 4px 8px; }}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"],
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:has(span[aria-current]) {{ background: rgba(59,130,246,0.18); }}
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {{ background: transparent; }}

/* ── 불필요한 기본 장식 숨기기 ─────────── */
footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ visibility: hidden; height: 0; }}
[data-testid="stToolbar"] [data-testid="stToolbarActions"] {{ display: none; }}

/* ══ 휴대폰 (폭 640px 이하) ═══════════════ */
@media (max-width: 640px) {{
  .block-container {{ padding: 3.2rem 0.75rem 3rem !important; }}
  h1 {{ font-size: 1.45rem !important; }}
  h2 {{ font-size: 1.2rem !important; }}
  h3 {{ font-size: 1.05rem !important; margin-top: 1rem !important; }}
  p, li {{ font-size: 0.93rem; }}

  /* 숫자 카드가 있는 줄은 2개씩 줄바꿈 */
  [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {{ flex-wrap: wrap !important; gap: 8px !important; }}
  [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"],
  [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="column"] {{
    flex: 1 1 calc(50% - 8px) !important; min-width: calc(50% - 8px) !important; width: calc(50% - 8px) !important;
  }}
  [data-testid="stMetric"] {{ padding: 10px 12px 8px; border-radius: 14px; }}
  [data-testid="stMetricValue"] {{ font-size: 1.2rem !important; }}
  [data-testid="stMetricLabel"] p {{ font-size: 0.74rem !important; }}
  [data-testid="stMetricDelta"] {{ font-size: 0.7rem !important; }}

  [data-testid="stPlotlyChart"] {{ padding: 4px 0 0; border-radius: 14px; }}
  [data-testid="stPlotlyChart"] .modebar-btn {{ padding: 6px 7px !important; }}
  [data-testid="stPlotlyChart"] .modebar-btn svg {{ width: 16px; height: 16px; }}
  [data-testid="stDataFrame"] {{ font-size: 0.78rem; }}
  [data-testid="stRadio"] div[role="radiogroup"] {{ flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; }}
  [data-testid="stRadio"] div[role="radiogroup"] > label {{ white-space: nowrap; padding: 4px 10px; }}
  [data-testid="stExpander"] summary p {{ font-size: 0.9rem; }}
}}
</style>
"""


# 모든 차트에 공통으로 붙는 도구 막대 설정
CHART_CONFIG = {
    "displayModeBar": True,          # 도구 막대 항상 보이기
    "displaylogo": False,
    "scrollZoom": False,             # 휴대폰에서 스크롤하다 실수로 확대되지 않게
    "doubleClick": "reset",          # 차트를 두 번 누르면 원래대로
    "modeBarButtons": [["zoom2d", "pan2d"], ["zoomIn2d", "zoomOut2d"], ["resetScale2d"], ["toImage"]],
    "toImageButtonOptions": {"format": "png", "filename": "mkflow_chart", "scale": 2},
}


def _patch_plotly_chart():
    """st.plotly_chart를 감싸서 모든 화면의 차트에 CHART_CONFIG를 자동으로 붙여요."""
    if getattr(st.plotly_chart, "_mkflow", False):
        return
    original = st.plotly_chart

    def plotly_chart(figure_or_data, *args, config=None, **kwargs):
        cfg = dict(CHART_CONFIG)
        if config:
            cfg.update(config)
        try:
            for ax in ("xaxis", "yaxis"):  # 범위를 직접 정한 축도 확대할 수 있게
                if getattr(figure_or_data.layout, ax, None) is not None and figure_or_data.layout[ax].fixedrange:
                    figure_or_data.layout[ax].fixedrange = False
        except Exception:
            pass
        return original(figure_or_data, *args, config=cfg, **kwargs)

    plotly_chart._mkflow = True
    st.plotly_chart = plotly_chart


def inject():
    st.markdown(CSS, unsafe_allow_html=True)
    _patch_plotly_chart()


def plotly_template():
    """모든 차트의 기본 모양: 투명 배경, Pretendard, 옅은 격자, 범례 아래."""
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except Exception:
        return
    try:
        _build(go, pio)
    except Exception:
        pass  # 차트 모양 설정에 실패해도 앱은 기본 모양으로 동작해요.


def _build(go, pio):
    t = go.layout.Template(pio.templates["plotly_dark"])
    t.layout.update(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=TEXT, size=12),
        colorway=["#3B82F6", "#F59E0B", "#22C55E", "#A78BFA", "#EF4444", "#14B8A6", "#EC4899", "#94A3B8"],
        legend=dict(orientation="h", y=-0.18, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        hoverlabel=dict(bgcolor=CARD2, bordercolor=LINE, font=dict(family=FONT, color=TEXT)),
        margin=dict(l=8, r=8, t=36, b=8),
    )
    for ax in ("xaxis", "yaxis"):
        t.layout[ax].update(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.12)",
                            linecolor="rgba(255,255,255,0.10)", tickfont=dict(color=SUB, size=11),
                            title=dict(font=dict(color=SUB, size=11)))
    pio.templates["mkflow"] = t
    pio.templates.default = "mkflow"
