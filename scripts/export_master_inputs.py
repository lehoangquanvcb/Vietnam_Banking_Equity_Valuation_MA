from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
MASTER=ROOT/"Vietnam_Banking_Equity_Valuation_MA_Master.xlsx"
if not MASTER.exists():
    print("Master not found; keeping config files.")
    raise SystemExit(0)

cfg_path=ROOT/"config/model_config.json"
cfg=json.loads(cfg_path.read_text(encoding="utf-8"))

try:
    v=pd.read_excel(MASTER,sheet_name="VALUATION_ASSUMPTIONS",header=2)
    val={str(r["Parameter"]).strip():r["Value"] for _,r in v.iterrows() if pd.notna(r.get("Parameter"))}
    mapping={
        "Risk-free rate":"risk_free_rate","Equity risk premium":"equity_risk_premium","Default beta":"default_beta",
        "Default size premium":"default_size_premium","Long-term growth":"long_term_growth",
        "Normalized ROE anchor":"normalized_roe_anchor","Forecast years":"forecast_years","Payout ratio":"payout_ratio"
    }
    for k,j in mapping.items():
        if k in val and pd.notna(val[k]): cfg[j]=float(val[k]) if j!="forecast_years" else int(val[k])
except Exception as exc:
    print("VALUATION_ASSUMPTIONS export skipped:",exc)

try:
    m=pd.read_excel(MASTER,sheet_name="M&A_ASSUMPTIONS",header=2)
    val={str(r["Parameter"]).strip():r["Value"] for _,r in m.iterrows() if pd.notna(r.get("Parameter"))}
    mapping={
        "Control premium":"control_premium","Cost synergy / target opex":"annual_cost_synergy_pct_target_opex",
        "Revenue synergy / target income":"annual_revenue_synergy_pct_target_income","Synergy ramp":"synergy_ramp",
        "Integration cost / target equity":"integration_cost_pct_equity","Credit mark / gross loans":"credit_mark_pct_gross_loans",
        "Identifiable intangible / deposits":"identifiable_intangible_pct_customer_deposits","M&A hurdle rate":"mna_hurdle_rate",
        "Synergy LT growth":"mna_synergy_growth","Tax rate":"tax_rate"
    }
    for k,j in mapping.items():
        if k in val and pd.notna(val[k]): cfg[j]=float(val[k])
except Exception as exc:
    print("M&A_ASSUMPTIONS export skipped:",exc)


try:
    s=pd.read_excel(MASTER,sheet_name="TRONG_SO_CHAM_DIEM",header=2)
    name_map={
        "Sinh lời":"profitability","Tăng trưởng":"growth","Chất lượng tài sản":"asset_quality",
        "Nguồn vốn":"funding","An toàn vốn":"capital","Định giá":"valuation"
    }
    sw=cfg.get("score_weights",{}).copy()
    for _,r in s.iterrows():
        name=str(r.get("Trụ cột","")).strip()
        val=r.get("Trọng số")
        if name in name_map and pd.notna(val):
            sw[name_map[name]]=float(val)
    if sw:
        total=sum(sw.values())
        if total>0:
            sw={k:v/total for k,v in sw.items()}
        cfg["score_weights"]=sw
except Exception as exc:
    print("TRONG_SO_CHAM_DIEM export skipped:",exc)

try:
    r=pd.read_excel(MASTER,sheet_name="CAU_HINH_BAO_CAO",header=2)
    for _,row in r.iterrows():
        if str(row.get("Tham số","")).strip()=="Số trang mục tiêu" and pd.notna(row.get("Giá trị")):
            cfg["report_pages_target"]=int(row.get("Giá trị"))
except Exception as exc:
    print("CAU_HINH_BAO_CAO export skipped:",exc)


try:
    q=pd.read_excel(MASTER,sheet_name="KIEM_SOAT_PHAT_HANH",header=2)
    vals={str(r.get("Tham số","")).strip():r.get("Ngưỡng") for _,r in q.iterrows() if pd.notna(r.get("Tham số"))}
    gate=cfg.get("report_quality_gate",{}).copy()
    fmap={
        "Độ phủ tối thiểu - Chính thức":"official_min_coverage",
        "Độ phủ tối thiểu - Bản nháp":"draft_min_coverage",
        "Số chỉ tiêu lõi thiếu tối đa - Chính thức":"max_core_missing_official",
        "Số chỉ tiêu lõi thiếu tối đa - Bản nháp":"max_core_missing_draft",
        "Tuổi dữ liệu cảnh báo":"max_data_age_days",
    }
    for k,j in fmap.items():
        if k in vals and pd.notna(vals[k]):
            gate[j]=int(vals[k]) if j in ("max_core_missing_official","max_core_missing_draft","max_data_age_days") else float(vals[k])
    cfg["report_quality_gate"]=gate
    nf=cfg.get("normalization_flags",{}).copy()
    nmap={"ROE cao cần normalization":"roe_high","NPL cao cần lưu ý":"npl_high","CAR thấp cần lưu ý":"car_low"}
    for k,j in nmap.items():
        if k in vals and pd.notna(vals[k]): nf[j]=float(vals[k])
    cfg["normalization_flags"]=nf
except Exception as exc:
    print("KIEM_SOAT_PHAT_HANH export skipped:",exc)

cfg_path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding="utf-8")


try:
    b=pd.read_excel(MASTER,sheet_name="BANK_ASSUMPTIONS",header=2)
    rename={
        "Size Premium":"SizePremium","LT Growth":"LongTermGrowth",
        "Normalized ROE Override":"NormalizedROE","Payout Ratio":"PayoutRatio"
    }
    b=b.rename(columns=rename)
    keep=["Ticker","Beta","SizePremium","LongTermGrowth","NormalizedROE","PayoutRatio","Note"]
    for c in keep:
        if c not in b.columns:b[c]=None
    b=b[keep]
    b=b[b["Ticker"].notna()]
    b.to_csv(ROOT/"config/valuation_assumptions.csv",index=False,encoding="utf-8-sig")
except Exception as exc:
    print("BANK_ASSUMPTIONS export skipped:",exc)

try:
    p=pd.read_excel(MASTER,sheet_name="DEAL_PRECEDENTS",header=2)
    rename={
        "Announcement Date":"AnnouncementDate","Stake %":"StakePct","Deal Value (VND bn)":"DealValueVND_bn",
        "Implied P/B":"ImpliedPB","Implied P/TBV":"ImpliedPTBV","Control Premium %":"ControlPremiumPct",
        "Target ROE":"TargetROE","Target NPL":"TargetNPL","Strategic Rationale":"StrategicRationale",
        "Source URL":"SourceURL","Data Type":"DataType"
    }
    p=p.rename(columns=rename)
    keep=["AnnouncementDate","Acquirer","Target","Country","StakePct","DealValueVND_bn","ImpliedPB","ImpliedPTBV","ControlPremiumPct","TargetROE","TargetNPL","StrategicRationale","SourceURL","DataType"]
    for c in keep:
        if c not in p.columns:p[c]=None
    p=p[keep]
    # Keep only rows where at least acquirer/target/source is entered.
    p=p[p[["Acquirer","Target","SourceURL"]].notna().any(axis=1)]
    p.to_csv(ROOT/"config/transaction_precedents.csv",index=False,encoding="utf-8-sig")
except Exception as exc:
    print("DEAL_PRECEDENTS export skipped:",exc)

print("Master assumptions exported to config.")
