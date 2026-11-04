"""임시 점검: 미국·한국 공식 통계를 받을 수 있는 곳을 찾아 data/probe_fred.txt에 적어요."""
import time
from pathlib import Path
import requests
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
     "Accept": "text/csv,text/html,application/json,*/*"}
out = []
def p(name, url, **kw):
    t = time.time()
    try:
        r = requests.get(url, headers=B, timeout=40, **kw)
        txt = r.text
        out.append(f"## {name} [{r.status_code}] {time.time()-t:.1f}s len={len(txt)}\n{txt[:250]}\n...{txt[-250:]}\n")
    except Exception as e:
        out.append(f"## {name} ERROR {type(e).__name__} {time.time()-t:.1f}s {str(e)[:100]}\n")
p("fred_csv_browserUA", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=WALCL")
p("fred_csv_cosd", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=UNRATE&cosd=2020-01-01")
p("fred_series_page", "https://fred.stlouisfed.org/series/UNRATE")
p("alfred", "https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=UNRATE")
p("dbnomics_bls_unrate", "https://api.db.nomics.world/v22/series/BLS/ln/LNS14000000?observations=1&format=json")
p("dbnomics_oecd_cli_usa", "https://api.db.nomics.world/v22/series/OECD/DSD_STES@DF_CLI/USA.M.LI...AA...H?observations=1")
p("oecd_sdmx_cli", "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,/USA+KOR.M.LI...AA...H?startPeriod=2024-01&format=csvfilewithlabels")
p("fiscaldata_tga", "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance?sort=-record_date&page[size]=3")
p("nyfed_rrp", "https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json?startDate=2026-10-20")
p("fed_h41_ddp", "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H41&series=c5d2a5b6b2d6d1c7a6b6d1a3e2a0b7d1&lastobs=5&from=&to=&filetype=csv&label=include&layout=seriescolumn")
p("bls_api_v1", "https://api.bls.gov/publicAPI/v1/timeseries/data/LNS14000000")
p("census_marts", "https://api.census.gov/data/timeseries/eits/marts?get=cell_value,time_slot_id&category_code=44X72&data_type_code=SM&time=from+2025")
Path(__file__).with_name("data").joinpath("probe_fred.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out)[:4000])
