from pathlib import Path
import sys
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.credit_rating_engine import (
    NOTCH_6_ALLOWED,FUNDING_LIQUIDITY_ALLOWED,FUNDING_LIQUIDITY_NOTCH,
    build_credit_rating,_shift_rating
)
from scripts.history_engine import load_effective_history,target_and_peer

# 1) Exact factor notch matrix.
expected6={1:[2],2:[1],3:[0],4:[-1],5:[-2,-3],6:[-4,-5]}
assert NOTCH_6_ALLOWED==expected6, f'NOTCH_6_ALLOWED sai: {NOTCH_6_ALLOWED}'

# 2) Exact funding x liquidity matrix and allowed ranges.
expected_base={
 (1,1):1,(1,2):0,(1,3):-1,(1,4):-2,
 (2,1):0,(2,2):0,(2,3):-1,(2,4):-2,
 (3,1):0,(3,2):-1,(3,3):-2,(3,4):-3,
 (4,1):-1,(4,2):-2,(4,3):-3,(4,4):-3,
}
for (f,l),v in expected_base.items():
    assert FUNDING_LIQUIDITY_NOTCH[f][l]==v,(f,l,FUNDING_LIQUIDITY_NOTCH[f][l],v)
    assert FUNDING_LIQUIDITY_ALLOWED[(f,l)][0]==v,(f,l,FUNDING_LIQUIDITY_ALLOWED[(f,l)],v)
assert FUNDING_LIQUIDITY_ALLOWED[(4,1)]==[-1], 'Yếu × Mạnh bắt buộc = -1'
assert FUNDING_LIQUIDITY_ALLOWED[(1,4)]==[-2,-3,-4,-5]
assert FUNDING_LIQUIDITY_ALLOWED[(3,4)]==[-3,-4,-5]

# 3) Rating shift semantics.
assert _shift_rating('vnA-',-2)=='vnBBB', 'A- -2 notch phải ra BBB'
assert _shift_rating('vnA-',1)=='vnA', 'A- +1 notch phải ra A'

# 4) Physical ACTUAL cache must not contain supplemental keys.
hist_path=ROOT/'data/bank_history_long.csv'; ov_path=ROOT/'config/historical_overrides.csv'
raw=pd.read_csv(hist_path); ov=pd.read_csv(ov_path,encoding='utf-8-sig')
keys=set(map(tuple,ov[['Ticker','Period','Metric']].astype(str).values.tolist()))
rawkeys=set(map(tuple,raw[['Ticker','Period','Metric']].astype(str).values.tolist()))
overlap=keys & rawkeys
assert not overlap, f'Lineage lỗi: supplemental history đã bị ghi vào ACTUAL cache: {sorted(overlap)[:5]}'

# 5) Runtime history merges verified supplement but keeps source lineage.
eff=load_effective_history(ROOT,raw)
klb=eff[(eff.Ticker.astype(str)=='KLB')&(eff.Metric.astype(str)=='CAR')]
if len(ov[(ov.Ticker.astype(str)=='KLB')&(ov.Metric.astype(str)=='CAR')]):
    assert len(klb)>=10, f'KLB CAR effective history quá ngắn: {len(klb)}'
    assert (klb.DataType.astype(str)=='VERIFIED_HISTORICAL').any(), 'Không giữ lineage VERIFIED_HISTORICAL'
h,p=target_and_peer(eff,'KLB','CAR')
if len(p):
    assert set(p.PeriodDate.dt.year).issubset(set(h.PeriodDate.dt.year)), 'Peer CAR chứa năm KLB không có dữ liệu'

# 6) End-to-end matrix selection test on KLB when valuation summary exists.
sp=ROOT/'data/model_outputs/valuation_summary.csv'
if sp.exists():
    s=pd.read_csv(sp)
    if 'KLB' in set(s.Ticker.astype(str)):
        r=build_credit_rating(s,'KLB',factor_score_overrides={'Funding':4,'Liquidity':1})
        assert r['FundingLiquidityNotch']==-1, r
        assert r['AllowedFundingLiquidityNotches']==[-1], r['AllowedFundingLiquidityNotches']

print('OK - methodology, matrix, rating shift, history sync and lineage controls passed.')
