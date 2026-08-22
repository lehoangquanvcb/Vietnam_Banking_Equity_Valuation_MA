from __future__ import annotations
from pathlib import Path
import re
import numpy as np
import pandas as pd

RATIO_METRICS={"ROE","ROA","NIM","NPL","CAR","CIR","LDR","CASA","PB","PE"}
BENCHMARK_LABEL="Bình quân 20 ngân hàng niêm yết"

def _csv(path):
    try:return pd.read_csv(path)
    except Exception:return pd.DataFrame()

def period_date(value):
    s=str(value).upper().strip()
    y=re.search(r"(20\d{2})",s); q=re.search(r"Q\s*([1-4])",s)
    if not y:return pd.NaT
    yy=int(y.group(1))
    if q:return pd.Timestamp(yy,(int(q.group(1))-1)*3+1,1)
    return pd.Timestamp(yy,1,1)

def clean_metric(df,metric):
    x=df.copy()
    if x.empty:return x
    x['Value']=pd.to_numeric(x.get('Value'),errors='coerce')
    x=x.dropna(subset=['Value'])
    if metric in RATIO_METRICS:x=x[x.Value!=0]
    if metric=='CAR':x=x[x.Value.between(.02,.50)]
    if metric=='NPL':x=x[x.Value.between(0,.50)]
    if metric=='CASA':x=x[x.Value.between(0,1)]
    if metric=='LDR':x=x[x.Value.between(.05,2.5)]
    if metric=='CIR':x=x[x.Value.between(.01,2.0)]
    x['PeriodDate']=x['Period'].map(period_date)
    x=x.dropna(subset=['PeriodDate']).sort_values('PeriodDate')
    return x

def load_effective_history(root,base_df=None):
    root=Path(root)
    base=base_df.copy() if base_df is not None else _csv(root/'data/bank_history_long.csv')
    if base.empty:base=pd.DataFrame(columns=['Ticker','Period','Metric','Value'])
    for c in ['Ticker','Period','Metric','Value']:
        if c not in base.columns:base[c]=np.nan
    base=base[['Ticker','Period','Metric','Value']].copy()
    base['DataType']='ACTUAL_VNSTOCK'; base['Source']='Vnstock/BCTC cache'
    sup=_csv(root/'config/historical_overrides.csv')
    if not sup.empty:
        for c in ['Ticker','Period','Metric','Value','DataType','Source']:
            if c not in sup.columns:sup[c]=np.nan
        # Vnstock/cache has first priority. Supplemental history only fills a missing ticker-period-metric.
        keys=set(map(tuple,base[['Ticker','Period','Metric']].astype(str).values.tolist()))
        sup=sup[~sup[['Ticker','Period','Metric']].astype(str).apply(tuple,axis=1).isin(keys)]
        base=pd.concat([base,sup[['Ticker','Period','Metric','Value','DataType','Source']]],ignore_index=True,sort=False)
    base['PeriodDate']=base['Period'].map(period_date)
    return base.sort_values(['Ticker','Metric','PeriodDate']).reset_index(drop=True)

def target_and_peer(history,ticker,metric,min_peer_banks=3):
    """Return target and synchronized peer history.

    For CAR, disclosures are sparse and often annual/semiannual. We compare by calendar year
    and use one target observation per year plus peer observations from that same year.
    Other metrics use exact quarter dates. No interpolation and no fabricated zeroes.
    """
    h=clean_metric(history[(history.Ticker.astype(str)==str(ticker)) & (history.Metric.astype(str)==str(metric))],metric)
    p=clean_metric(history[history.Metric.astype(str)==str(metric)],metric)
    if h.empty:return h,p.iloc[0:0].copy()
    if metric=='CAR':
        h=h.assign(Year=h.PeriodDate.dt.year).sort_values('PeriodDate').groupby('Year',as_index=False).tail(1)
        years=set(h.Year.tolist())
        p=p.assign(Year=p.PeriodDate.dt.year)
        p=p[p.Year.isin(years)]
        pm=p.groupby('Year',as_index=False).agg(PeerMean=('Value','mean'),BankCount=('Ticker','nunique'))
        pm=pm[pm.BankCount>=min_peer_banks]
        pm['PeriodDate']=pd.to_datetime(pm.Year.astype(str)+'-07-01')
        h['PeriodDate']=pd.to_datetime(h.Year.astype(str)+'-07-01')
        return h.sort_values('PeriodDate'),pm.sort_values('PeriodDate')
    dates=set(h.PeriodDate.tolist())
    p=p[p.PeriodDate.isin(dates)]
    pm=p.groupby('PeriodDate',as_index=False).agg(PeerMean=('Value','mean'),BankCount=('Ticker','nunique'))
    pm=pm[pm.BankCount>=min_peer_banks]
    return h.sort_values('PeriodDate'),pm.sort_values('PeriodDate')

def coverage_note(target,peer):
    if target is None or len(target)==0:return 'Không có dữ liệu lịch sử hợp lệ.'
    y0=pd.Timestamp(target.PeriodDate.min()).year; y1=pd.Timestamp(target.PeriodDate.max()).year
    n=len(target); pn=int(peer.BankCount.max()) if peer is not None and len(peer) and 'BankCount' in peer else 0
    extra=''
    if 'DataType' in target.columns and target['DataType'].astype(str).eq('VERIFIED_HISTORICAL').any():
        srcs=target.loc[target['DataType'].astype(str).eq('VERIFIED_HISTORICAL'),'Source'].dropna().astype(str).unique().tolist()
        if srcs:extra=' Dữ liệu lịch sử bổ sung: '+', '.join(srcs)+'.'
    return f'Dữ liệu ngân hàng: {n} quan sát ({y0}-{y1}); benchmark chỉ hiển thị tại các kỳ/năm ngân hàng có dữ liệu; không nội suy. Số ngân hàng có dữ liệu benchmark tối đa tại một kỳ: {pn}/20.'+extra
