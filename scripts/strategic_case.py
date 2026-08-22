from pathlib import Path
import json, math
import pandas as pd
import numpy as np


def n(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def load_research(root):
    p=Path(root)/'config'/'stb_public_research_benchmarks.csv'
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def all_bank_means(summary):
    fields=['ROE_Used','ROA','NIM','NPL','CAR','CASA','CIR','LDR','PB_Current','PTBV_Current','PE_Current','InvestmentScore','FundamentalScore']
    out={}
    for c in fields:
        if c in summary:
            out[c]=pd.to_numeric(summary[c],errors='coerce').replace([np.inf,-np.inf],np.nan).mean()
    return out


def strategic_reasonableness(row, cfg, research=None):
    """Quantitative bridge from listed-market value to large-block / strategic value.

    Prices in row/config are stored in thousand VND/share. This function does NOT
    assert that a transaction will happen; it measures what assumptions are needed
    for a quoted strategic range to be economically coherent.
    """
    ticker=str(row.get('Ticker',''))
    price=n(row.get('Price'))
    bvps=n(row.get('BVPS_Used'))
    shares=n(row.get('Shares'))
    # Legacy valuation outputs may store Shares 1,000x too high because BVPS is in thousand VND/share while equity is in VND.
    # Normalize to actual share count for transaction-size calculations only.
    if shares is not None and shares>1e11:
        shares=shares/1000.0
    lo=n(row.get('StrategicPriceLow'))
    hi=n(row.get('StrategicPriceHigh'))
    ref_stake=n(row.get('StrategicReferenceStake')) or .325
    sc=(cfg.get('strategic_case') or {}).get(ticker,{})
    claim_bn=n(sc.get('secured_claim_estimate_vnd_bn'))
    public_high=n(sc.get('public_high_case_value_per_share_thousand'))
    bvps_uplift=n(sc.get('post_resolution_bvps_uplift_thousand')) or 0

    block_shares=shares*ref_stake if shares is not None else None
    post_bvps=(bvps+bvps_uplift) if bvps is not None else None

    def one(px):
        if px is None:return {}
        consideration_bn=(block_shares*px/1e6) if block_shares is not None else None
        # shares * thousand VND = thousand VND; /1e6 => VND bn
        recovery=(consideration_bn/claim_bn) if consideration_bn is not None and claim_bn else None
        return {
            'price':px,
            'premium_to_market':px/price-1 if price else None,
            'implied_pb_current':px/bvps if bvps else None,
            'implied_pb_post_resolution':px/post_bvps if post_bvps else None,
            'block_consideration_bn':consideration_bn,
            'claim_recovery':recovery,
            'premium_to_public_high':px/public_high-1 if public_high else None,
        }

    low=one(lo); high=one(hi)
    clearing=(claim_bn*1e6/block_shares) if claim_bn and block_shares else None

    # Public research range, if available.
    public_bases=[]; public_highs=[]
    if research is not None and len(research):
        for c in ['BasePrice','HighPrice']:
            if c in research:
                vals=pd.to_numeric(research[c],errors='coerce').dropna().tolist()
                (public_bases if c=='BasePrice' else public_highs).extend(vals)
    public_base_median=float(np.median(public_bases)) if public_bases else None
    public_observed_high=max(public_highs+public_bases) if (public_highs or public_bases) else public_high

    return {
        'ticker':ticker,'market_price':price,'strategic_low':lo,'strategic_high':hi,'reference_stake':ref_stake,
        'block_shares':block_shares,'claim_bn':claim_bn,'full_recovery_clearing_price':clearing,
        'bvps':bvps,'post_resolution_bvps':post_bvps,'public_base_median':public_base_median,
        'public_observed_high':public_observed_high,'low':low,'high':high,
        'source':sc.get('source'),'source_url':sc.get('source_url')
    }


def reasonableness_conclusion(case):
    lo=case.get('low') or {}; hi=case.get('high') or {}
    if not lo or not hi:return 'Chưa đủ dữ liệu để kiểm tra tính hợp lý của vùng giá chiến lược.'
    lp=lo.get('premium_to_market'); hp=hi.get('premium_to_market')
    lr=lo.get('claim_recovery'); hr=hi.get('claim_recovery')
    ph=case.get('public_observed_high'); cp=case.get('full_recovery_clearing_price')
    pieces=[]
    if lp is not None and hp is not None:
        pieces.append(f"Vùng giá chiến lược chỉ cao hơn thị giá khoảng {lp:.1%} đến {hp:.1%}, tức low-end gần với giá niêm yết còn high-end phản ánh premium cho một lô cổ phần lớn.")
    if ph is not None:
        pieces.append(f"Các báo cáo công khai trong package cho thấy vùng định giá standalone/high-case đã lên tới khoảng {ph*1000:,.0f} đồng/cp; vì vậy 80.000 đồng/cp nằm sát vùng high-case, còn 100.000 đồng/cp cần thêm giá trị chiến lược ngoài standalone valuation.")
    if lr is not None and hr is not None:
        pieces.append(f"Với lô tham chiếu 32,5%, giá 80.000–100.000 đồng/cp tạo giá trị lô tương đương khoảng {lr:.1%}–{hr:.1%} của ước tính 63.250 tỷ đồng gốc+lãi liên quan đến tài sản bảo đảm.")
    if cp is not None:
        pieces.append(f"Mức giá xấp xỉ {cp*1000:,.0f} đồng/cp mới tương đương thu hồi 100% ước tính 63.250 tỷ đồng; do đó 100.000 đồng/cp nằm gần 'clearing price' kinh tế của kịch bản thu hồi gần đầy đủ, không phải một con số phi lý về mặt cấu trúc thương vụ.")
    pieces.append("Tuy nhiên, đây là kiểm tra tính hợp lý kinh tế chứ không phải bằng chứng rằng giao dịch chắc chắn sẽ xảy ra ở mức giá đó; mức 100.000 đồng/cp chỉ hợp lý nếu xác suất xử lý thành công lô 32,5%, giá trị hậu tái cơ cấu, scarcity/quyền ảnh hưởng và/hoặc synergy đủ lớn để bù rủi ro thời gian và chất lượng tài sản.")
    return ' '.join(pieces)
