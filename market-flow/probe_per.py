"""임시 점검: 지수 PER·PBR을 받을 수 있는 곳을 찾아 data/kr/probe.txt에 적어요."""
import json, re
from pathlib import Path
import requests
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
      "Referer": "https://m.stock.naver.com/"}
out = []
def probe(name, url, method="get", **kw):
    try:
        r = getattr(requests, method)(url, headers=UA, timeout=15, **kw)
        t = r.text
        hits = [m.start() for m in re.finditer(r"(?i)per|pbr|배당", t)][:5]
        snip = " || ".join(t[max(0, h - 80):h + 120].replace("\n", " ") for h in hits[:3])
        out.append(f"## {name} [{r.status_code}] len={len(t)}\n{t[:600]}\n-- hits: {snip}\n")
    except Exception as e:
        out.append(f"## {name} ERROR {e}\n")
N = "https://m.stock.naver.com/api"
probe("idx_integration", f"{N}/index/KOSPI/integration")
probe("idx_basic", f"{N}/index/KOSPI/basic")
probe("stock_integration", f"{N}/stock/005930/integration")
probe("marketValue", f"{N}/stocks/marketValue/KOSPI?page=1&pageSize=5")
probe("pc_sise_index", "https://finance.naver.com/sise/sise_index.naver?code=KOSPI")
probe("krx_idx_per", "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd", method="post",
      data={"bld": "dbms/MDC/STAT/standard/MDCSTAT00701", "searchType": "A", "idxIndMidclssCd": "02",
            "trdDd": "20261023", "csvxls_isNo": "false"})
probe("krx_idx_per_hist", "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd", method="post",
      data={"bld": "dbms/MDC/STAT/standard/MDCSTAT00702", "indIdx": "1", "indIdx2": "001",
            "strtDd": "20260901", "endDd": "20261023", "csvxls_isNo": "false"})
probe("fnguide_market", "https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?gicode=A005930")
probe("investing_kospi", "https://www.investing.com/indices/kospi-ratios")
Path(__file__).with_name("data").joinpath("kr", "probe.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out)[:3000])
