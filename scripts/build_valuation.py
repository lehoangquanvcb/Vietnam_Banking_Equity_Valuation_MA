from pathlib import Path
import json, math, re
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"; OUT=DATA/"model_outputs"; OUT.mkdir(parents=True,exist_ok=True)
CFG=json.loads((ROOT/"config/model_config.json").read_text(encoding="utf-8"))


def load_csv(path):
    try:return pd.read_csv(path)
    except Exception:return pd.DataFrame()

snap=load_csv(DATA/"bank_snapshot.csv")
groups=load_csv(ROOT/"config/bank_groups.csv")
ass=load_csv(ROOT/"config/valuation_assumptions.csv")
hist=load_csv(DATA/"bank_history_long.csv")
precedents=load_csv(ROOT/"config/transaction_precedents.csv")
market_intel=load_csv(ROOT/"config/market_intelligence.csv")

if snap.empty:
    pd.DataFrame().to_csv(OUT/"valuation_summary.csv",index=False)
    pd.DataFrame().to_csv(OUT/"valuation_methods.csv",index=False)
    pd.DataFrame().to_csv(OUT/"mna_baseline.csv",index=False)
    (OUT/"summary.json").write_text(json.dumps({"status":"NO_BANK_DATA"},indent=2),encoding="utf-8")
    raise SystemExit(0)

snap["Ticker"]=snap["Ticker"].astype(str).str.upper()
d=snap.merge(groups,on="Ticker",how="left").merge(ass,on="Ticker",how="left",suffixes=("","_Ass"))
numcols=["Price","PB","PE","ROE","ROA","NIM","NPL","CAR","CIR","LDR","CASA","EPS","BVPS","TotalAssets","GrossLoans","CustomerDeposits","Equity","TangibleEquity","NPAT","NetInterestIncome","OperatingIncome","ProvisionExpense","Beta","SizePremium","LongTermGrowth","NormalizedROE","PayoutRatio"]
for c in numcols:
    if c in d.columns:d[c]=pd.to_numeric(d[c],errors="coerce")

# Derived accounting / market measures.
d["ROE_Calc"]=d["NPAT"]/d["Equity"]
d["ROE_Used"]=d["ROE"].where(d["ROE"].notna(),d["ROE_Calc"])
d["ROE_Used"]=d["ROE_Used"].clip(-0.20,0.60)
# Infer shares from equity/BVPS first; NPAT/EPS second.
d["Shares"] = np.where((d["BVPS"]>0)&d["Equity"].notna(),d["Equity"]/d["BVPS"],np.nan)
mask=d["Shares"].isna()&(d["EPS"].abs()>0)&d["NPAT"].notna(); d.loc[mask,"Shares"]=d.loc[mask,"NPAT"]/d.loc[mask,"EPS"]
d["BVPS_Calc"]=d["Equity"]/d["Shares"]
d["BVPS_Used"]=d["BVPS"].where(d["BVPS"].notna(),d["BVPS_Calc"])
d["TBVPS"]=d["TangibleEquity"]/d["Shares"]
d["PB_Current"]=d["PB"].where(d["PB"].notna(),d["Price"]/d["BVPS_Used"])
d["PTBV_Current"]=d["Price"]/d["TBVPS"]
d["PE_Current"]=d["PE"].where(d["PE"].notna(),d["Price"]/d["EPS"])

# Cost of equity and normalized ROE.
d["Beta_Used"]=d["Beta"].fillna(CFG["default_beta"])
d["SizePremium_Used"]=d["SizePremium"].fillna(CFG["default_size_premium"])
d["COE"]=CFG["risk_free_rate"]+d["Beta_Used"]*CFG["equity_risk_premium"]+d["SizePremium_Used"]
d["LTG"]=d["LongTermGrowth"].fillna(CFG["long_term_growth"])
d["Payout_Used"]=d["PayoutRatio"].fillna(CFG["payout_ratio"])
d["NormalizedROE_Used"]=d["NormalizedROE"].where(d["NormalizedROE"].notna(),d["ROE_Used"]*(1-CFG["roe_mean_reversion"])+CFG["normalized_roe_anchor"]*CFG["roe_mean_reversion"])

# Justified P/B.
den=(d["COE"]-d["LTG"]).replace(0,np.nan)
d["JustifiedPB"]=(d["NormalizedROE_Used"]-d["LTG"])/den
d["JustifiedPB"]=d["JustifiedPB"].clip(CFG["justified_pb_floor"],CFG["justified_pb_cap"])
d["Fair_JustifiedPB"]=d["JustifiedPB"]*d["BVPS_Used"]

# Peer quality-adjusted P/B.
peer=d.groupby("PeerGroup").agg(PeerPBMedian=("PB_Current","median"),PeerROEMedian=("ROE_Used","median"),PeerPTBVMedian=("PTBV_Current","median")).reset_index()
d=d.merge(peer,on="PeerGroup",how="left")
ratio=(d["ROE_Used"]/d["PeerROEMedian"]).clip(0.4,2.0)
d["PeerPB_Adjusted"]=d["PeerPBMedian"]*(ratio**CFG["peer_pb_roe_elasticity"])
d["Fair_PeerPB"]=d["PeerPB_Adjusted"]*d["BVPS_Used"]

# Historical P/B from Vnstock ratio history when available.
hist_pb=pd.DataFrame(columns=["Ticker","HistoricalPBMedian"])
if len(hist):
    h=hist.copy(); h["Metric"]=h["Metric"].astype(str); h["Value"]=pd.to_numeric(h["Value"],errors="coerce")
    h=h[(h.Metric=="PB")&h.Value.between(.05,10)]
    if len(h): hist_pb=h.groupby("Ticker",as_index=False).tail(12).groupby("Ticker",as_index=False).Value.median().rename(columns={"Value":"HistoricalPBMedian"})
d=d.merge(hist_pb,on="Ticker",how="left")
d["Fair_HistoricalPB"]=d["HistoricalPBMedian"]*d["BVPS_Used"]

# Residual income valuation per share.
def residual_income(row):
    bv=row.get("BVPS_Used"); roe0=row.get("ROE_Used"); roeN=row.get("NormalizedROE_Used"); coe=row.get("COE"); g=row.get("LTG"); payout=row.get("Payout_Used")
    vals=[bv,roe0,roeN,coe,g,payout]
    if any(pd.isna(v) for v in vals) or bv<=0 or coe<=g+.005:return np.nan
    years=int(CFG["forecast_years"]); cur_bv=float(bv); pv=0.0
    for t in range(1,years+1):
        w=t/years; roe=float(roe0)*(1-w)+float(roeN)*w
        ri=(roe-float(coe))*cur_bv
        pv += ri/((1+float(coe))**t)
        earnings=roe*cur_bv; cur_bv += earnings*(1-float(payout))
    terminal_ri=(float(roeN)-float(coe))*cur_bv
    tv=terminal_ri*(1+float(g))/(float(coe)-float(g))
    pv += tv/((1+float(coe))**years)
    return float(bv)+pv

d["Fair_ResidualIncome"]=d.apply(residual_income,axis=1)
# Guardrail absurd outputs from sparse data.
d["Fair_ResidualIncome"]=np.where((d["Fair_ResidualIncome"]>0)&(d["Fair_ResidualIncome"]<d["BVPS_Used"]*8),d["Fair_ResidualIncome"],np.nan)

# Blend available methods, renormalizing weights.
weights=CFG["valuation_weights"]
method_cols={"ResidualIncome":"Fair_ResidualIncome","JustifiedPB":"Fair_JustifiedPB","PeerPB":"Fair_PeerPB","HistoricalPB":"Fair_HistoricalPB"}
def blend(r):
    total=0; wsum=0
    for m,c in method_cols.items():
        v=r.get(c); w=float(weights.get(m,0))
        if pd.notna(v) and v>0: total+=w*v; wsum+=w
    return total/wsum if wsum else np.nan

d["FairValue_Base"]=d.apply(blend,axis=1)
d["FairValue_Bear"]=d["FairValue_Base"]*0.85
d["FairValue_Bull"]=d["FairValue_Base"]*1.15
d["Upside_Base"]=d["FairValue_Base"]/d["Price"]-1

# Strategic / M&A market intelligence is deliberately separated from fundamental fair value.
# It may contain user-supplied or public deal intelligence and must never overwrite FairValue_Base.
if not market_intel.empty and "Ticker" in market_intel.columns:
    mi=market_intel.copy()
    mi["Ticker"]=mi["Ticker"].astype(str).str.upper()
    for c in ["LowPrice","HighPrice","ReferenceStake"]:
        if c in mi: mi[c]=pd.to_numeric(mi[c],errors="coerce")
    keep=[c for c in ["Ticker","IntelligenceType","LowPrice","HighPrice","ReferenceStake","AsOfDate","Source","Confidence","Note"] if c in mi]
    mi=mi[keep].drop_duplicates("Ticker",keep="last")
    mi=mi.rename(columns={"LowPrice":"StrategicPriceLow","HighPrice":"StrategicPriceHigh","ReferenceStake":"StrategicReferenceStake","AsOfDate":"StrategicAsOfDate","Source":"StrategicSource","Confidence":"StrategicConfidence","Note":"StrategicNote","IntelligenceType":"StrategicIntelligenceType"})
    d=d.merge(mi,on="Ticker",how="left")
else:
    for c in ["StrategicPriceLow","StrategicPriceHigh","StrategicReferenceStake","StrategicAsOfDate","StrategicSource","StrategicConfidence","StrategicNote","StrategicIntelligenceType"]: d[c]=np.nan

d["StrategicPriceMid"]=(d["StrategicPriceLow"]+d["StrategicPriceHigh"])/2
d["StrategicPremiumLow"]=d["StrategicPriceLow"]/d["Price"]-1
d["StrategicPremiumHigh"]=d["StrategicPriceHigh"]/d["Price"]-1
d["StrategicVsFundamentalLow"]=d["StrategicPriceLow"]/d["FairValue_Base"]-1
d["StrategicVsFundamentalHigh"]=d["StrategicPriceHigh"]/d["FairValue_Base"]-1

# Transaction-value curve: larger strategic blocks can command higher scarcity/control value.
# When a directly observed/intelligence range exists, interpolate within that range by stake size.
def strategic_block_price(row, stake):
    lo=row.get("StrategicPriceLow"); hi=row.get("StrategicPriceHigh"); ref=row.get("StrategicReferenceStake")
    if pd.isna(lo) or pd.isna(hi): return np.nan
    ref=float(ref) if pd.notna(ref) and ref>0 else .325
    # 5% block starts near low end; reference/control block approaches high end.
    x=np.clip((float(stake)-.05)/max(ref-.05,.01),0,1)
    return float(lo)+(float(hi)-float(lo))*(x**0.75)
for stake,label in [(.05,"5pct"),(.10,"10pct"),(.20,"20pct"),(.325,"32_5pct"),(.51,"51pct")]:
    d[f"StrategicPrice_{label}"]=d.apply(lambda r: strategic_block_price(r,stake),axis=1)


# Growth intelligence from historical Vnstock series.
def latest_growth(metric, periods_back=4):
    if hist.empty:
        return pd.DataFrame(columns=["Ticker", f"{metric}_Growth"])
    h=hist[hist["Metric"].astype(str).eq(metric)].copy()
    if h.empty:
        return pd.DataFrame(columns=["Ticker", f"{metric}_Growth"])
    h["Value"]=pd.to_numeric(h["Value"],errors="coerce")
    h=h.dropna(subset=["Value"])
    h["_pk"]=h["Period"].astype(str).map(lambda s: tuple(int(x) for x in re.findall(r"\d+",s)[:2]) if re.findall(r"\d+",s) else (0,))
    rows=[]
    for t,g in h.groupby("Ticker"):
        g=g.sort_values("_pk")
        vals=g["Value"].dropna().tolist()
        if len(vals)>=2:
            back=vals[-(periods_back+1)] if len(vals)>periods_back else vals[0]
            cur=vals[-1]
            growth=(cur/back-1) if back not in (0,None) and pd.notna(back) else np.nan
            rows.append({"Ticker":t,f"{metric}_Growth":growth})
    return pd.DataFrame(rows)

for metric in ["TotalAssets","GrossLoans","CustomerDeposits","NPAT","NetInterestIncome"]:
    g=latest_growth(metric,4)
    if len(g): d=d.merge(g,on="Ticker",how="left")
    elif f"{metric}_Growth" not in d: d[f"{metric}_Growth"]=np.nan

# Six-pillar bank scorecard.
def pct_score(s,higher=True):
    x=pd.to_numeric(s,errors="coerce")
    r=x.rank(pct=True,method="average")
    return (r if higher else 1-r)*100

def mean_available(parts):
    if not parts:
        return pd.Series(np.nan,index=d.index)
    return pd.concat(parts,axis=1).mean(axis=1,skipna=True)

profit_parts=[
    pct_score(d["ROE_Used"],True),
    pct_score(d["ROA"],True),
    pct_score(d["NIM"],True),
]
growth_parts=[
    pct_score(d["GrossLoans_Growth"],True),
    pct_score(d["CustomerDeposits_Growth"],True),
    pct_score(d["NPAT_Growth"],True),
]
asset_parts=[
    pct_score(d["NPL"],False),
]
if "ProvisionExpense" in d:
    asset_parts.append(pct_score(d["ProvisionExpense"].abs()/d["GrossLoans"].replace(0,np.nan),False))

funding_parts=[
    pct_score(d["CASA"],True) if "CASA" in d else pd.Series(np.nan,index=d.index),
    pct_score((d["LDR"]-0.85).abs(),False),
]
capital_parts=[
    pct_score(d["CAR"],True),
    pct_score(d["Equity"]/d["TotalAssets"].replace(0,np.nan),True),
]
valuation_parts=[
    pct_score(d["Upside_Base"],True),
    pct_score(d["PB_Current"],False),
    pct_score(d["PE_Current"],False),
]

d["ProfitabilityScore"]=mean_available(profit_parts)
d["GrowthScore"]=mean_available(growth_parts)
d["AssetQualityScore"]=mean_available(asset_parts)
d["FundingScore"]=mean_available(funding_parts)
d["CapitalScore"]=mean_available(capital_parts)
d["ValuationScore"]=mean_available(valuation_parts)

sw=CFG.get("score_weights",{})
weights_score={
    "ProfitabilityScore":float(sw.get("profitability",.22)),
    "GrowthScore":float(sw.get("growth",.15)),
    "AssetQualityScore":float(sw.get("asset_quality",.18)),
    "FundingScore":float(sw.get("funding",.12)),
    "CapitalScore":float(sw.get("capital",.13)),
    "ValuationScore":float(sw.get("valuation",.20)),
}
num_score=0.0
den_score=0.0
for c,w in weights_score.items():
    valid=d[c].notna().astype(float)
    num_score += d[c].fillna(0)*w
    den_score += valid*w
d["InvestmentScore"]=num_score/den_score.replace(0,np.nan)
d["FundamentalScore"]=mean_available([
    d["ProfitabilityScore"],d["GrowthScore"],d["AssetQualityScore"],d["FundingScore"],d["CapitalScore"]
])

def view_score(x):
    if pd.isna(x): return "CHƯA ĐỦ DỮ LIỆU"
    if x>=75:return "RẤT TỐT"
    if x>=60:return "TỐT"
    if x>=45:return "TRUNG BÌNH"
    return "YẾU"
d["FundamentalView"]=d["FundamentalScore"].map(view_score)
d["InvestmentView"]=d["InvestmentScore"].map(view_score)

# Quality / valuation scores.
def pct_score(s, higher=True):
    x=pd.to_numeric(s,errors="coerce"); r=x.rank(pct=True)
    return (r if higher else 1-r)*100
quality_parts=[]
for col,higher in [("ROE_Used",True),("ROA",True),("NIM",True),("NPL",False),("CAR",True),("CIR",False)]:
    if col in d: quality_parts.append(pct_score(d[col],higher))
d["QualityScore"]=pd.concat(quality_parts,axis=1).mean(axis=1) if quality_parts else np.nan
d["ValueScore"]=pct_score(d["Upside_Base"],True)
d["RiskScore"]=(100-pct_score(d["NPL"],True)).fillna(50) if "NPL" in d else 50
d["CompositeScore"]=d["InvestmentScore"].where(d["InvestmentScore"].notna(),0.45*d["ValueScore"]+0.45*d["QualityScore"]+0.10*d["RiskScore"])
d["ValuationView"]=pd.cut(d["Upside_Base"],[-np.inf,-.10,.05,.20,np.inf],labels=["EXPENSIVE","FAIR","ATTRACTIVE","VERY_ATTRACTIVE"])
d["QualityView"]=pd.cut(d["QualityScore"],[-np.inf,35,65,np.inf],labels=["LOW","MODERATE","HIGH"])


# Report quality gate + normalization alerts.
try:
    from scripts.quality_engine import assess_report_quality, normalization_flags
except Exception:
    from quality_engine import assess_report_quality, normalization_flags

quality_rows=[]
for _,rr in d.iterrows():
    qa=assess_report_quality(rr.to_dict(),CFG,hist,None)
    flags=normalization_flags(rr.to_dict(),CFG,None)
    quality_rows.append({**qa,"NormalizationFlags":" | ".join(flags)})
qdf=pd.DataFrame(quality_rows,index=d.index)
for c in qdf.columns:
    d[c]=qdf[c].values

# Method output.
method_rows=[]
for _,r in d.iterrows():
    for name,col in method_cols.items():
        method_rows.append({"Ticker":r.Ticker,"Method":name,"FairValuePerShare":r.get(col),"MarketPrice":r.get("Price"),"Upside":(r.get(col)/r.get("Price")-1) if pd.notna(r.get(col)) and pd.notna(r.get("Price")) and r.get("Price") else np.nan,"DataType":"CALCULATED"})
methods=pd.DataFrame(method_rows)

# Baseline M&A / restructuring view — scenario assumptions, not observed transaction prices.
def pv_synergy(r):
    coe=float(r.COE) if pd.notna(r.COE) else CFG["mna_hurdle_rate"]
    g=min(float(CFG["mna_synergy_growth"]),coe-.01)
    op=float(r.OperatingIncome) if pd.notna(r.OperatingIncome) else 0.0
    ni=float(r.NetInterestIncome) if pd.notna(r.NetInterestIncome) else op
    # Without explicit opex, use CIR * operating income if available.
    opex=(float(r.CIR)*op) if pd.notna(r.CIR) and op else 0.0
    annual=(opex*CFG["annual_cost_synergy_pct_target_opex"] + ni*CFG["annual_revenue_synergy_pct_target_income"])*(1-CFG["tax_rate"])*CFG["synergy_ramp"]
    return annual*(1+g)/(coe-g) if annual>0 and coe>g else 0.0

mrows=[]
for _,r in d.iterrows():
    shares=r.Shares if pd.notna(r.Shares) and r.Shares>0 else np.nan
    standalone_equity=(r.FairValue_Base*shares) if pd.notna(r.FairValue_Base) and pd.notna(shares) else np.nan
    credit_mark=(r.GrossLoans*CFG["credit_mark_pct_gross_loans"]) if pd.notna(r.GrossLoans) else 0.0
    intang=(r.CustomerDeposits*CFG["identifiable_intangible_pct_customer_deposits"]) if pd.notna(r.CustomerDeposits) else 0.0
    adj_net=(r.TangibleEquity if pd.notna(r.TangibleEquity) else r.Equity) - credit_mark + intang if pd.notna(r.Equity) else np.nan
    synergy=pv_synergy(r)
    integration=(r.Equity*CFG["integration_cost_pct_equity"]) if pd.notna(r.Equity) else 0.0
    consideration=standalone_equity*(1+CFG["control_premium"]) + synergy - integration if pd.notna(standalone_equity) else np.nan
    goodwill=consideration-adj_net if pd.notna(consideration) and pd.notna(adj_net) else np.nan
    offer_ps=consideration/shares if pd.notna(consideration) and pd.notna(shares) and shares else np.nan
    mrows.append({
        "Ticker":r.Ticker,"StandaloneEquityValue":standalone_equity,"ControlPremium":CFG["control_premium"],"PV_Synergies":synergy,
        "IntegrationCost":integration,"CreditMark":credit_mark,"IdentifiableIntangibles":intang,"AdjustedNetAssets":adj_net,
        "IllustrativeConsideration":consideration,"IllustrativeOfferPerShare":offer_ps,
        "ImpliedPB":consideration/r.Equity if pd.notna(consideration) and pd.notna(r.Equity) and r.Equity else np.nan,
        "ImpliedPTBV":consideration/r.TangibleEquity if pd.notna(consideration) and pd.notna(r.TangibleEquity) and r.TangibleEquity else np.nan,
        "Goodwill":goodwill,"DataType":"SCENARIO_ASSUMPTION"
    })
mna=pd.DataFrame(mrows)

# Restructuring-adjusted book value.
d["ExtraProvision_Restructuring"] = d["GrossLoans"].fillna(0)*CFG["restructuring_extra_provision_pct_loans"]
d["NPLHaircut_Restructuring"] = d["GrossLoans"].fillna(0)*d["NPL"].fillna(0)*CFG["restructuring_npl_haircut"]
d["AdjustedEquity_Restructuring"] = d["Equity"]-d["ExtraProvision_Restructuring"]-d["NPLHaircut_Restructuring"]
d["AdjustedBVPS_Restructuring"] = d["AdjustedEquity_Restructuring"]/d["Shares"]

# Data coverage.
key=["Price","ROE_Used","BVPS_Used","Equity","NPAT","NPL","CAR","NIM"]
d["DataCoverage"]=d[key].notna().sum(axis=1)/len(key)

summary_cols=["Ticker","PeerGroup","OwnershipType","Price","PB_Current","PTBV_Current","PE_Current","ROE_Used","ROA","NIM","NPL","CAR","CIR","LDR","CASA","BVPS_Used","TBVPS","COE","LTG","NormalizedROE_Used","JustifiedPB","PeerPB_Adjusted","HistoricalPBMedian","Fair_ResidualIncome","Fair_JustifiedPB","Fair_PeerPB","Fair_HistoricalPB","FairValue_Bear","FairValue_Base","FairValue_Bull","Upside_Base","ProfitabilityScore","GrowthScore","AssetQualityScore","FundingScore","CapitalScore","ValuationScore","FundamentalScore","InvestmentScore","FundamentalView","InvestmentView","QualityScore","ValueScore","RiskScore","CompositeScore","ValuationView","QualityView","DataCoverage","TotalAssets_Growth","GrossLoans_Growth","CustomerDeposits_Growth","NPAT_Growth","NetInterestIncome_Growth","ReportStatus","ReportStamp","ReportCoverage","CoreMissingCount","CoreMissing","DataAgeDays","QualityWarnings","CanExportOfficial","CanExportDraft","NormalizationFlags","TotalAssets","Equity","TangibleEquity","NPAT","NetInterestIncome","OperatingIncome","ProvisionExpense","GrossLoans","CustomerDeposits","Shares","RetrievedAt","DataType","SourceMode","StrategicIntelligenceType","StrategicPriceLow","StrategicPriceHigh","StrategicPriceMid","StrategicReferenceStake","StrategicAsOfDate","StrategicSource","StrategicConfidence","StrategicNote","StrategicPremiumLow","StrategicPremiumHigh","StrategicVsFundamentalLow","StrategicVsFundamentalHigh","StrategicPrice_5pct","StrategicPrice_10pct","StrategicPrice_20pct","StrategicPrice_32_5pct","StrategicPrice_51pct"]
for c in summary_cols:
    if c not in d:d[c]=np.nan
summary=d[summary_cols].sort_values("CompositeScore",ascending=False)
summary.to_csv(OUT/"valuation_summary.csv",index=False,encoding="utf-8-sig")
methods.to_csv(OUT/"valuation_methods.csv",index=False,encoding="utf-8-sig")
mna.to_csv(OUT/"mna_baseline.csv",index=False,encoding="utf-8-sig")

# Peer summary.
peer_summary=summary.groupby("PeerGroup",dropna=False).agg(
    Banks=("Ticker","count"),MedianPB=("PB_Current","median"),MedianPTBV=("PTBV_Current","median"),MedianPE=("PE_Current","median"),
    MedianROE=("ROE_Used","median"),MedianROA=("ROA","median"),MedianNIM=("NIM","median"),MedianNPL=("NPL","median"),
    MedianCAR=("CAR","median"),MedianCIR=("CIR","median"),MedianLDR=("LDR","median"),MedianCASA=("CASA","median"),
    MedianUpside=("Upside_Base","median"),MedianInvestmentScore=("InvestmentScore","median")
).reset_index()
peer_summary.to_csv(OUT/"peer_summary.csv",index=False,encoding="utf-8-sig")

meta={
    "status":"OK","banks":int(len(summary)),"banks_with_fair_value":int(summary.FairValue_Base.notna().sum()),
    "banks_with_price":int(summary.Price.notna().sum()),"median_upside":float(summary.Upside_Base.median()) if summary.Upside_Base.notna().any() else None,
    "methodology":["Residual Income","Justified P/B","Peer P/B","Historical P/B"],
    "mna_methodology":["Standalone value","Control premium","PV synergies","PPA / adjusted net assets","Goodwill","Restructuring-adjusted equity"]
}
(OUT/"summary.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
print(summary[["Ticker","Price","PB_Current","ROE_Used","FairValue_Base","Upside_Base","CompositeScore"]].to_string(index=False))
