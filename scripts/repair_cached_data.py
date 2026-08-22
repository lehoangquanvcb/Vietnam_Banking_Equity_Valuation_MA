from pathlib import Path
import json
import numpy as np
import pandas as pd

try:
    from scripts.refresh_vnstock import (
        ROOT, DATA, BANKS, RATIO_METRICS, load_raw_bank, clean_ratio_value,
        ensure_ticker_column, derive_per_share_from_market_multiples, now
    )
except Exception:
    from refresh_vnstock import (
        ROOT, DATA, BANKS, RATIO_METRICS, load_raw_bank, clean_ratio_value,
        ensure_ticker_column, derive_per_share_from_market_multiples, now
    )

SNAP=DATA/'bank_snapshot.csv'
HIST=DATA/'bank_history_long.csv'


def read_csv(path):
    try:return pd.read_csv(path)
    except Exception:return pd.DataFrame()


def main():
    old_snap=ensure_ticker_column(read_csv(SNAP))
    old_hist=read_csv(HIST)
    rebuilt=[]; hist_rows=[]; rebuilt_tickers=[]
    for ticker in [str(x).upper().strip() for x in BANKS]:
        snap,hist=load_raw_bank(ticker)
        if snap is None:
            continue
        rebuilt.append(snap); hist_rows.extend(hist); rebuilt_tickers.append(ticker)

    if rebuilt:
        new_snap=pd.DataFrame(rebuilt)
        # Preserve the latest market price already stored locally; this repair never calls Vnstock.
        if 'Price' in old_snap.columns:
            px=old_snap[['Ticker','Price']].drop_duplicates('Ticker',keep='last')
            new_snap=new_snap.merge(px,on='Ticker',how='left')
        new_snap=derive_per_share_from_market_multiples(new_snap)
        untouched=old_snap[~old_snap['Ticker'].isin(rebuilt_tickers)].copy() if len(old_snap) else pd.DataFrame()
        out=pd.concat([untouched,new_snap],ignore_index=True,sort=False)
        out=ensure_ticker_column(out).drop_duplicates('Ticker',keep='last').sort_values('Ticker')
        # Final snapshot guardrail even for untouched banks.
        for m in RATIO_METRICS:
            if m in out.columns: out[m]=out[m].map(lambda v:clean_ratio_value(m,v))
        out.to_csv(SNAP,index=False,encoding='utf-8-sig')

    if hist_rows:
        new_hist=pd.DataFrame(hist_rows,columns=['Ticker','Period','Metric','Value'])
        new_hist['Ticker']=new_hist['Ticker'].astype(str).str.upper().str.strip()
        # Remove old ratio rows for rebuilt banks before appending. This is essential:
        # old CAR=0 placeholders and NPL-coverage collisions must disappear rather than survive de-duplication.
        if len(old_hist):
            keep=~(
                old_hist['Ticker'].astype(str).str.upper().isin(rebuilt_tickers)
                & old_hist['Metric'].astype(str).isin(set(RATIO_METRICS))
            )
            old_hist=old_hist.loc[keep].copy()
        out_hist=pd.concat([old_hist,new_hist],ignore_index=True,sort=False)
        out_hist=out_hist.dropna(subset=['Ticker','Period','Metric','Value'])
        out_hist=out_hist.drop_duplicates(['Ticker','Period','Metric'],keep='last')
        out_hist.to_csv(HIST,index=False,encoding='utf-8-sig')

    print(f'CACHE DATA QUALITY REPAIR: {len(rebuilt_tickers)}/{len(BANKS)} banks rebuilt from real raw Vnstock cache; no API call.')
    if rebuilt_tickers:
        print('Rebuilt:', ', '.join(rebuilt_tickers))

if __name__=='__main__':
    main()
