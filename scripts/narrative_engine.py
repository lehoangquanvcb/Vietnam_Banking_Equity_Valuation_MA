
import math
import numpy as np
import pandas as pd

def n(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None

def pct(v,d=1):
    x=n(v)
    return "N/A" if x is None else f"{x:.{d}%}"

def mult(v,d=2):
    x=n(v)
    return "N/A" if x is None else f"{x:.{d}f}x"

def money(v):
    x=n(v)
    return "N/A" if x is None else f"{x*1000:,.0f} đồng/cp"

def bn(v):
    x=n(v)
    return "N/A" if x is None else f"{x/1e9:,.0f} tỷ đồng"

def direction(v, positive="tăng", negative="giảm", flat="ổn định", threshold=.03):
    x=n(v)
    if x is None:return "chưa đủ dữ liệu"
    if x>threshold:return positive
    if x<-threshold:return negative
    return flat

def investment_view_vi(row):
    up=n(row.get("Upside_Base"))
    if up is None:return "CHƯA ĐỦ DỮ LIỆU"
    if up>=.20:return "HẤP DẪN CAO"
    if up>=.08:return "HẤP DẪN"
    if up>=-.05:return "TRUNG LẬP"
    return "KÉM HẤP DẪN"

def executive_summary(row):
    t=str(row.get("Ticker",""))
    p=money(row.get("Price")); fv=money(row.get("FairValue_Base")); up=pct(row.get("Upside_Base"))
    roe=pct(row.get("ROE_Used")); pb=mult(row.get("PB_Current")); npl=pct(row.get("NPL")); car=pct(row.get("CAR"))
    fview=str(row.get("FundamentalView","CHƯA ĐỦ DỮ LIỆU"))
    strategic=""
    if n(row.get("StrategicPriceLow")) is not None:
        strategic=(f" Song song với định giá cơ bản, lớp Market Intelligence ghi nhận vùng giá chiến lược/M&A "
                   f"{money(row.get('StrategicPriceLow'))} - {money(row.get('StrategicPriceHigh'))}. Vùng này được trình bày riêng "
                   "vì có thể phản ánh scarcity premium, quy mô lô, quyền kiểm soát, optionality tái cơ cấu và synergy; không phải giá trị hợp lý fundamental.")
    return (
        f"{t} đang giao dịch tại {p}. Giá trị cơ bản của mô hình là {fv}, tương ứng chênh lệch {up} so với thị giá. "
        f"ROE {roe}, P/B {pb}, NPL {npl} và CAR {car}; chất lượng cơ bản tổng hợp được xếp {fview}. "
        "Giá trị cơ bản được xác định bằng Residual Income và kiểm tra chéo với P/B hợp lý, peer P/B và vùng P/B lịch sử."
        + strategic
    )

def business_profile(row, peer_row=None):
    t=str(row.get("Ticker",""))
    assets=bn(row.get("TotalAssets")); loans=bn(row.get("GrossLoans")); dep=bn(row.get("CustomerDeposits")); eq=bn(row.get("Equity"))
    pg=str(row.get("PeerGroup","N/A"))
    ag=direction(row.get("TotalAssets_Growth"))
    lg=direction(row.get("GrossLoans_Growth"))
    dg=direction(row.get("CustomerDeposits_Growth"))
    text=(
        f"{t} được xếp trong nhóm so sánh '{pg}'. Quy mô tài sản hiện tại khoảng {assets}, dư nợ khách hàng {loans}, "
        f"tiền gửi khách hàng {dep} và vốn chủ sở hữu {eq}. So với các kỳ quan sát trước, tổng tài sản đang {ag}, "
        f"tín dụng {lg} và tiền gửi khách hàng {dg}. Cấu trúc này được sử dụng để đánh giá vị thế thị trường, "
        "khả năng mở rộng bảng cân đối và mức độ phù hợp của tốc độ tăng trưởng với nền vốn."
    )
    if peer_row is not None:
        text += f" P/B trung vị của nhóm tương đồng là {mult(peer_row.get('MedianPB'))}, ROE trung vị {pct(peer_row.get('MedianROE'))}."
    return text

def profitability_text(row):
    roe=pct(row.get("ROE_Used")); roa=pct(row.get("ROA")); nim=pct(row.get("NIM")); cir=pct(row.get("CIR"))
    npg=pct(row.get("NPAT_Growth"))
    score=n(row.get("ProfitabilityScore"))
    label="chưa đủ dữ liệu" if score is None else ("rất tốt" if score>=75 else "tốt" if score>=60 else "trung bình" if score>=45 else "yếu")
    return (
        f"Khả năng sinh lời được xếp mức {label}. ROE hiện tại đạt {roe}, ROA {roa} và NIM {nim}; tỷ lệ chi phí/thu nhập "
        f"(CIR) ở mức {cir}. Lợi nhuận sau thuế so với mốc lịch sử gần đây biến động {npg}. Mô hình ưu tiên ROE và NIM "
        "do đây là các biến có quan hệ trực tiếp với khả năng duy trì P/B cao hơn chi phí vốn trong dài hạn."
    )

def asset_quality_text(row):
    npl=pct(row.get("NPL")); score=n(row.get("AssetQualityScore"))
    label="chưa đủ dữ liệu" if score is None else ("tốt" if score>=60 else "trung bình" if score>=45 else "cần lưu ý")
    return (
        f"Chất lượng tài sản được đánh giá {label}, với NPL hiện tại {npl}. Đối với ngân hàng, P/B thấp không được xem là "
        "hấp dẫn nếu book value chưa phản ánh đầy đủ chi phí tín dụng tiềm ẩn. Trong định giá tái cơ cấu, mô hình vì vậy "
        "điều chỉnh vốn chủ sở hữu cho phần dự phòng bổ sung và haircut trên nợ xấu trước khi áp dụng mức P/B chuẩn hóa."
    )

def funding_text(row):
    casa=pct(row.get("CASA")); ldr=pct(row.get("LDR")); depg=pct(row.get("CustomerDeposits_Growth"))
    score=n(row.get("FundingScore"))
    label="chưa đủ dữ liệu" if score is None else ("tốt" if score>=60 else "trung bình" if score>=45 else "yếu")
    return (
        f"Chất lượng nguồn vốn được xếp mức {label}. CASA đạt {casa}, LDR {ldr} và tăng trưởng tiền gửi gần đây {depg}. "
        "CASA cao thường hỗ trợ chi phí vốn và NIM, nhưng mô hình không nội suy CASA khi nguồn Vnstock/BCTC không cung cấp; "
        "trường hợp thiếu dữ liệu được thể hiện N/A và không chuyển thành dữ liệu thực bằng giả định."
    )

def capital_text(row):
    car=pct(row.get("CAR")); eqassets=None
    if n(row.get("Equity")) is not None and n(row.get("TotalAssets")) not in (None,0):
        eqassets=n(row.get("Equity"))/n(row.get("TotalAssets"))
    score=n(row.get("CapitalScore"))
    label="chưa đủ dữ liệu" if score is None else ("tốt" if score>=60 else "trung bình" if score>=45 else "cần củng cố")
    return (
        f"Nền vốn được đánh giá {label}. CAR hiện tại {car}; vốn chủ sở hữu/tổng tài sản khoảng {pct(eqassets)}. "
        "Trong các kịch bản M&A hoặc tái cơ cấu, mô hình tách riêng phần vốn bổ sung bắt buộc vì recapitalization có thể "
        "làm giảm đáng kể giá mua tối đa mà bên thâu tóm có thể chấp nhận."
    )

def valuation_text(row):
    return (
        f"Cổ phiếu hiện giao dịch tại P/B {mult(row.get('PB_Current'))}, P/TBV {mult(row.get('PTBV_Current'))} và "
        f"P/E {mult(row.get('PE_Current'),1)}. P/B hợp lý theo ROE/COE/g là {mult(row.get('JustifiedPB'))}; "
        f"COE sử dụng {pct(row.get('COE'))}, tăng trưởng dài hạn {pct(row.get('LTG'))} và ROE chuẩn hóa "
        f"{pct(row.get('NormalizedROE_Used'))}. Giá trị hợp lý cơ sở {money(row.get('FairValue_Base'))}, "
        f"tương ứng {pct(row.get('Upside_Base'))} so với giá thị trường."
    )

def catalysts_risks(row):
    cats=[]
    risks=[]
    if n(row.get("ROE_Used")) and n(row.get("ROE_Used"))>=.18: cats.append("ROE duy trì ở mức cao, hỗ trợ P/B hợp lý.")
    if n(row.get("NIM")) and n(row.get("NIM"))>=.035: cats.append("NIM tương đối tốt, hỗ trợ khả năng tạo thu nhập.")
    if n(row.get("GrossLoans_Growth")) and n(row.get("GrossLoans_Growth"))>.10: cats.append("Tăng trưởng tín dụng tích cực nếu đi kèm chất lượng tài sản.")
    if n(row.get("CASA")) and n(row.get("CASA"))>=.20: cats.append("CASA cao tạo lợi thế về chi phí vốn.")
    if n(row.get("NPL")) and n(row.get("NPL"))>.025: risks.append("NPL cao có thể làm tăng chi phí tín dụng và giảm book value sạch.")
    if n(row.get("CAR")) and n(row.get("CAR"))<.10: risks.append("Biên an toàn vốn thấp có thể hạn chế tăng trưởng hoặc phát sinh nhu cầu tăng vốn.")
    if n(row.get("PB_Current")) and n(row.get("JustifiedPB")) and n(row.get("PB_Current"))>n(row.get("JustifiedPB")): risks.append("P/B thị trường cao hơn P/B hợp lý của mô hình.")
    if not cats: cats=["Cải thiện ROE, NIM, CASA hoặc tốc độ tăng trưởng chất lượng có thể là động lực tái định giá."]
    if not risks: risks=["Rủi ro chính gồm suy giảm chất lượng tài sản, tăng chi phí vốn, pha loãng vốn và thay đổi môi trường lãi suất/quy định."]
    return cats,risks

def mna_text(row, mna_row=None):
    if mna_row is None:
        return "Chưa có baseline M&A cho ngân hàng này."
    return (
        f"Giá trị độc lập của vốn chủ sở hữu được ước tính {bn(mna_row.get('StandaloneEquityValue'))}. "
        f"Kịch bản cơ sở áp dụng thặng dư quyền kiểm soát {pct(mna_row.get('ControlPremium'))}, PV giá trị cộng hưởng "
        f"{bn(mna_row.get('PV_Synergies'))} và chi phí tích hợp {bn(mna_row.get('IntegrationCost'))}. "
        f"Giá trị giao dịch minh họa là {bn(mna_row.get('IllustrativeConsideration'))}, tương ứng P/B "
        f"{mult(mna_row.get('ImpliedPB'))} và P/TBV {mult(mna_row.get('ImpliedPTBV'))}. "
        f"Goodwill/(bargain purchase) minh họa {bn(mna_row.get('Goodwill'))}. Đây là giá trị kịch bản, không phải giá chào mua quan sát thực tế."
    )
