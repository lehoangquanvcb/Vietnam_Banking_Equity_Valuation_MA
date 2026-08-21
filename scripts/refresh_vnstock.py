from pathlib import Path
from datetime import datetime
import json, re, sys, time, unicodedata, argparse, os
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
DATA.mkdir(exist_ok=True); RAW.mkdir(exist_ok=True)
BANKS = json.loads((ROOT / "config" / "banks.json").read_text(encoding="utf-8"))

VNSTOCK_IMPORT_ERROR=None
try:
    from vnstock_data import Fundamental, Market
except Exception as exc:
    Fundamental=Market=None
    VNSTOCK_IMPORT_ERROR=exc


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def norm(v):
    s = str(v if v is not None else "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^A-Za-z0-9]+", " ", s).lower().strip()


def flatten(df):
    if df is None:
        return pd.DataFrame()
    x = df.copy()
    try:
        if isinstance(x.index, pd.MultiIndex) or x.index.name is not None:
            x = x.reset_index()
    except Exception:
        x.index = pd.RangeIndex(len(x))
    if isinstance(x.columns, pd.MultiIndex):
        out=[]; seen={}
        for c in x.columns:
            parts=[str(z).strip() for z in c if str(z).strip() not in {"", "None", "nan"}]
            name=" | ".join(parts) if parts else "column"
            k=seen.get(name,0); seen[name]=k+1
            out.append(name if k==0 else f"{name}__{k}")
        x.columns=out
    else:
        x.columns=[str(c) for c in x.columns]
    return x


def find_col(df, aliases):
    wanted=[norm(a) for a in aliases]
    for c in df.columns:
        nc=norm(c)
        if any(nc==w or nc.endswith(" "+w) for w in wanted):
            return c
    for c in df.columns:
        nc=norm(c)
        if any(w and w in nc for w in wanted):
            return c
    return None


def call_safe(label, funcs):
    errs=[]
    for fn in funcs:
        try:
            df=fn()
            if df is not None and len(df):
                return df, f"{label}:OK"
            errs.append("EMPTY")
        except Exception as exc:
            errs.append(str(exc)[:160])
    return pd.DataFrame(), f"{label}:ERROR:" + " | ".join(errs)


def period_key(v):
    s=str(v).upper()
    y=re.search(r"(20\d{2})",s)
    q=re.search(r"Q([1-4])",s)
    return (int(y.group(1)) if y else 0, int(q.group(1)) if q else 0)


def latest_metric(df, ids=(), names=()):
    x=flatten(df)
    if x.empty: return np.nan
    idc=find_col(x,["id","code","metric_id"])
    nc=find_col(x,["name","metric","indicator","item","label"])
    vc=find_col(x,["value","metric_value","ratio_value"])
    pc=find_col(x,["period","report_period","quarter","year"])
    masks=[]
    if idc:
        s=x[idc].astype(str).str.upper()
        for a in ids:
            aa=str(a).upper(); masks.append(s.eq(aa)|s.str.contains(aa,regex=False,na=False))
    if nc:
        s=x[nc].astype(str).map(norm)
        for a in names:
            aa=norm(a); masks.append(s.str.contains(aa,regex=False,na=False))
    for m in masks:
        if not bool(m.any()): continue
        z=x.loc[m].copy()
        if pc:
            z["_pk"]=z[pc].map(period_key); z=z.sort_values("_pk")
        if vc:
            vals=pd.to_numeric(z[vc],errors="coerce").dropna()
            if len(vals): return float(vals.iloc[-1])
        # wide layout: choose latest period-like numeric column
        for _,r in z.iterrows():
            vals=[]
            for c in z.columns:
                if c in {idc,nc,pc,"_pk"}: continue
                v=pd.to_numeric(pd.Series([r[c]]),errors="coerce").dropna()
                if len(v): vals.append((period_key(c),float(v.iloc[0])))
            if vals:
                vals.sort(key=lambda q:q[0]); return vals[-1][1]
    return np.nan


def history_metric(df, ticker, metric_name, ids=(), names=()):
    x=flatten(df)
    if x.empty: return []
    idc=find_col(x,["id","code","metric_id"])
    nc=find_col(x,["name","metric","indicator","item","label"])
    vc=find_col(x,["value","metric_value","ratio_value"])
    pc=find_col(x,["period","report_period","quarter","year"])
    mask=pd.Series(False,index=x.index)
    if idc:
        s=x[idc].astype(str).str.upper()
        for a in ids:
            aa=str(a).upper(); mask |= s.eq(aa)|s.str.contains(aa,regex=False,na=False)
    if nc:
        s=x[nc].astype(str).map(norm)
        for a in names:
            mask |= s.str.contains(norm(a),regex=False,na=False)
    z=x.loc[mask].copy()
    rows=[]
    if z.empty: return rows
    if pc and vc:
        for _,r in z.iterrows():
            v=pd.to_numeric(pd.Series([r[vc]]),errors="coerce").iloc[0]
            if pd.notna(v): rows.append({"Ticker":ticker,"Period":str(r[pc]),"Metric":metric_name,"Value":float(v)})
    else:
        for _,r in z.iterrows():
            for c in z.columns:
                if period_key(c)[0] > 0:
                    v=pd.to_numeric(pd.Series([r[c]]),errors="coerce").iloc[0]
                    if pd.notna(v): rows.append({"Ticker":ticker,"Period":str(c),"Metric":metric_name,"Value":float(v)})
    return rows


METRICS = {
    "ROE": (["RT_ROE","RT_BANK_ROE"],["return on equity","roe"]),
    "ROA": (["RT_ROA","RT_BANK_ROA"],["return on assets","roa"]),
    "NIM": (["RT_BANK_NIM"],["net interest margin","nim"]),
    "NPL": (["RT_BANK_NPL"],["non performing loan","npl ratio","bad debt ratio"]),
    "CAR": (["RT_BANK_CAR"],["capital adequacy ratio","car"]),
    "CIR": (["RT_BANK_CIR"],["cost income ratio","cir"]),
    "LDR": (["RT_BANK_LDR"],["loan to deposit ratio","ldr"]),
    "CASA": (["RT_BANK_CASA"],["casa","current account savings","current account saving"]),
    "EPS": (["RT_EPS"],["earnings per share","eps"]),
    "BVPS": (["RT_BVPS"],["book value per share","bvps"]),
    "PB": (["RT_PB","RT_P_B"],["price to book","p b"]),
    "PE": (["RT_PE","RT_P_E"],["price earnings","p e"]),
}
BS_METRICS = {
    "TotalAssets": (["BS_TOTAL_ASSETS"],["total assets"]),
    "GrossLoans": (["BS_CUSTOMER_LOANS","BS_LOANS_TO_CUSTOMERS","BS_LOANS_AND_ADVANCES_TO_CUSTOMERS"],["loans to customers","customer loans","loans and advances to customers"]),
    "CustomerDeposits": (["BS_CUSTOMER_DEPOSITS"],["customer deposits","deposits from customers"]),
    "Equity": (["BS_TOTAL_EQUITY","BS_OWNERS_EQUITY"],["total equity","owners equity","shareholders equity"]),
    "IntangibleAssets": (["BS_INTANGIBLE_ASSETS"],["intangible assets"]),
}
IS_METRICS = {
    "NPAT": (["IS_NET_PROFIT_AFTER_TAX","IS_NET_PROFIT"],["net profit after tax","profit after tax","net income"]),
    "NetInterestIncome": (["IS_NET_INTEREST_INCOME"],["net interest income"]),
    "OperatingIncome": (["IS_TOTAL_OPERATING_INCOME","IS_OPERATING_INCOME"],["total operating income","operating income"]),
    "ProvisionExpense": (["IS_PROVISION_EXPENSE"],["provision expense","credit loss expense"]),
}


SNAPSHOT_BASE_COLUMNS = [
    "Ticker","RetrievedAt","DataType","SourceMode","ParserLog",
    "ROE","ROA","NIM","NPL","CAR","CIR","LDR","CASA","EPS","BVPS","PB","PE",
    "TotalAssets","GrossLoans","CustomerDeposits","Equity","IntangibleAssets","TangibleEquity",
    "NPAT","NetInterestIncome","OperatingIncome","ProvisionExpense"
]


def error_snapshot(ticker, message):
    """Return a schema-stable bank row when one bank's fundamental fetch fails."""
    row={c:np.nan for c in SNAPSHOT_BASE_COLUMNS}
    row.update({
        "Ticker":str(ticker).upper().strip(),
        "RetrievedAt":now(),
        "DataType":"ACTUAL_PARTIAL",
        "SourceMode":"VNSTOCK_BRONZE",
        "ParserLog":"FUNDAMENTAL_ERROR:"+str(message)[:450],
    })
    return row


def ensure_ticker_column(df, default_tickers=None):
    """Normalize ticker/symbol columns or index into canonical `Ticker` without raising."""
    if df is None:
        return pd.DataFrame(columns=["Ticker"])
    x=df.copy()
    if isinstance(x.index,pd.MultiIndex) or x.index.name is not None:
        try:x=x.reset_index()
        except Exception:pass
    if "Ticker" not in x.columns:
        alias=find_col(x,["ticker","symbol","code","stock_code","stock symbol"])
        if alias is not None:
            x=x.rename(columns={alias:"Ticker"})
    if "Ticker" not in x.columns:
        if default_tickers is not None and len(x)==len(default_tickers):
            x["Ticker"]=[str(v).upper().strip() for v in default_tickers]
        else:
            x["Ticker"]=pd.Series(dtype="object") if len(x)==0 else np.nan
    x["Ticker"]=x["Ticker"].astype(str).str.upper().str.strip()
    x.loc[x["Ticker"].isin(["NAN","NONE","<NA>",""]),"Ticker"]=np.nan
    return x


def fetch_one(ticker):
    eq=Fundamental().equity(ticker)
    health,s1=call_safe("health",[
        lambda:eq.financial_health(scorecard="banking",lang="en",limit=20),
        lambda:eq.financial_health(scorecard="bank",lang="en",limit=20),
    ])
    ratio_q,s2=call_safe("ratio_q",[
        lambda:eq.ratio(period="quarter",lang="en",scorecard="banking"),
        lambda:eq.ratio(period="quarter",lang="en"),
        lambda:eq.ratio(period="quarter"),
    ])
    bs_q,s3=call_safe("bs_q",[
        lambda:eq.balance_sheet(period="quarter",lang="en",scorecard="banking"),
        lambda:eq.balance_sheet(period="quarter",lang="en"),
        lambda:eq.balance_sheet(period="quarter"),
    ])
    is_q,s4=call_safe("is_q",[
        lambda:eq.income_statement(period="quarter",lang="en",scorecard="banking"),
        lambda:eq.income_statement(period="quarter",lang="en"),
        lambda:eq.income_statement(period="quarter"),
    ])
    ratio_y,s5=call_safe("ratio_y",[
        lambda:eq.ratio(period="year",lang="en",scorecard="banking"),
        lambda:eq.ratio(period="year",lang="en"),
        lambda:eq.ratio(period="year"),
    ])
    for name,df in [("health",health),("ratio_q",ratio_q),("balance_q",bs_q),("income_q",is_q),("ratio_y",ratio_y)]:
        if len(df):
            try: flatten(df).to_csv(RAW/f"{ticker}_{name}.csv",index=False,encoding="utf-8-sig")
            except Exception: pass

    snap={"Ticker":ticker,"RetrievedAt":now(),"DataType":"ACTUAL","SourceMode":"VNSTOCK_BRONZE",
          "ParserLog":" || ".join([s1,s2,s3,s4,s5])}
    for m,(ids,names) in METRICS.items():
        v=latest_metric(health,ids,names)
        if pd.isna(v): v=latest_metric(ratio_q,ids,names)
        snap[m]=v
    for m,(ids,names) in BS_METRICS.items(): snap[m]=latest_metric(bs_q,ids,names)
    for m,(ids,names) in IS_METRICS.items(): snap[m]=latest_metric(is_q,ids,names)

    # Normalize ratio percentages if returned in percent units.
    for m in ["ROE","ROA","NIM","NPL","CAR","CIR","LDR","CASA"]:
        v=snap.get(m)
        if pd.notna(v) and abs(v)>1.5 and abs(v)<=100: snap[m]=v/100.0

    # Derive BVPS/EPS only when direct ratios are absent and units appear coherent.
    if pd.isna(snap.get("BVPS")) and pd.notna(snap.get("Equity")) and pd.notna(snap.get("NPAT")) and pd.notna(snap.get("EPS")) and snap["EPS"]!=0:
        shares=snap["NPAT"]/snap["EPS"]
        if shares>0: snap["BVPS"]=snap["Equity"]/shares
    snap["TangibleEquity"] = snap.get("Equity") - snap.get("IntangibleAssets") if pd.notna(snap.get("Equity")) and pd.notna(snap.get("IntangibleAssets")) else snap.get("Equity")

    hist=[]
    for m,(ids,names) in METRICS.items(): hist += history_metric(ratio_q,ticker,m,ids,names)
    for m,(ids,names) in BS_METRICS.items(): hist += history_metric(bs_q,ticker,m,ids,names)
    for m,(ids,names) in IS_METRICS.items(): hist += history_metric(is_q,ticker,m,ids,names)
    return snap,hist


def fetch_price(ticker, start_date="2021-01-01"):
    try:
        m=Market().equity(ticker)
        df=m.ohlcv(start=start_date,end=datetime.now().strftime("%Y-%m-%d"),interval="1D")
        x=flatten(df)
        if len(x): x.to_csv(RAW/f"{ticker}_ohlcv.csv",index=False,encoding="utf-8-sig")
        dc=find_col(x,["time","date","datetime"]); cc=find_col(x,["close","close_price","price"])
        if dc is None or cc is None: return pd.DataFrame(),np.nan,"SCHEMA_NOT_FOUND"
        y=pd.DataFrame({"Ticker":ticker,"Date":pd.to_datetime(x[dc],errors="coerce"),"Close":pd.to_numeric(x[cc],errors="coerce")}).dropna()
        y=y.sort_values("Date").drop_duplicates("Date",keep="last")
        return y,float(y.Close.iloc[-1]) if len(y) else np.nan,"OK"
    except Exception as exc:
        return pd.DataFrame(),np.nan,str(exc)[:180]


def read_existing_csv(path, columns=None):
    try:
        x=pd.read_csv(path)
    except Exception:
        x=pd.DataFrame(columns=columns or [])
    if columns:
        for c in columns:
            if c not in x.columns:x[c]=np.nan
    return x


def merge_history(old,new):
    cols=["Ticker","Period","Metric","Value"]
    old=old.copy() if old is not None else pd.DataFrame(columns=cols)
    new=new.copy() if new is not None else pd.DataFrame(columns=cols)
    for x in (old,new):
        for c in cols:
            if c not in x.columns:x[c]=np.nan
    z=pd.concat([old[cols],new[cols]],ignore_index=True)
    z["Ticker"]=z["Ticker"].astype(str).str.upper().str.strip()
    z=z.dropna(subset=["Ticker","Period","Metric"])
    return z.drop_duplicates(["Ticker","Period","Metric"],keep="last")


def merge_snapshot(old,new, target_tickers=None):
    old=ensure_ticker_column(old)
    new=ensure_ticker_column(new)
    if target_tickers:
        target={str(t).upper().strip() for t in target_tickers}
        old=old[~old["Ticker"].isin(target)]
    z=pd.concat([old,new],ignore_index=True,sort=False)
    z=ensure_ticker_column(z)
    return z.dropna(subset=["Ticker"]).drop_duplicates("Ticker",keep="last")


def market_incremental_start(existing_price,ticker,full_history=False):
    if full_history or existing_price is None or existing_price.empty:
        return "2021-01-01"
    q=existing_price[existing_price["Ticker"].astype(str).str.upper().eq(str(ticker).upper())].copy()
    if q.empty:return "2021-01-01"
    d=pd.to_datetime(q.get("Date"),errors="coerce").max()
    if pd.isna(d):return "2021-01-01"
    # overlap a few calendar days so corporate-action/source corrections can replace recent observations.
    return (d-pd.Timedelta(days=7)).strftime("%Y-%m-%d")


def parse_args():
    ap=argparse.ArgumentParser(description="Vnstock Bronze incremental refresh")
    ap.add_argument("--mode",choices=["full","fundamentals","prices"],default="full")
    ap.add_argument("--tickers",default="",help="Comma-separated tickers; blank = full bank universe")
    ap.add_argument("--workers",type=int,default=int(os.getenv("VNSTOCK_WORKERS","4")))
    ap.add_argument("--full-price-history",action="store_true",help="Reload market history from 2021 instead of incremental append")
    return ap.parse_args()


def main():
    args=parse_args()
    if VNSTOCK_IMPORT_ERROR is not None:
        print(f"ERROR: vnstock_data unavailable: {VNSTOCK_IMPORT_ERROR!r}")
        print("Hay chay BAT refresh trong Bronze venv; RUN_FAST.bat khong can vnstock_data.")
        raise SystemExit(2)
    selected=[x.strip().upper() for x in args.tickers.split(",") if x.strip()] or [str(x).upper().strip() for x in BANKS]
    unknown=[x for x in selected if x not in {str(b).upper().strip() for b in BANKS}]
    if unknown:
        print("WARNING: ticker outside configured universe:",", ".join(unknown))
    workers=max(1,min(int(args.workers),6))
    print(f"REFRESH MODE: {args.mode} | BANKS: {len(selected)} | WORKERS: {workers}")

    old_snap=read_existing_csv(DATA/"bank_snapshot.csv",SNAPSHOT_BASE_COLUMNS+["Price"])
    old_hist=read_existing_csv(DATA/"bank_history_long.csv",["Ticker","Period","Metric","Value"])
    old_price=read_existing_csv(DATA/"price_history.csv",["Ticker","Date","Close"])
    old_log=read_existing_csv(DATA/"refresh_log.csv",["Dataset","Status","Message","RetrievedAt"])
    old_price=ensure_ticker_column(old_price)
    if "Date" in old_price: old_price["Date"]=pd.to_datetime(old_price["Date"],errors="coerce")
    if "Close" in old_price: old_price["Close"]=pd.to_numeric(old_price["Close"],errors="coerce")

    snapshots=[]; histories=[]; new_prices=[]; log=[]

    if args.mode in ("full","fundamentals"):
        def fund_job(t):
            try:
                snap,hist=fetch_one(t); snap["Ticker"]=t
                return t,snap,hist,"OK",str(snap.get("ParserLog",""))[:500]
            except Exception as exc:
                msg=f"{type(exc).__name__}: {exc}"
                return t,error_snapshot(t,msg),[],"ERROR",msg[:500]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures={ex.submit(fund_job,t):t for t in selected}
            done=0
            for fut in as_completed(futures):
                done+=1; t,snap,hist,status,msg=fut.result()
                print(f"[FUND {done}/{len(selected)}] {t}: {status}")
                snapshots.append(snap); histories.extend(hist or [])
                log.append([f"fundamental:{t}",status,msg,now()])
        new_snap=pd.DataFrame(snapshots)
        for c in SNAPSHOT_BASE_COLUMNS:
            if c not in new_snap.columns:new_snap[c]=np.nan
        new_snap=ensure_ticker_column(new_snap,selected)
        snap=merge_snapshot(old_snap,new_snap,selected)
        new_hist=pd.DataFrame(histories)
        hist_df=merge_history(old_hist,new_hist)
    else:
        snap=old_snap.copy(); hist_df=old_hist.copy()

    if args.mode in ("full","prices"):
        def price_job(t):
            start=market_incremental_start(old_price,t,args.full_price_history)
            ph,px,status=fetch_price(t,start)
            return t,ph,px,status,start
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures={ex.submit(price_job,t):t for t in selected}
            done=0
            for fut in as_completed(futures):
                done+=1; t,ph,px,status,start=fut.result()
                ok="OK" if len(ph) else "ERROR"
                print(f"[PRICE {done}/{len(selected)}] {t}: {ok} | from {start}")
                if len(ph):
                    ph=ensure_ticker_column(ph); ph["Ticker"]=t; new_prices.append(ph[["Ticker","Date","Close"]])
                log.append([f"price:{t}",ok,f"{status} | start={start}"[:500],now()])
        price_parts=[old_price[["Ticker","Date","Close"]]] if len(old_price) else []
        price_parts += new_prices
        if price_parts:
            price_hist=pd.concat(price_parts,ignore_index=True,sort=False)
            price_hist=ensure_ticker_column(price_hist)
            price_hist["Date"]=pd.to_datetime(price_hist["Date"],errors="coerce")
            price_hist["Close"]=pd.to_numeric(price_hist["Close"],errors="coerce")
            price_hist=price_hist.dropna(subset=["Ticker","Date","Close"]).sort_values(["Ticker","Date"]).drop_duplicates(["Ticker","Date"],keep="last")
        else:
            price_hist=pd.DataFrame(columns=["Ticker","Date","Close"])
    else:
        price_hist=old_price.copy()

    # Market price in snapshot always comes from accumulated price history.
    snap=ensure_ticker_column(snap)
    if "Price" in snap.columns:snap=snap.drop(columns=["Price"])
    if len(price_hist):
        latest=price_hist.sort_values(["Ticker","Date"]).groupby("Ticker",as_index=False).tail(1)[["Ticker","Close"]].rename(columns={"Close":"Price"})
        latest=ensure_ticker_column(latest).drop_duplicates("Ticker",keep="last")
        snap=snap.merge(latest,on="Ticker",how="left")
    else:
        snap["Price"]=np.nan

    # Stable output schemas and accumulated log.
    snap=snap.sort_values("Ticker").drop_duplicates("Ticker",keep="last")
    snap.to_csv(DATA/"bank_snapshot.csv",index=False,encoding="utf-8-sig")
    hist_df[["Ticker","Period","Metric","Value"]].to_csv(DATA/"bank_history_long.csv",index=False,encoding="utf-8-sig")
    price_hist[["Ticker","Date","Close"]].to_csv(DATA/"price_history.csv",index=False,encoding="utf-8-sig")
    new_log=pd.DataFrame(log,columns=["Dataset","Status","Message","RetrievedAt"])
    log_df=pd.concat([old_log,new_log],ignore_index=True,sort=False).tail(1500)
    log_df.to_csv(DATA/"refresh_log.csv",index=False,encoding="utf-8-sig")

    fund_rows=new_log[new_log.Dataset.astype(str).str.startswith("fundamental:")] if len(new_log) else pd.DataFrame()
    price_rows=new_log[new_log.Dataset.astype(str).str.startswith("price:")] if len(new_log) else pd.DataFrame()
    ok_fund=int((fund_rows.Status=="OK").sum()) if len(fund_rows) else 0
    ok_price=int((price_rows.Status=="OK").sum()) if len(price_rows) else 0
    print("\nREFRESH SUMMARY")
    if args.mode in ("full","fundamentals"):print(f"Fundamental OK: {ok_fund}/{len(selected)}")
    if args.mode in ("full","prices"):print(f"Price OK: {ok_price}/{len(selected)} (incremental)")
    print(f"Snapshot rows: {len(snap)} | History rows: {len(hist_df)} | Price rows: {len(price_hist)}")
    print("DONE")

if __name__=="__main__":
    main()
