"""임시 점검: FRED 시리즈별 마지막 날짜를 data/probe_fred.txt에 적어요."""
import io
from pathlib import Path
import pandas as pd, requests
IDS = ["WALCL", "WTREGEN", "RRPONTSYD", "T10Y3M", "USALOLITOAASTSAM", "USALOLITONOSTSAM", "KORLOLITOAASTSAM",
       "KORLOLITONOSTSAM", "XTEXVA01KRM667S", "KORPROINDMISMEI", "BSCICP03KRM665S", "CSCICP03KRM665S",
       "BSCICP03USM665S", "INDPRO", "PAYEMS", "RSAFS", "UNRATE", "ICSA", "HOUST", "UMCSENT", "PERMIT", "AWHMAN",
       "NEWORDER", "CFNAI", "BAMLH0A0HYM2", "DTWEXBGS", "KORCPIALLMINMEI", "IRLTLT01KRM156N"]
out = []
for i in IDS:
    try:
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={i}", timeout=20,
                         headers={"User-Agent": "Mozilla/5.0 mkflow"})
        df = pd.read_csv(io.StringIO(r.text))
        df = df[pd.to_numeric(df.iloc[:, 1], errors="coerce").notna()]
        out.append(f"{i}: [{r.status_code}] {len(df)}행 {df.iloc[0,0]} ~ {df.iloc[-1,0]} 마지막값 {df.iloc[-1,1]}")
    except Exception as e:
        out.append(f"{i}: ERROR {type(e).__name__} {str(e)[:80]}")
Path(__file__).with_name("data").joinpath("probe_fred.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
