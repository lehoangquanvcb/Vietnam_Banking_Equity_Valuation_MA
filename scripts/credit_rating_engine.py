from __future__ import annotations
import math
import numpy as np
import pandas as pd

# Thang xếp hạng nội địa dùng để dịch chuyển notch.
RATING_SCALE = [
    "vnAAA","vnAA+","vnAA","vnAA-","vnA+","vnA","vnA-",
    "vnBBB+","vnBBB","vnBBB-","vnBB+","vnBB","vnBB-","vnB+","vnB","vnB-","vnCCC"
]

# Theo Phương pháp XHTN Ngân hàng Saigon Ratings 2025: BICRA Việt Nam hiện ở a-.
BICRA_ANCHOR = "vnA-"

FACTOR_LABELS = {
    "BusinessPosition":"Hồ sơ kinh doanh",
    "CapitalEarnings":"Vốn và lợi nhuận",
    "RiskPosition":"Vị thế rủi ro",
    "Funding":"Huy động vốn",
    "Liquidity":"Thanh khoản",
}

DESCRIPTOR_6={1:"Rất Mạnh",2:"Mạnh",3:"Phù Hợp",4:"Trung Bình",5:"Yếu",6:"Rất Yếu"}
DESCRIPTOR_4={1:"Mạnh",2:"Phù Hợp",3:"Trung Bình",4:"Yếu"}
# Bảng hướng dẫn số 2. Với Yếu/Rất yếu, methodology cho khoảng notch; engine mặc định lấy mức ít tiêu cực hơn,
# chuyên viên có thể điều chỉnh thêm bằng "Điều chỉnh khác trước SACP".
NOTCH_6={1:2,2:1,3:0,4:-1,5:-2,6:-4}
# Khoảng notch được phép theo ma trận methodology chính thức.
NOTCH_6_ALLOWED={1:[2],2:[1],3:[0],4:[-1],5:[-2,-3],6:[-4,-5]}
# Bảng hướng dẫn số 10: Huy động vốn (hàng) x Thanh khoản (cột)
FUNDING_LIQUIDITY_NOTCH={
    1:{1:1,2:0,3:-1,4:-2},
    2:{1:0,2:0,3:-1,4:-2},
    3:{1:0,2:-1,3:-2,4:-3},
    4:{1:-1,2:-2,3:-3,4:-3},
}
# “-2 hoặc hơn” / “-3 hoặc hơn” được giữ đúng như methodology; engine chỉ
# tự động lấy mức đầu tiên, chuyên viên có thể chọn mức nghiêm khắc hơn tới -5.
FUNDING_LIQUIDITY_ALLOWED={
    (1,1):[1],(1,2):[0],(1,3):[-1],(1,4):[-2,-3,-4,-5],
    (2,1):[0],(2,2):[0],(2,3):[-1],(2,4):[-2,-3,-4,-5],
    (3,1):[0],(3,2):[-1],(3,3):[-2],(3,4):[-3,-4,-5],
    (4,1):[-1],(4,2):[-2],(4,3):[-3],(4,4):[-3,-4,-5],
}

def allowed_factor_notches(score):
    return NOTCH_6_ALLOWED[int(score)]

def allowed_funding_liquidity_notches(funding_score, liquidity_score):
    return FUNDING_LIQUIDITY_ALLOWED[(int(funding_score),int(liquidity_score))]

def _n(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except Exception:return None

def _pct_rank(series,value,higher_better=True):
    s=pd.to_numeric(series,errors="coerce").dropna(); v=_n(value)
    if v is None or s.empty:return .5
    return float((s<=v).mean()) if higher_better else float((s>=v).mean())

def _weighted_percentile(parts):
    valid=[(p,w) for p,w in parts if p is not None]
    if not valid:return .5
    sw=sum(w for _,w in valid)
    return sum(p*w for p,w in valid)/sw if sw else .5

def _score6(p):
    if p>=.85:return 1
    if p>=.65:return 2
    if p>=.40:return 3
    if p>=.20:return 4
    if p>=.08:return 5
    return 6

def _score4(p):
    if p>=.75:return 1
    if p>=.45:return 2
    if p>=.20:return 3
    return 4

def _car_score(car):
    """Bảng 8 methodology: CAR kỳ vọng."""
    v=_n(car)
    if v is None:return 3
    if v>.18:return 1
    if v>=.15:return 2
    if v>=.12:return 3
    if v>=.09:return 4
    if v>=.08:return 5
    return 6

def _bounded_ldr_percentile(ldr):
    v=_n(ldr)
    if v is None:return .5
    if .75<=v<=.95:return .85
    if .65<=v<.75 or .95<v<=1.05:return .62
    if .55<=v<.65 or 1.05<v<=1.15:return .38
    return .15

def _shift_rating(rating,notches):
    try:i=RATING_SCALE.index(rating)
    except ValueError:return rating
    # notch dương = nâng hạng.
    j=max(0,min(len(RATING_SCALE)-1,i-int(notches)))
    return RATING_SCALE[j]

def _trend_outlook(row):
    pos=neg=0
    loan=_n(row.get("GrossLoans_Growth")); dep=_n(row.get("CustomerDeposits_Growth")); npat=_n(row.get("NPAT_Growth"))
    npl=_n(row.get("NPL")); car=_n(row.get("CAR")); casa=_n(row.get("CASA")); roe=_n(row.get("ROE_Used"))
    if npat is not None: pos += npat>.12; neg += npat<0
    if dep is not None and loan is not None: pos += dep>=loan*.8; neg += loan-dep>.12
    if car is not None: pos += car>=.12; neg += car<.09
    if npl is not None: pos += npl<.02; neg += npl>.035
    if casa is not None: pos += casa>.20
    if roe is not None: pos += roe>.16; neg += roe<.08
    if pos-neg>=3:return "Tích cực"
    if neg-pos>=2:return "Tiêu cực"
    return "Ổn định"

def _fmt_pct(x):
    v=_n(x)
    if v is None:return "N/A"
    return f"{v*100:.1f}%".replace(".",",")

def build_credit_rating(summary:pd.DataFrame,ticker:str,governance_score=3,external_support_notches=0,analyst_notches=0,notch_overrides=None,factor_score_overrides=None):
    """Saigon Ratings 2025 notch framework.

    Anchor BICRA (vnA-) -> Hồ sơ kinh doanh -> Vốn & lợi nhuận -> Vị thế rủi ro
    -> kết hợp Huy động vốn & Thanh khoản -> điều chỉnh khác = SACP
    -> hỗ trợ bên ngoài = ICR cuối cùng.
    """
    if summary is None or summary.empty:raise ValueError("Chưa có dữ liệu ngân hàng để xếp hạng.")
    s=summary.copy(); rr=s[s["Ticker"].astype(str).eq(str(ticker))]
    if rr.empty:raise ValueError(f"Không tìm thấy {ticker}")
    row=rr.iloc[0]

    # HỒ SƠ KINH DOANH: định lượng + chất lượng quản trị/chiến lược do chuyên viên chấm 1-6.
    bp_quant=_weighted_percentile([
        (_pct_rank(s.TotalAssets,row.get("TotalAssets"),True),.40),
        (_pct_rank(s.GrossLoans_Growth,row.get("GrossLoans_Growth"),True),.20),
        (_pct_rank(s.CustomerDeposits_Growth,row.get("CustomerDeposits_Growth"),True),.20),
        (_pct_rank(s.CASA,row.get("CASA"),True),.20),
    ])
    bp_quant_score=_score6(bp_quant)
    gov=max(1,min(6,int(governance_score)))
    business_score=max(1,min(6,round(bp_quant_score*.65+gov*.35)))

    # VỐN & LỢI NHUẬN: CAR là điểm ban đầu theo Bảng 8, sau đó điều chỉnh tối đa +/-1 theo chất lượng sinh lời.
    capital_initial=_car_score(row.get("CAR"))
    earn_p=_weighted_percentile([
        (_pct_rank(s.ROE_Used,row.get("ROE_Used"),True),.35),
        (_pct_rank(s.ROA,row.get("ROA"),True),.20),
        (_pct_rank(s.NIM,row.get("NIM"),True),.20),
        (_pct_rank(s.CIR,row.get("CIR"),False),.15),
        (_pct_rank(s.NPL,row.get("NPL"),False),.10),
    ])
    earn_adj=1 if earn_p>=.75 else (-1 if earn_p<.20 else 0)
    capital_score=max(1,min(6,capital_initial-earn_adj))

    # VỊ THẾ RỦI RO.
    risk_p=_weighted_percentile([
        (_pct_rank(s.NPL,row.get("NPL"),False),.50),
        (_pct_rank(s.GrossLoans_Growth,row.get("GrossLoans_Growth"),False),.15),
        (_pct_rank(s.CAR,row.get("CAR"),True),.15),
        (_pct_rank(s.ROE_Used,row.get("ROE_Used"),True),.20),
    ])
    risk_score=_score6(risk_p)

    # HUY ĐỘNG VỐN & THANH KHOẢN: chấm riêng 4 mức rồi dùng ma trận Bảng 10 để ra 1 notch kết hợp.
    funding_p=_weighted_percentile([
        (_pct_rank(s.CASA,row.get("CASA"),True),.45),
        (_pct_rank(s.CustomerDeposits_Growth,row.get("CustomerDeposits_Growth"),True),.25),
        (_bounded_ldr_percentile(row.get("LDR")),.20),
        (_pct_rank(s.TotalAssets,row.get("TotalAssets"),True),.10),
    ])
    liquidity_p=_weighted_percentile([
        (_bounded_ldr_percentile(row.get("LDR")),.60),
        (_pct_rank(s.CASA,row.get("CASA"),True),.15),
        (_pct_rank(s.CustomerDeposits_Growth,row.get("CustomerDeposits_Growth"),True),.15),
        (_pct_rank(s.TotalAssets,row.get("TotalAssets"),True),.10),
    ])
    funding_score=_score4(funding_p); liquidity_score=_score4(liquidity_p)

    # Chuyên viên có thể xác nhận/override MỨC ĐÁNH GIÁ yếu tố.
    # Override này diễn ra TRƯỚC khi tra notch để bảo đảm ma trận luôn đúng với mức đánh giá đang hiển thị.
    factor_score_overrides=factor_score_overrides or {}
    score_limits={"BusinessPosition":6,"CapitalEarnings":6,"RiskPosition":6,"Funding":4,"Liquidity":4}
    computed_scores={"BusinessPosition":business_score,"CapitalEarnings":capital_score,"RiskPosition":risk_score,
                     "Funding":funding_score,"Liquidity":liquidity_score}
    factor_scores={}
    for key,auto_score in computed_scores.items():
        chosen=int(factor_score_overrides.get(key,auto_score))
        if chosen<1 or chosen>score_limits[key]:
            raise ValueError(f"Điểm {chosen} không hợp lệ cho {FACTOR_LABELS[key]} (1-{score_limits[key]}).")
        factor_scores[key]=chosen

    business_score=factor_scores["BusinessPosition"]
    capital_score=factor_scores["CapitalEarnings"]
    risk_score=factor_scores["RiskPosition"]
    funding_score=factor_scores["Funding"]
    liquidity_score=factor_scores["Liquidity"]
    funding_liquidity_notch=FUNDING_LIQUIDITY_NOTCH[funding_score][liquidity_score]
    factor_notches={
        "BusinessPosition":NOTCH_6[business_score],
        "CapitalEarnings":NOTCH_6[capital_score],
        "RiskPosition":NOTCH_6[risk_score],
    }
    notch_overrides=notch_overrides or {}
    for key,score in (("BusinessPosition",business_score),("CapitalEarnings",capital_score),("RiskPosition",risk_score)):
        if key in notch_overrides:
            chosen=int(notch_overrides[key])
            if chosen not in NOTCH_6_ALLOWED[score]:
                raise ValueError(f"Notch {chosen} không hợp lệ cho {FACTOR_LABELS[key]} mức {DESCRIPTOR_6[score]}.")
            factor_notches[key]=chosen
    if "FundingLiquidity" in notch_overrides:
        chosen=int(notch_overrides["FundingLiquidity"])
        allowed=FUNDING_LIQUIDITY_ALLOWED[(funding_score,liquidity_score)]
        if chosen not in allowed:
            raise ValueError(f"Notch {chosen} không hợp lệ cho ma trận Huy động vốn × Thanh khoản.")
        funding_liquidity_notch=chosen
    internal_notches=sum(factor_notches.values())+funding_liquidity_notch+int(analyst_notches)
    sacp=_shift_rating(BICRA_ANCHOR,internal_notches)
    final=_shift_rating(sacp,int(external_support_notches))
    outlook=_trend_outlook(row)

    rationale={
      "BusinessPosition":f"Quy mô, tăng trưởng tín dụng {_fmt_pct(row.get('GrossLoans_Growth'))}, tăng trưởng tiền gửi {_fmt_pct(row.get('CustomerDeposits_Growth'))} và CASA {_fmt_pct(row.get('CASA'))} được so sánh với 20 ngân hàng niêm yết; điểm quản trị/chiến lược do chuyên viên chấm {gov}/6.",
      "CapitalEarnings":f"CAR {_fmt_pct(row.get('CAR'))} xác định điểm ban đầu theo ngưỡng CAR của methodology; sau đó kiểm tra ROE {_fmt_pct(row.get('ROE_Used'))}, ROA {_fmt_pct(row.get('ROA'))}, NIM {_fmt_pct(row.get('NIM'))}, CIR {_fmt_pct(row.get('CIR'))} và chất lượng lợi nhuận.",
      "RiskPosition":f"NPL {_fmt_pct(row.get('NPL'))}, tốc độ tăng trưởng tín dụng và bộ đệm vốn được dùng để đánh giá khẩu vị rủi ro, kinh nghiệm tổn thất và mức độ nhạy cảm so với 20 ngân hàng niêm yết.",
      "Funding":f"CASA {_fmt_pct(row.get('CASA'))}, tăng trưởng tiền gửi {_fmt_pct(row.get('CustomerDeposits_Growth'))}, LDR {_fmt_pct(row.get('LDR'))} và quy mô được dùng để đánh giá tính ổn định/đa dạng của nguồn vốn.",
      "Liquidity":f"LDR {_fmt_pct(row.get('LDR'))} là biến định lượng trọng tâm, kết hợp CASA, tăng trưởng tiền gửi và khả năng tiếp cận nguồn thanh khoản thứ cấp.",
    }

    strengths=[]; constraints=[]
    for k,sc in factor_scores.items():
        desc=(DESCRIPTOR_4 if k in {"Funding","Liquidity"} else DESCRIPTOR_6)[sc]
        if sc<=2:strengths.append(f"{FACTOR_LABELS[k]}: {desc}.")
        if (k in {"Funding","Liquidity"} and sc>=3) or (k not in {"Funding","Liquidity"} and sc>=4):constraints.append(f"{FACTOR_LABELS[k]}: {desc}.")
    if _n(row.get("CAR")) is not None and _n(row.get("CAR"))>=.12:strengths.append("CAR từ 12% trở lên hỗ trợ khả năng hấp thụ tổn thất và tăng trưởng.")
    if _n(row.get("NPL")) is not None and _n(row.get("NPL"))>.03:constraints.append("NPL trên 3% tạo áp lực lên chi phí tín dụng, lợi nhuận và vốn.")
    if _n(row.get("CASA")) is not None and _n(row.get("CASA"))<.10:constraints.append("CASA thấp làm giảm lợi thế chi phí vốn và khả năng bảo vệ NIM.")

    return {
      "Ticker":str(ticker),"AnchorRating":BICRA_ANCHOR,"SACPRating":sacp,"StandaloneRating":sacp,"FinalRating":final,"Outlook":outlook,
      "BusinessNotch":factor_notches["BusinessPosition"],"CapitalNotch":factor_notches["CapitalEarnings"],"RiskNotch":factor_notches["RiskPosition"],
      "FundingLiquidityNotch":funding_liquidity_notch,"OtherInternalNotches":int(analyst_notches),"InternalNotches":int(internal_notches),
      "ExternalSupportNotches":int(external_support_notches),"TotalNotches":int(internal_notches)+int(external_support_notches),
      "FactorScores":factor_scores,"ComputedFactorScores":computed_scores,"FactorScoreOverrides":factor_score_overrides,
      "FactorNotches":factor_notches,"FactorRationale":rationale,
      "AllowedFactorNotches":{k:NOTCH_6_ALLOWED[v] for k,v in factor_scores.items() if k not in {"Funding","Liquidity"}},
      "AllowedFundingLiquidityNotches":FUNDING_LIQUIDITY_ALLOWED[(funding_score,liquidity_score)],
      "FundingDescriptor":DESCRIPTOR_4[funding_score],"LiquidityDescriptor":DESCRIPTOR_4[liquidity_score],
      "FundingLiquidityCell":f"{DESCRIPTOR_4[funding_score]} ({funding_score}/4) × {DESCRIPTOR_4[liquidity_score]} ({liquidity_score}/4)",
      "Strengths":strengths or ["Chưa phát hiện điểm mạnh nổi trội từ dữ liệu công khai hiện có."],
      "Constraints":constraints or ["Chưa phát hiện hạn chế định lượng nổi trội; vẫn cần rà soát định tính."],
      "UpgradeTriggers":["CAR kỳ vọng cải thiện bền vững sang vùng đánh giá cao hơn trong methodology.","NPL và tổn thất tín dụng giảm bền vững so với nhóm ngân hàng tương đồng.","CASA, tiền gửi khách hàng và dự trữ thanh khoản cải thiện, giúp nâng đánh giá Huy động vốn/Thanh khoản.","Hồ sơ kinh doanh và quản trị được chứng minh tốt hơn trung bình ngành mà không gia tăng khẩu vị rủi ro."],
      "DowngradeTriggers":["CAR suy giảm sang vùng đánh giá thấp hơn hoặc xuất hiện rủi ro vi phạm yêu cầu vốn.","NPL/tổn thất tín dụng tăng mạnh hoặc khẩu vị rủi ro vượt mức trung bình ngành.","Nguồn vốn kém ổn định, LDR tăng cao hoặc phải phụ thuộc đáng kể vào nguồn thanh khoản khẩn cấp.","Suy yếu quản trị, kiểm soát nội bộ, chiến lược hoặc xuất hiện rủi ro tập trung/phức tạp đáng kể."],
      "Methodology":"BICRA/Anchor vnA- -> cộng/trừ notch Hồ sơ kinh doanh -> Vốn & lợi nhuận -> Vị thế rủi ro -> ma trận Huy động vốn & Thanh khoản -> điều chỉnh khác = SACP -> hỗ trợ bên ngoài = ICR.",
      "Disclaimer":"Kết quả là mô phỏng theo phương pháp XHTN Ngân hàng 2025 từ dữ liệu công khai. Các yếu tố định tính, dự phóng 1-2 năm, thông tin phỏng vấn và quyết định Hội đồng XHTN vẫn phải được chuyên viên xác nhận trước khi phát hành chính thức."
    }

def rating_table(summary,governance_score=3):
    rows=[]
    for t in summary["Ticker"].astype(str):
        try:
            r=build_credit_rating(summary,t,governance_score=governance_score)
            rows.append({"Mã ngân hàng":t,"Anchor BICRA":r["AnchorRating"],"Tổng notch nội tại":r["InternalNotches"],"SACP":r["SACPRating"],"ICR mô phỏng":r["FinalRating"],"Triển vọng":r["Outlook"]})
        except Exception:pass
    return pd.DataFrame(rows)
