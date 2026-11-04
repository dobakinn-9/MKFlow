"""미국·세계 공식 통계를 받아 data/us/ 에 저장해요 (GitHub Actions가 매일 실행).

FRED(세인트루이스 연은)는 해외 클라우드 서버에서 접속이 막혀서, 각 기관에서 직접 받아요.
저장 형식: data/us/{키}.csv  (열: date, value, source) — 키는 앱이 쓰던 FRED 코드 그대로예요.

- 미 노동통계국(BLS) API  : UNRATE, PAYEMS, CPIAUCSL, CPILFESL
- 미 노동부(DOL)          : ICSA (주간 신규 실업수당 청구, 계절조정 전 전국 합계)
- 미 경제분석국(BEA)·연준 : PCEPILFE, INDPRO (DBnomics 거울)
- 미시간대               : UMCSENT, MICH
- 미 재무부              : T10YIE, T5YIE (명목 − 실질 국채금리), TGA_B (재무부 현금잔고)
- 연준·뉴욕 연은          : WALCL_B (연준 총자산), RRP_B (역레포)
- 인구조사국             : RSAFS, HOUST (가능할 때)
- OECD                  : CLI_USA, CLI_KOR, CLI_CHN, CLI_JPN, CLI_DEU, CLI_G7 (경기선행지수)
직접 실행:  cd market-flow && python fetch_us.py
"""
from __future__ import annotations

import io
import json
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

OUT = Path(__file__).parent / "data" / "us"
OUT.mkdir(parents=True, exist_ok=True)
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"})
DBN = "https://api.db.nomics.world/v22/series"
log: list[str] = []
THIS_YEAR = date.today().year


def say(m):
    print(m, flush=True)
    log.append(m)


def get(url, **kw):
    for k in range(3):
        try:
            r = S.get(url, timeout=60, **kw)
            if r.status_code == 200:
                return r
        except Exception:
            pass
        time.sleep(2 * (k + 1))
    return None


def save(key: str, s: pd.Series, source: str):
    s = pd.to_numeric(s, errors="coerce").dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    if s.empty:
        raise RuntimeError("빈 자료")
    f = OUT / f"{key}.csv"
    if f.exists():  # 예전 기록과 합쳐요 (새 값 우선)
        old = pd.read_csv(f, parse_dates=["date"]).set_index("date")["value"]
        s = pd.concat([old[~old.index.isin(s.index)], s]).sort_index()
    pd.DataFrame({"date": s.index.strftime("%Y-%m-%d"), "value": s.values, "source": source}).to_csv(f, index=False)
    say(f"  ✓ {key}: {len(s)}개 · {s.index.min():%Y-%m-%d} ~ {s.index.max():%Y-%m-%d} · 마지막 {s.iloc[-1]:,.3f} ({source})")


def dbn(code: str) -> pd.Series:
    r = get(f"{DBN}/{code}", params={"observations": 1})
    d = r.json()["series"]["docs"][0]
    return pd.Series(d["value"], index=pd.to_datetime(d["period_start_day"])).replace("NA", None)


def run(key, fn):
    try:
        fn()
    except Exception as e:
        say(f"  ✗ {key}: {type(e).__name__}: {str(e)[:150]}")


# ── BLS ─────────────────────────────────────────────────
BLS = {"UNRATE": "LNS14000000", "PAYEMS": "CES0000000001", "CPIAUCSL": "CUSR0000SA0", "CPILFESL": "CUSR0000SA0L1E"}


def bls():
    got = {k: {} for k in BLS}
    for y0 in (THIS_YEAR - 19, THIS_YEAR - 9):
        r = S.post("https://api.bls.gov/publicAPI/v1/timeseries/data/", timeout=60,
                   json={"seriesid": list(BLS.values()), "startyear": str(y0), "endyear": str(y0 + 9)})
        js = r.json()
        if js.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS 응답: {js.get('status')} {js.get('message')}")
        for ser in js["Results"]["series"]:
            key = next(k for k, v in BLS.items() if v == ser["seriesID"])
            for o in ser["data"]:
                if o["period"].startswith("M") and o["period"] != "M13":
                    got[key][pd.Timestamp(f"{o['year']}-{o['period'][1:]}-01")] = o["value"]
        time.sleep(1)
    for k, d in got.items():
        save(k, pd.Series(d), "미 노동통계국(BLS)")


# ── DOL 주간 실업수당 ─────────────────────────────────────
def icsa():
    r = get("https://oui.doleta.gov/unemploy/csv/ar539.csv")
    df = pd.read_csv(io.BytesIO(r.content), usecols=["st", "c2", "c3"], dtype={"c3": float})
    df["c2"] = pd.to_datetime(df["c2"], errors="coerce")
    s = df.dropna(subset=["c2"]).groupby("c2")["c3"].sum()
    s = s[s.index >= "2010-01-01"]
    s = s[s > 50000]  # 주 일부만 보고된 주는 빼요
    save("ICSA", s, "미 노동부(DOL) · 계절조정 전")


# ── BEA·연준 (DBnomics) ──────────────────────────────────
def pce():
    s = dbn("BEA/NIPA-T20804/DPCCRG-M")
    save("PCEPILFE", s, "미 경제분석국(BEA)")


def indpro():
    s = dbn("FED/G17_IP_MAJOR_INDUSTRY_GROUPS/IP.B50001.S")
    save("INDPRO", s, "연준 산업생산(G.17)")


# ── 미시간대 ─────────────────────────────────────────────
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                       "September", "October", "November", "December"], 1)}


def umich():
    for key, url, col in [("UMCSENT", "https://www.sca.isr.umich.edu/files/tbmics.csv", "ICS_ALL"),
                          ("MICH", "https://www.sca.isr.umich.edu/files/tbmpx1px5.csv", "PX_MD")]:
        df = pd.read_csv(io.StringIO(get(url).text))
        df = df[df["Month"].isin(MONTHS)]
        idx = [pd.Timestamp(int(y), MONTHS[m], 1) for m, y in zip(df["Month"], df["YYYY"])]
        save(key, pd.Series(df[col].values, index=idx), "미시간대 소비자조사")


# ── 재무부: 기대인플레이션, TGA ───────────────────────────
def treasury_breakeven():
    nom, real = [], []
    for y in range(THIS_YEAR - 9, THIS_YEAR + 1):
        base = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all"
        for typ, bag in (("daily_treasury_yield_curve", nom), ("daily_treasury_real_yield_curve", real)):
            r = get(base, params={"type": typ, "field_tdr_date_value": y, "page": "", "_format": "csv"})
            if r is not None and r.text.startswith("Date"):
                bag.append(pd.read_csv(io.StringIO(r.text), parse_dates=["Date"]).set_index("Date"))
            time.sleep(0.3)
    n, rl = pd.concat(nom).sort_index(), pd.concat(real).sort_index()
    for key, col in (("T10YIE", "10 YR"), ("T5YIE", "5 YR")):
        cn = next(c for c in n.columns if c.replace("Yr", "YR").upper() == col.upper().replace("YR", "YR"))
        be = (n[cn] - rl[col]).dropna()
        save(key, be, "미 재무부 (명목 − 물가연동 국채금리)")


def tga():
    rows, page = [], 1
    while page < 30:
        r = get("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance",
                params={"filter": "record_date:gte:2019-01-01", "fields": "record_date,account_type,close_today_bal,open_today_bal",
                        "page[size]": 10000, "page[number]": page, "sort": "record_date"})
        js = r.json()
        rows += js["data"]
        if page >= js["meta"]["total-pages"]:
            break
        page += 1
    df = pd.DataFrame(rows)
    df["v"] = pd.to_numeric(df["close_today_bal"].replace("null", None), errors="coerce")
    df["v"] = df["v"].fillna(pd.to_numeric(df["open_today_bal"].replace("null", None), errors="coerce"))
    tg = df[df["account_type"].str.contains("Treasury General Account|Federal Reserve Account", case=False, na=False)
            & ~df["account_type"].str.contains("Total", case=False, na=False)]
    # 같은 날 여러 줄이면 '마감(Closing)' 줄을 먼저 써요
    tg = tg.assign(closing=tg["account_type"].str.contains("Closing", case=False)).sort_values(["record_date", "closing"])
    s = tg.groupby("record_date")["v"].last() / 1000  # 백만 달러 → 10억 달러
    s.index = pd.to_datetime(s.index)
    save("TGA_B", s, "미 재무부 일일 국고 보고서(TGA)")


# ── 연준 총자산 · 역레포 ─────────────────────────────────
def walcl():
    tried = []
    for code in ["FED/H41/RESPPA_N.WW", "FED/H41/RESPPMA_N.WW", "FED/H41/RESPPT_N.WW"]:
        try:
            s = dbn(code)
            tried.append(f"{code}→{s.index.max():%Y-%m-%d}")
            if s.index.max() > pd.Timestamp.today() - pd.Timedelta(days=21):
                save("WALCL_B", pd.to_numeric(s, errors="coerce") / 1000, "연준 H.4.1 총자산")
                return
        except Exception as e:
            tried.append(f"{code}→{type(e).__name__}")
    # 검색으로 후보를 찾아 기록 (다음 수정용)
    r = get(f"{DBN}/FED/H41", params={"q": "Total assets Wednesday level", "limit": 10, "observations": 0})
    cands = []
    try:
        cands = [f"{d['series_code']}={d.get('series_name', '')[:70]}" for d in r.json()["series"]["docs"]]
    except Exception:
        pass
    raise RuntimeError("최신 총자산 시리즈를 못 찾음: " + "; ".join(tried) + " | 후보: " + " | ".join(cands))


def rrp():
    r = get("https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json",
            params={"startDate": "2019-01-01", "endDate": date.today().isoformat()})
    ops = r.json()["repo"]["operations"]
    df = pd.DataFrame(ops)
    df["d"] = pd.to_datetime(df["operationDate"])
    s = df.groupby("d")["totalAmtAccepted"].sum() / 1e9  # 달러 → 10억 달러
    save("RRP_B", s, "뉴욕 연은 역레포(ON RRP)")


# ── 인구조사국 (가능할 때) ───────────────────────────────
def census():
    for key, prog, cat, dtp in [("RSAFS", "MARTS", "44X72", "SM"), ("HOUST", "RESCONST", "APSTARTS", "TOTAL")]:
        try:
            r = get("https://www.census.gov/econ/currentdata/export/csv",
                    params={"programCode": prog, "timeSlotType": 12, "startYear": THIS_YEAR - 10, "endYear": THIS_YEAR,
                            "categories[]": cat, "dataType": dtp, "geoLevel": "US", "adjusted": 1, "notAdjusted": 0,
                            "errorData": 0})
            txt = r.text if r is not None else ""
            lines = txt.splitlines()
            start = next(i for i, l in enumerate(lines) if l.startswith("Period"))
            df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
            idx = pd.to_datetime(df["Period"], format="%b-%Y", errors="coerce")
            s = pd.Series(pd.to_numeric(df["Value"].astype(str).str.replace(",", ""), errors="coerce").values, index=idx).dropna()
            save(key, s, "미 인구조사국")
        except Exception as e:
            say(f"  ✗ {key}: {type(e).__name__}: {str(e)[:120]}")


# ── OECD 경기선행지수 ────────────────────────────────────
CLI = ["USA", "KOR", "CHN", "JPN", "DEU", "G7"]


def oecd_cli():
    got = {}
    r = get("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,/" + "+".join(CLI) + ".M.LI...AA...H",
            params={"startPeriod": "2005-01", "format": "csvfile"})
    if r is not None and "REF_AREA" in r.text[:500]:
        df = pd.read_csv(io.StringIO(r.text))
        for c, g in df.groupby("REF_AREA"):
            got[c] = (pd.Series(g["OBS_VALUE"].values, index=pd.to_datetime(g["TIME_PERIOD"])), "OECD 경기선행지수")
    for c in CLI:
        try:
            s = dbn(f"OECD/DSD_STES@DF_CLI/{c}.M.LI...AA...H")
            s = pd.to_numeric(s, errors="coerce").dropna()
            s = s[s.index >= "2005-01-01"]
            if c not in got or s.index.max() > got[c][0].index.max():
                got[c] = (s, "OECD 경기선행지수 (DBnomics)")
        except Exception:
            pass
    for c in CLI:
        if c in got:
            save(f"CLI_{c}", got[c][0], got[c][1])
        else:
            say(f"  ✗ CLI_{c}: 받지 못함")


def wti():
    r = get("https://api.eia.gov/v2/seriesid/PET.RWTC.D", params={"api_key": "DEMO_KEY"})
    js = r.json()["response"]["data"]
    s = pd.Series({pd.Timestamp(x["period"]): x["value"] for x in js})
    save("DCOILWTICO", s, "미 에너지정보청(EIA)")


def main():
    say(f"미국·세계 공식 통계 받기 ({date.today()})")
    for key, fn in [("BLS", bls), ("ICSA", icsa), ("PCEPILFE", pce), ("INDPRO", indpro), ("미시간대", umich),
                    ("기대인플레이션", treasury_breakeven), ("TGA", tga), ("WALCL", walcl), ("RRP", rrp),
                    ("인구조사국", census), ("CLI", oecd_cli), ("WTI", wti)]:
        run(key, fn)
    (OUT / "status.txt").write_text("\n".join(log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
