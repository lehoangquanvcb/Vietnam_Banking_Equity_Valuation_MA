
from pathlib import Path
import json, math
from datetime import datetime, timezone
import pandas as pd
import numpy as np

def n(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:return None

def _parse_date(v):
    try:
        return pd.to_datetime(v,errors="coerce",utc=True)
    except Exception:
        return pd.NaT

def assess_report_quality(row,cfg,history=None,prices=None):
    gate=cfg.get("report_quality_gate",{})
    core=gate.get("core_metrics",["Price","BVPS_Used","ROE_Used","NPL","TotalAssets","GrossLoans","CustomerDeposits","Equity","NPAT","FairValue_Base"])
    missing=[c for c in core if n(row.get(c)) is None]
    available=len(core)-len(missing)
    core_coverage=available/len(core) if core else 0
    model_coverage=n(row.get("DataCoverage"))
    if model_coverage is None:model_coverage=core_coverage
    coverage=min(1.0,max(0.0,(model_coverage+core_coverage)/2))

    warnings=[]
    critical=[]
    if n(row.get("Price")) is None: critical.append("Thiếu giá thị trường.")
    if n(row.get("FairValue_Base")) is None: critical.append("Chưa tính được giá trị hợp lý.")
    if n(row.get("Equity")) is None or n(row.get("BVPS_Used")) is None: critical.append("Thiếu vốn chủ sở hữu/BVPS.")
    if n(row.get("ROE_Used")) is None: warnings.append("Thiếu ROE.")
    if n(row.get("NPL")) is None: warnings.append("Thiếu NPL.")
    if n(row.get("CAR")) is None: warnings.append("Thiếu CAR; phần an toàn vốn bị hạn chế.")
    if n(row.get("CASA")) is None: warnings.append("Thiếu CASA; phần chất lượng nguồn vốn bị hạn chế.")

    retrieved=_parse_date(row.get("RetrievedAt"))
    age_days=None
    if pd.notna(retrieved):
        now=pd.Timestamp.now(tz="UTC")
        age_days=max(0,(now-retrieved).days)
        if age_days>int(gate.get("max_data_age_days",120)):
            warnings.append(f"Dữ liệu đã {age_days} ngày kể từ lần truy xuất gần nhất.")
    else:
        warnings.append("Không xác định được ngày truy xuất dữ liệu.")

    off_cov=float(gate.get("official_min_coverage",.80))
    draft_cov=float(gate.get("draft_min_coverage",.60))
    off_missing=int(gate.get("max_core_missing_official",2))
    draft_missing=int(gate.get("max_core_missing_draft",5))
    if not critical and coverage>=off_cov and len(missing)<=off_missing:
        status="CHÍNH THỨC"
        stamp="ĐỦ ĐIỀU KIỆN PHÁT HÀNH"
    elif coverage>=draft_cov and len(missing)<=draft_missing:
        status="BẢN NHÁP"
        stamp="BẢN NHÁP – CẦN RÀ SOÁT"
    else:
        status="CHƯA ĐỦ DỮ LIỆU"
        stamp="KHÔNG PHÁT HÀNH – THIẾU DỮ LIỆU"

    return {
        "ReportStatus":status,"ReportStamp":stamp,"ReportCoverage":coverage,
        "CoreMissingCount":len(missing),"CoreMissing":", ".join(missing),
        "DataAgeDays":age_days,"QualityWarnings":" | ".join(critical+warnings),
        "CanExportOfficial":status=="CHÍNH THỨC","CanExportDraft":status in ("CHÍNH THỨC","BẢN NHÁP")
    }

def normalization_flags(row,cfg,prices=None):
    f=cfg.get("normalization_flags",{})
    flags=[]
    roe=n(row.get("ROE_Used")); nroe=n(row.get("NormalizedROE_Used"))
    if roe is not None and roe>=float(f.get("roe_high",.30)):
        flags.append("ROE hiện tại rất cao; cần kiểm tra tính bền vững và khoản thu nhập bất thường.")
    if roe is not None and roe<=float(f.get("roe_low",.03)):
        flags.append("ROE hiện tại rất thấp; normalized ROE nên được xem xét riêng thay vì ngoại suy cơ học.")
    if roe is not None and nroe is not None and abs(roe-nroe)>=.05:
        flags.append(f"ROE hiện tại lệch {abs(roe-nroe):.1%} so với ROE chuẩn hóa; kết quả định giá nhạy với giả định normalization.")
    npl=n(row.get("NPL"))
    if npl is not None and npl>=float(f.get("npl_high",.03)):
        flags.append("NPL ở mức cao; cần kiểm tra nợ nhóm 2, coverage và khả năng clean-up book value.")
    car=n(row.get("CAR"))
    if car is not None and car<float(f.get("car_low",.10)):
        flags.append("CAR thấp; tăng trưởng hoặc M&A có thể phát sinh nhu cầu bổ sung vốn.")
    pb=n(row.get("PB_Current")); jpb=n(row.get("JustifiedPB"))
    if pb is not None and jpb is not None and pb>jpb*(1+float(f.get("pb_above_justified_buffer",.15))):
        flags.append("P/B thị trường cao đáng kể so với P/B hợp lý; biên an toàn định giá hạn chế.")
    if prices is not None and len(prices):
        try:
            p=prices.copy()
            p=p[p["Ticker"].astype(str).eq(str(row.get("Ticker")))]
            p["Date"]=pd.to_datetime(p["Date"],errors="coerce"); p["Close"]=pd.to_numeric(p["Close"],errors="coerce")
            p=p.dropna().sort_values("Date")
            if len(p)>=2:
                cutoff=p["Date"].max()-pd.Timedelta(days=365)
                q=p[p["Date"]>=cutoff]
                if len(q)>=2 and q.iloc[0]["Close"]:
                    move=q.iloc[-1]["Close"]/q.iloc[0]["Close"]-1
                    if abs(move)>=float(f.get("price_move_alert",.35)):
                        flags.append(f"Giá cổ phiếu biến động {move:+.1%} trong khoảng 12 tháng; cần kiểm tra mức tái định giá đã phản ánh vào market price.")
        except Exception:pass
    if not flags: flags=["Không phát hiện cảnh báo normalization trọng yếu theo ngưỡng tự động; vẫn cần rà soát analyst trước phát hành."]
    return flags
