from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; CFG=ROOT/'config'
p=CFG/'historical_overrides.csv'
if not p.exists():
    print('Không có historical_overrides.csv.'); raise SystemExit(0)
s=pd.read_csv(p,encoding='utf-8-sig')
req={'Ticker','Period','Metric','Value','DataType','Source'}
miss=req-set(s.columns)
if miss: raise ValueError(f'Historical overrides thiếu cột: {sorted(miss)}')
if s.duplicated(['Ticker','Period','Metric']).any():
    raise ValueError('Historical overrides có khóa Ticker-Period-Metric trùng lặp.')
print(f'Đã kiểm tra {len(s)} dòng lịch sử bổ sung. Không ghi vào bank_history_long.csv; lineage được giữ riêng khi runtime merge.')
