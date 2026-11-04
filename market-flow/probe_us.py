"""임시 점검 3: 미국 통계 시리즈 코드 찾기 → data/probe_us.txt"""
import json, time
from pathlib import Path
import requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}
D = "https://api.db.nomics.world/v22"
out = []
def g(url, n=600, **kw):
    try:
        r = requests.get(url, headers=H, timeout=40, **kw)
        return r.status_code, r.text
    except Exception as e:
        return -1, f"ERR {e}"
def series_search(ds, q, lim=6):
    c, t = g(f"{D}/series/{ds}", params={"q": q, "limit": lim, "observations": 0})
    try:
        docs = json.loads(t)["series"]["docs"]
        out.append(f"## {ds} q='{q}' [{c}] → " + " | ".join(f"{d['series_code']} = {d.get('series_name','')[:90]}" for d in docs))
    except Exception:
        out.append(f"## {ds} q='{q}' [{c}] {t[:200]}")
def last_obs(code):
    c, t = g(f"{D}/series/{code}", params={"observations": 1})
    try:
        d = json.loads(t)["series"]["docs"][0]
        out.append(f"## OBS {code} [{c}] {d['period'][0]}~{d['period'][-1]} last={d['value'][-1]} name={d.get('series_name','')[:80]}")
    except Exception:
        out.append(f"## OBS {code} [{c}] {t[:200]}")
c, t = g(f"{D}/providers")
try:
    out.append("## providers: " + ", ".join(p["code"] for p in json.loads(t)["providers"]["docs"]))
except Exception:
    out.append("## providers " + t[:300])
for prov in ["FED", "BEA", "CENSUS", "BLS"]:
    c, t = g(f"{D}/datasets/{prov}", params={"limit": 200})
    try:
        out.append(f"## datasets {prov}: " + " | ".join(f"{d['code']}={d.get('name','')[:40]}" for d in json.loads(t)["datasets"]["docs"]))
    except Exception:
        out.append(f"## datasets {prov} [{c}] {t[:200]}")
series_search("FED/H41", "total assets")
series_search("FED/G17", "total index")
series_search("BEA/NIPA-T20804", "excluding food and energy")
series_search("BLS/cu", "all items less food and energy seasonally adjusted")
for code in ["BLS/ln/LNS14000000", "BLS/ce/CES0000000001", "BLS/cu/CUSR0000SA0", "BLS/cu/CUSR0000SA0L1E",
             "OECD/DSD_STES@DF_CLI/USA.M.LI...AA...H", "OECD/DSD_STES@DF_CLI/KOR.M.LI...AA...H",
             "OECD/DSD_STES@DF_CLI/CHN.M.LI...AA...H", "OECD/DSD_STES@DF_CLI/JPN.M.LI...AA...H",
             "OECD/DSD_STES@DF_CLI/DEU.M.LI...AA...H", "OECD/DSD_STES@DF_CLI/G7.M.LI...AA...H"]:
    last_obs(code)
for nm, url in [("umich_sent", "https://www.sca.isr.umich.edu/files/tbcics.csv"),
                ("umich_mics", "https://www.sca.isr.umich.edu/files/tbmics.csv"),
                ("umich_px", "https://www.sca.isr.umich.edu/files/tbmpx1px5.csv"),
                ("dol_ar539", "https://oui.doleta.gov/unemploy/csv/ar539.csv"),
                ("treas_real", "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv"),
                ("treas_nom", "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv"),
                ("eia_wti", "https://api.eia.gov/series/?api_key=DEMO_KEY&series_id=PET.RWTC.D"),
                ("fiscal_tga", "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance?filter=record_date:gte:2026-10-25&page[size]=20")]:
    c, t = g(url)
    out.append(f"## {nm} [{c}] len={len(t)}\n{t[:500]}\n…{t[-300:]}")
Path(__file__).with_name("data").joinpath("probe_us.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out)[:3000])
