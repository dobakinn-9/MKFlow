"""종합: 오늘의 시장 / 흐름 점수·전망."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analysis as an
import common as cm
import data as dt
from config import KOREA, MACRO, SCORE_TARGETS, US, name


def _metric_row(prices: pd.DataFrame, tickers: list[str]):
    tbl = an.change_table(prices, tickers)
    if tbl.empty:
        return
    cols = st.columns(len(tbl))
    for col, (_, r) in zip(cols, tbl.iterrows()):
        rate = r["티커"] in an.RATE_TICKERS
        val = f"{r['현재']:.2f}" if rate or r["현재"] < 100 else f"{r['현재']:,.0f}" if r["현재"] > 10000 else f"{r['현재']:,.2f}"
        inverse = r["티커"] in ("^VIX", "^TNX", "^IRX", "KRW=X", "CL=F", "DX-Y.NYB")
        col.metric(r["지표"], val, cm.fmt_change(r["1일"], r["단위"]), delta_color="inverse" if inverse else "normal")


def today():
    p = cm.prices()
    cm.warn_if_sample(cm.price_note())
    st.title("오늘의 시장")
    st.caption(f"기준일 {p['^KS11'].dropna().index[-1].date()} · 데이터: {cm.price_note()}")

    from views import flowmap  # 오늘 바뀐 것 3줄
    flowmap.changes_card(p)
    from views import riskgauge
    riskgauge.mini(p)

    # 흐름 점수 두 시장
    cols = st.columns(len(SCORE_TARGETS))
    for col, (t, nm) in zip(cols, SCORE_TARGETS.items()):
        sc, _ = cm.score_bundle(t, cm.period())
        now = float(sc.dropna().iloc[-1])
        prev = float(sc.dropna().iloc[-6]) if len(sc.dropna()) > 6 else now
        col.metric(f"{nm} 흐름 점수", f"{now:+.1f} · {an.regime(now)}", f"{now - prev:+.1f} (1주 전 대비)")
    st.caption("흐름 점수: 추세·모멘텀·변동성·금리·유가·환율·반도체를 합친 −10(강한 약세) ~ +10(강한 강세). 자세한 내용은 '흐름 점수·전망' 메뉴.")

    # 아침 5분 체크리스트
    st.subheader("아침 5분 체크")
    tbl = an.change_table(p, ["^GSPC", "^IXIC", "^SOX", "^TNX", "KRW=X", "^VIX"]).set_index("티커")

    def g(t, col="1일"):
        return tbl.loc[t, col] if t in tbl.index else float("nan")

    def judge(good: bool | None) -> str:
        return "🟢 우호적" if good is True else "🔴 부담" if good is False else "⚪ 중립"

    vix = tbl.loc["^VIX", "현재"] if "^VIX" in tbl.index else float("nan")
    rows = [
        ("1. 간밤 미국 증시", f"S&P {cm.fmt_change(g('^GSPC'))} · 나스닥 {cm.fmt_change(g('^IXIC'))}",
         judge(None if abs(g("^GSPC")) < 0.3 else g("^GSPC") > 0)),
        ("2. 미국 반도체 (SOX)", cm.fmt_change(g("^SOX")), judge(None if abs(g("^SOX")) < 0.5 else g("^SOX") > 0)),
        ("3. 미 10년물 금리", f"{tbl.loc['^TNX', '현재']:.2f}% ({cm.fmt_change(g('^TNX'), '%p')})" if "^TNX" in tbl.index else "—",
         judge(None if abs(g("^TNX")) < 0.05 else g("^TNX") < 0)),
        ("4. 원/달러 환율", f"{tbl.loc['KRW=X', '현재']:,.1f}원 ({cm.fmt_change(g('KRW=X'))})" if "KRW=X" in tbl.index else "—",
         judge(None if abs(g("KRW=X")) < 0.3 else g("KRW=X") < 0)),
        ("5. 공포 지수 (VIX)", f"{vix:.1f}", judge(None if 15 <= vix <= 22 else vix < 15)),
    ]
    ev, _ = dt.load_events()
    if ev is not None:
        soon = ev[(ev["date"] >= pd.Timestamp.today().normalize()) & (ev["date"] <= pd.Timestamp.today().normalize() + pd.Timedelta(days=7))]
        rows.append(("6. 7일 안 주요 일정", " · ".join(soon["title"]) if len(soon) else "없음",
                     "🟠 주의" if (soon["importance"] == "상").any() else "⚪ 중립"))
    st.dataframe(pd.DataFrame(rows, columns=["확인 항목", "현재", "판단"]), hide_index=True, use_container_width=True)

    for title, group in [("한국", KOREA), ("미국", US), ("금리·환율·유가·변동성", MACRO)]:
        st.subheader(title)
        _metric_row(p, group)
    st.caption("VIX·금리·환율·유가·달러는 오르면 주식에 부담이라 색을 반대로 표시해요.")


def score():
    p = cm.prices()
    t, nm, fwd = cm.target(), cm.target_name(), cm.fwd()
    cm.warn_if_sample(cm.price_note())
    st.title(f"{nm} 흐름 점수·전망")
    cm.explain("""
- **흐름 점수**는 추세, 평균선 배열, 한 달 모멘텀, RSI, VIX, 미국 금리, 유가, 환율(또는 달러), 반도체 업황을 각각 +/− 신호로 바꿔 가중 합산한 값이에요. −10(강한 약세) ~ +10(강한 강세).
- **전망**은 과거에 지금과 비슷한 점수(±2점)였던 날들의 *N거래일 뒤 수익률* 통계예요. 미래 예측이 아니라 '과거엔 이랬다'는 참고치예요.
- 사이드바에서 분석할 시장과 전망 기간을 바꿀 수 있어요.
""")
    sc, fdf = cm.score_bundle(t, cm.period())
    now = float(sc.dropna().iloc[-1])
    ol = an.outlook(p[t], sc, fwd)
    sim = ol["similar"]

    a, b = st.columns(2)
    a.metric("흐름 점수", f"{now:+.1f}")
    b.metric("국면", an.regime(now))

    st.subheader("요인별 진단")
    st.plotly_chart(cm.hbar(fdf["요인"], fdf["기여"]), use_container_width=True)
    for _, r in fdf.iterrows():
        st.markdown(f"- **{r['요인']}**: {r['설명']}")

    st.subheader("흐름 점수 추이 (최근 1년)")
    hist = pd.DataFrame({"점수": sc, nm: p[t]}).dropna().tail(250)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=hist[nm], name=nm, line=dict(color=cm.BLUE, width=2)))
    fig.add_trace(go.Bar(x=hist.index, y=hist["점수"], name="흐름 점수", yaxis="y2",
                         marker_color=[cm.UP if v > 0 else cm.DOWN for v in hist["점수"]], opacity=0.35))
    fig.update_layout(yaxis=dict(title=nm), yaxis2=dict(title="점수", overlaying="y", side="right", range=[-10, 10]))
    cm.show(fig, 380)

    st.subheader(f"전망: 비슷한 국면 이후 {fwd}거래일 수익률")
    if sim.get("n", 0) >= 20:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("평균", f"{sim['mean']:+.1f}%", f"전체 평균 {ol['base']['mean']:+.1f}%", delta_color="off")
        c2.metric("중간값", f"{sim['median']:+.1f}%")
        c3.metric("오를 확률", f"{sim['up']:.0f}%", f"전체 {ol['base']['up']:.0f}%", delta_color="off")
        c4.metric("범위 (하위~상위 10%)", f"{sim['p10']:+.1f}% ~ {sim['p90']:+.1f}%")
        fig3 = px.histogram(ol["dist"], nbins=40, labels={"value": f"{fwd}거래일 뒤 수익률 (%)"})
        fig3.add_vline(x=0, line_dash="dash", line_color=cm.MUTED)
        fig3.update_layout(showlegend=False, yaxis_title="일수", hovermode=False)
        cm.show(fig3, 280)
        st.caption(f"과거 {sim['n']:,}일의 사례를 바탕으로 했어요.")
    else:
        st.info("비슷한 점수의 과거 사례가 20일 미만이에요. 사이드바에서 불러올 기간을 늘려 보세요.")

    with st.expander("이 점수가 과거에 실제로 맞았나요? (검증)"):
        st.dataframe(an.score_buckets(p[t], sc, fwd), hide_index=True, use_container_width=True,
                     column_config={"평균 수익률(%)": st.column_config.NumberColumn(format="%+.2f"),
                                    "상승 확률(%)": st.column_config.NumberColumn(format="%.0f")})
        st.caption("점수가 높은 구간일수록 이후 수익률·상승 확률이 높다면 점수에 의미가 있다는 뜻이에요.")
