
from pathlib import Path
import json
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from scripts.narrative_engine import (
    executive_summary,business_profile,profitability_text,asset_quality_text,
    funding_text,capital_text,valuation_text,catalysts_risks,mna_text
)
from scripts.report_engine import generate_pdf_bytes, generate_docx_bytes
from scripts.credit_rating_engine import build_credit_rating, rating_table, FACTOR_LABELS, DESCRIPTOR_6
from scripts.credit_rating_report import generate_credit_rating_pdf, generate_credit_rating_docx
from scripts.quality_engine import assess_report_quality, normalization_flags
from scripts.strategic_case import load_research, strategic_reasonableness, reasonableness_conclusion, all_bank_means

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"; OUT=DATA/"model_outputs"

st.set_page_config(
    page_title="Nền tảng Phân tích, Định giá & M&A Ngân hàng Việt Nam",
    page_icon="🏦",layout="wide"
)

st.markdown("""
<style>
.block-container{padding-top:1.1rem;padding-bottom:2rem;max-width:1500px}
[data-testid="stSidebar"]{min-width:310px;max-width:310px}
h1{font-size:2rem!important;letter-spacing:-.4px;color:#0F2747}
h2{font-size:1.48rem!important;color:#0F2747}
h3{font-size:1.18rem!important;color:#163A5F}
[data-testid="stMetricValue"]{font-size:1.38rem}
[data-testid="stMetricLabel"]{font-weight:700}
div[data-testid="stMetric"]{padding:.35rem .25rem}
div[data-testid="stTabs"] button{white-space:nowrap;font-weight:650}
.analysis-box{border-left:4px solid #0F2747;padding:.75rem 1rem;background:#F6F8FB;border-radius:4px;margin:.4rem 0 .8rem 0}
.muted{color:#667085;font-size:.86rem}
.report-box{border:1px solid #D0D5DD;padding:1rem;border-radius:8px;background:#FCFCFD}
</style>
""",unsafe_allow_html=True)

def csv(path):
    try:return pd.read_csv(path)
    except Exception:return pd.DataFrame()
def js(path):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return {}
def num(x):
    try:
        v=float(x); return v if np.isfinite(v) else None
    except:return None
def pct(x): return "N/A" if num(x) is None else f"{num(x):.1%}"
def money(x): return "N/A" if num(x) is None else f"{num(x)*1000:,.0f} đồng/cp"
def mult(x,d=2): return "N/A" if num(x) is None else f"{num(x):.{d}f}x"
def fmtbn(x): return "N/A" if num(x) is None else f"{num(x)/1e9:,.0f} tỷ"
def safe(df): return df.copy().replace([np.inf,-np.inf],np.nan)


# ===== Nhãn hiển thị tiếng Việt (chỉ presentation layer; không đổi schema dữ liệu) =====
METRIC_VI = {
    "TotalAssets":"Tổng tài sản",
    "GrossLoans":"Dư nợ khách hàng",
    "CustomerDeposits":"Tiền gửi khách hàng",
    "Equity":"Vốn chủ sở hữu",
    "TangibleEquity":"Vốn chủ sở hữu hữu hình",
    "NPAT":"Lợi nhuận sau thuế",
    "NetInterestIncome":"Thu nhập lãi thuần",
    "OperatingIncome":"Tổng thu nhập hoạt động",
    "ProvisionExpense":"Chi phí dự phòng",
    "ROE":"ROE",
    "ROA":"ROA",
    "NIM":"NIM",
    "NPL":"Tỷ lệ nợ xấu (NPL)",
    "CAR":"Hệ số an toàn vốn (CAR)",
    "CIR":"Tỷ lệ chi phí/thu nhập (CIR)",
    "LDR":"Tỷ lệ cho vay/tiền gửi (LDR)",
    "CASA":"CASA",
    "PB":"P/B",
    "PE":"P/E",
}
COLUMN_VI = {
    "Ticker":"Mã ngân hàng","PeerGroup":"Nhóm ngân hàng so sánh","OwnershipType":"Hình thức sở hữu",
    "Price":"Giá thị trường","FairValue_Base":"Giá trị cơ bản","FairValue_Bear":"Kịch bản thận trọng",
    "FairValue_Bull":"Kịch bản tích cực","Upside_Base":"Chênh lệch so với thị giá",
    "PB_Current":"P/B hiện tại","PTBV_Current":"P/TBV hiện tại","PE_Current":"P/E hiện tại",
    "ROE_Used":"ROE","ROA":"ROA","NIM":"NIM","NPL":"NPL","CAR":"CAR","CASA":"CASA","CIR":"CIR","LDR":"LDR",
    "InvestmentScore":"Điểm đầu tư","InvestmentView":"Đánh giá đầu tư","DataCoverage":"Độ phủ dữ liệu",
    "TotalAssets":"Tổng tài sản","GrossLoans":"Dư nợ khách hàng","CustomerDeposits":"Tiền gửi khách hàng",
    "Equity":"Vốn chủ sở hữu","NPAT":"Lợi nhuận sau thuế","NetInterestIncome":"Thu nhập lãi thuần",
    "ProfitabilityScore":"Điểm sinh lời","GrowthScore":"Điểm tăng trưởng",
    "AssetQualityScore":"Điểm chất lượng tài sản","FundingScore":"Điểm nguồn vốn",
    "CapitalScore":"Điểm an toàn vốn","ValuationScore":"Điểm định giá",
}
PEER_GROUP_VI = {
    "State-owned large":"Ngân hàng quốc doanh quy mô lớn",
    "Private large":"Ngân hàng tư nhân quy mô lớn",
    "Private mid":"Ngân hàng tư nhân quy mô trung bình",
    "Private small":"Ngân hàng tư nhân quy mô nhỏ",
}
METHOD_VI = {
    "ResidualIncome":"Thu nhập thặng dư",
    "JustifiedPB":"P/B hợp lý",
    "PeerPB":"P/B nhóm so sánh",
    "HistoricalPB":"P/B lịch sử",
}
def metric_vi(metric):
    return METRIC_VI.get(str(metric), str(metric))
def display_df(df):
    return df.rename(columns={c:COLUMN_VI.get(c,c) for c in df.columns})
def _apply_y_padding(fig, values, percent=True):
    vals=pd.to_numeric(pd.Series(values),errors="coerce").dropna()
    if vals.empty:return
    lo=float(vals.min()); hi=float(vals.max())
    span=hi-lo
    if span<=0:
        span=max(abs(hi)*0.20,0.01 if percent else 1.0)
    pad=max(span*0.15, 0.003 if percent else abs(hi)*0.03 if hi else 1.0)
    lower=lo-pad; upper=hi+pad
    if percent and lo>=0:
        lower=max(0.0, lower)
        if lo>0 and lower==lo: lower=max(0.0,lo*0.75)
    fig.update_yaxes(range=[lower,upper])

def _period_parts(value):
    import re
    s=str(value).upper().strip()
    y=re.search(r"(20\d{2})",s)
    q=re.search(r"Q\s*([1-4])",s)
    return (int(y.group(1)) if y else 0,int(q.group(1)) if q else 0)

def _period_date(value):
    y,q=_period_parts(value)
    if y and q:return pd.Timestamp(year=y,month=(q-1)*3+1,day=1)
    if y:return pd.Timestamp(year=y,month=1,day=1)
    return pd.NaT

def _clean_history_metric(df,metric):
    x=df.copy()
    x["Value"]=pd.to_numeric(x.Value,errors="coerce")
    x=x.dropna(subset=["Value"])
    if metric in {"ROE","ROA","NIM","NPL","CAR","CIR","LDR","CASA","PB","PE"}: x=x[x.Value!=0]
    if metric=="CAR": x=x[x.Value>0]
    x["PeriodDate"]=x.Period.map(_period_date)
    x=x.dropna(subset=["PeriodDate"]).sort_values("PeriodDate")
    return x

def peer_history(metric):
    if hist.empty:return pd.DataFrame()
    x=hist[hist.Metric.astype(str).eq(str(metric))].copy()
    x=_clean_history_metric(x,metric)
    if x.empty:return pd.DataFrame()
    return x.groupby("PeriodDate",as_index=False).agg(PeerMean=("Value","mean"),BankCount=("Ticker","nunique")).sort_values("PeriodDate")

def metric_history_figure(ticker,metrics,title,percent=True):
    """Biểu đồ lịch sử trên trục thời gian thực, có benchmark bình quân 20 ngân hàng niêm yết."""
    fig=go.Figure()
    all_values=[]
    for metric in metrics:
        h=hist[(hist.Ticker.astype(str)==str(ticker)) & (hist.Metric.astype(str)==str(metric))].copy()
        h=_clean_history_metric(h,metric)
        pm=peer_history(metric)
        label=metric_vi(metric)
        if len(h):
            all_values.extend(h.Value.tolist())
            fig.add_trace(go.Scatter(
                x=h.PeriodDate,y=h.Value,mode="lines+markers",
                name=f"{ticker} - {label}",customdata=h.Period,
                hovertemplate="%{customdata}<br>%{y}<extra></extra>"
            ))
        if len(pm):
            all_values.extend(pm.PeerMean.tolist())
            fig.add_trace(go.Scatter(
                x=pm.PeriodDate,y=pm.PeerMean,mode="lines",
                line=dict(dash="dash"),
                name=f"Bình quân 20 NH - {label}",
                hovertemplate="%{x|%Y}<br>%{y}<extra></extra>"
            ))
    fig.update_layout(
        title=title+" · so với bình quân 20 ngân hàng niêm yết",
        height=390,legend=dict(orientation="h",y=-.22),
        margin=dict(t=55,b=75)
    )
    fig.update_xaxes(type="date",dtick="M12",tickformat="%Y",title="")
    if percent: fig.update_yaxes(tickformat=".1%")
    _apply_y_padding(fig,all_values,percent=percent)
    return fig

def relative_price_figure(ticker):
    p=prices.copy()
    if p.empty:return go.Figure()
    p["Date"]=pd.to_datetime(p.Date,errors="coerce"); p["Close"]=pd.to_numeric(p.Close,errors="coerce"); p=p.dropna(subset=["Date","Close"]).sort_values(["Ticker","Date"])
    p["Norm"]=p.groupby("Ticker")["Close"].transform(lambda s: s/s.iloc[0]*100 if len(s) and s.iloc[0] else np.nan)
    bench=p.groupby("Date",as_index=False).Norm.mean(); q=p[p.Ticker.astype(str)==str(ticker)]
    fig=go.Figure(); fig.add_trace(go.Scatter(x=q.Date,y=q.Norm,mode="lines",name=f"{ticker} (đầu kỳ=100)")); fig.add_trace(go.Scatter(x=bench.Date,y=bench.Norm,mode="lines",line=dict(dash="dash"),name="Bình quân 20 NH (đầu kỳ=100)"))
    fig.update_layout(title="Diễn biến giá tương đối · so với bình quân 20 ngân hàng niêm yết",height=430,yaxis_title="Chỉ số giá")
    return fig

summary=csv(OUT/"valuation_summary.csv")
methods=csv(OUT/"valuation_methods.csv")
peer=csv(OUT/"peer_summary.csv")
mna=csv(OUT/"mna_baseline.csv")
hist=csv(DATA/"bank_history_long.csv")
prices=csv(DATA/"price_history.csv")
log=csv(DATA/"refresh_log.csv")
cfg=js(ROOT/"config/model_config.json")
precedents=csv(ROOT/"config/transaction_precedents.csv")
research=load_research(ROOT)

st.sidebar.markdown("## MỤC ĐÍCH PHÂN TÍCH")
mode_label=st.sidebar.radio(
    "Chọn chế độ",
    ["Đầu tư cổ phiếu","M&A / Thâu tóm","Tái cơ cấu ngân hàng","Xếp hạng tín nhiệm"],
    index=0
)
mode={"Đầu tư cổ phiếu":"investment","M&A / Thâu tóm":"mna","Tái cơ cấu ngân hàng":"restructuring","Xếp hạng tín nhiệm":"credit_rating"}[mode_label]
presentation=st.sidebar.toggle("Chế độ trình bày",value=False,help="Ưu tiên KPI, biểu đồ và nhận định; giảm chi tiết kỹ thuật.")

st.sidebar.markdown("---")
if len(summary):
    tickers=summary["Ticker"].astype(str).tolist()
    selected=st.sidebar.selectbox("Ngân hàng phân tích",tickers)
else:
    selected=None

st.sidebar.markdown("## TRẠNG THÁI DỮ LIỆU")
if len(summary):
    st.sidebar.success(f"Universe: {len(summary)} ngân hàng")
    st.sidebar.write(f"Có giá thị trường: **{int(pd.to_numeric(summary.Price,errors='coerce').notna().sum())}**")
    st.sidebar.write(f"Có giá trị hợp lý: **{int(pd.to_numeric(summary.FairValue_Base,errors='coerce').notna().sum())}**")
    st.sidebar.write(f"Coverage trung vị: **{pd.to_numeric(summary.DataCoverage,errors='coerce').median():.0%}**")
else:
    st.sidebar.warning("Chưa có outputs. Chạy RUN_UPDATE_AND_PUSH.bat trên máy local có Vnstock Bronze.")

st.sidebar.caption("Vnstock Bronze chạy LOCAL → ACTUAL CSV → mô hình định giá → GitHub → Streamlit chỉ đọc dữ liệu.")
st.sidebar.caption("ACTUAL = dữ liệu nguồn · CALCULATED = công thức · ASSUMPTION = kịch bản.")
st.sidebar.caption("ENGINE V7.0 · PEER AVERAGE + STRATEGIC CASE")

st.title("NỀN TẢNG PHÂN TÍCH, ĐỊNH GIÁ & M&A NGÂN HÀNG VIỆT NAM")
st.caption("Vietnam Banking Valuation & M&A Intelligence Platform · ENGINE V7.0 · PEER AVERAGE + STRATEGIC CASE")
st.markdown(f"**Chế độ hiện tại:** {mode_label}")

if summary.empty:
    st.info("Project đã sẵn sàng nhưng chưa có dữ liệu valuation. Chạy `RUN_UPDATE_AND_PUSH.bat` trên máy local có Vnstock Sponsor Bronze.")
    st.stop()

# Normalize numeric columns.
text_cols={"Ticker","PeerGroup","OwnershipType","ValuationView","QualityView","FundamentalView","InvestmentView","RetrievedAt","DataType","SourceMode","StrategicIntelligenceType","StrategicAsOfDate","StrategicSource","StrategicConfidence","StrategicNote"}
for c in summary.columns:
    if c not in text_cols:
        summary[c]=pd.to_numeric(summary[c],errors="coerce")

row=summary[summary.Ticker.astype(str).eq(str(selected))].iloc[0]
peer_row=None
if len(peer):
    q=peer[peer.PeerGroup.astype(str).eq(str(row.PeerGroup))]
    if len(q):peer_row=q.iloc[0].to_dict()
mna_row=None
if len(mna):
    q=mna[mna.Ticker.astype(str).eq(str(selected))]
    if len(q):mna_row=q.iloc[0].to_dict()

qa=assess_report_quality(row.to_dict(),cfg,hist,prices)
norm_flags=normalization_flags(row.to_dict(),cfg,prices)
strategic_case=strategic_reasonableness(row.to_dict(),cfg,research)
strategic_case_text=reasonableness_conclusion(strategic_case)
all_means=all_bank_means(summary)

# Header investment case.
h1,h2,h3,h4,h5,h6=st.columns(6)
h1.metric("Giá thị trường",money(row.Price))
h2.metric("Giá trị cơ bản",money(row.FairValue_Base))
if num(row.get("StrategicPriceLow")) is not None:
    h3.metric("Giá chiến lược thấp",money(row.StrategicPriceLow),pct(row.StrategicPremiumLow))
    h4.metric("Giá chiến lược cao",money(row.StrategicPriceHigh),pct(row.StrategicPremiumHigh))
else:
    h3.metric("P/B",mult(row.PB_Current)); h4.metric("ROE",pct(row.ROE_Used))
h5.metric("NPL",pct(row.NPL))
h6.metric("Điểm cơ bản",f"{row.FundamentalScore:.0f}/100" if num(row.get("FundamentalScore")) is not None else "N/A")

status_icon={"CHÍNH THỨC":"✅","BẢN NHÁP":"⚠️","CHƯA ĐỦ DỮ LIỆU":"⛔"}.get(qa["ReportStatus"],"ℹ️")
st.markdown(f"""<div class="analysis-box"><b>{status_icon} TRẠNG THÁI BÁO CÁO: {qa["ReportStatus"]}</b> · Độ phủ kiểm soát {qa["ReportCoverage"]:.0%}<br><br><b>NHẬN ĐỊNH CHÍNH</b><br>{executive_summary(row.to_dict(),peer_row)}</div>""",unsafe_allow_html=True)

if num(row.get("StrategicPriceLow")) is not None:
    st.info(f"GIÁ TRỊ CHIẾN LƯỢC / M&A (THÔNG TIN THỊ TRƯỜNG): {money(row.StrategicPriceLow)} - {money(row.StrategicPriceHigh)}. Đây là lớp giá trị giao dịch riêng, không thay thế giá trị cơ bản {money(row.FairValue_Base)}.")

tabs=st.tabs([
    "Tổng quan thị trường","Sàng lọc cổ phiếu","Hồ sơ ngân hàng","Định giá cổ phiếu",
    "So sánh tương quan","M&A / Quyền kiểm soát","Tái cơ cấu","PPA & Goodwill","Xếp hạng tín nhiệm","Báo cáo & Quản trị"
])

with tabs[0]:
    a,b,c,d,e=st.columns(5)
    a.metric("Số ngân hàng",len(summary))
    b.metric("P/B trung vị",mult(summary.PB_Current.median()))
    c.metric("ROE trung vị",pct(summary.ROE_Used.median()))
    d.metric("Tiềm năng trung vị",pct(summary.Upside_Base.median()))
    e.metric("Điểm đầu tư trung vị",f"{summary.InvestmentScore.median():.0f}" if "InvestmentScore" in summary else "N/A")

    left,right=st.columns([1.25,1])
    with left:
        q=summary.dropna(subset=["ROE_Used","PB_Current"]).copy()
        fig=px.scatter(q,x="ROE_Used",y="PB_Current",size="Equity",color="PeerGroup",text="Ticker",
                       hover_data=["Upside_Base","NPL","CAR","InvestmentScore"],title="Bản đồ ROE - P/B")
        fig.update_traces(textposition="top center"); fig.update_xaxes(tickformat=".0%",title="ROE"); fig.update_yaxes(title="P/B (x)")
        fig.update_layout(height=460); st.plotly_chart(fig,use_container_width=True)
    with right:
        q=summary.sort_values("InvestmentScore",ascending=False).head(10).sort_values("InvestmentScore")
        fig=px.bar(q,x="InvestmentScore",y="Ticker",orientation="h",title="Top 10 điểm đầu tư · so sánh 20 ngân hàng niêm yết",hover_data=["Upside_Base","ROE_Used","NPL"])
        mean_score=pd.to_numeric(summary.InvestmentScore,errors="coerce").mean(); fig.add_vline(x=mean_score,line_dash="dash",annotation_text=f"Bình quân 20 NH {mean_score:.1f}")
        fig.update_layout(height=460,xaxis_title="Điểm / 100"); st.plotly_chart(fig,use_container_width=True)

    if not presentation:
        cols=["Ticker","PeerGroup","Price","FairValue_Base","Upside_Base","PB_Current","ROE_Used","NPL","CAR","InvestmentScore","InvestmentView"]
        st.dataframe(display_df(safe(summary[cols].sort_values("InvestmentScore",ascending=False))),hide_index=True,use_container_width=True,height=400)

with tabs[1]:
    st.subheader("Sàng lọc cổ phiếu ngân hàng")
    c1,c2,c3,c4=st.columns(4)
    groups=["Tất cả"]+sorted(summary.PeerGroup.dropna().astype(str).unique().tolist())
    grp=c1.selectbox("Nhóm ngân hàng",groups,format_func=lambda x: "Tất cả" if x=="Tất cả" else PEER_GROUP_VI.get(x,x))
    minroe=c2.slider("ROE tối thiểu",0.0,.35,.10,.01)
    maxpb=c3.slider("P/B tối đa",.3,4.0,2.0,.1)
    minscore=c4.slider("Điểm đầu tư tối thiểu",0,100,50,5)
    z=summary.copy()
    if grp!="Tất cả":z=z[z.PeerGroup.astype(str).eq(grp)]
    z=z[(z.ROE_Used>=minroe)&(z.PB_Current<=maxpb)&(z.InvestmentScore>=minscore)]
    cols=["Ticker","PeerGroup","Price","FairValue_Base","Upside_Base","PB_Current","PTBV_Current","PE_Current","ROE_Used","NIM","NPL","CAR","CASA","InvestmentScore","InvestmentView"]
    st.dataframe(display_df(safe(z[cols].sort_values("InvestmentScore",ascending=False))),hide_index=True,use_container_width=True)

with tabs[2]:
    st.subheader(f"Hồ sơ ngân hàng - {selected}")
    c1,c2,c3,c4,c5,c6=st.columns(6)
    c1.metric("ROE",pct(row.ROE_Used)); c2.metric("ROA",pct(row.ROA)); c3.metric("NIM",pct(row.NIM))
    c4.metric("NPL",pct(row.NPL)); c5.metric("CAR",pct(row.CAR)); c6.metric("CASA",pct(row.CASA))
    st.markdown(f"""<div class="analysis-box"><b>VỊ THẾ & TĂNG TRƯỞNG</b><br>{business_profile(row.to_dict(),peer_row)}</div>""",unsafe_allow_html=True)

    if peer_row:
        st.markdown("### So sánh với nhóm tương đồng")
        bench=pd.DataFrame([
            ["ROE",row.get("ROE_Used"),peer_row.get("MeanROE"),peer_row.get("MedianROE"),all_means.get("ROE_Used")],
            ["ROA",row.get("ROA"),peer_row.get("MeanROA"),peer_row.get("MedianROA"),all_means.get("ROA")],
            ["NIM",row.get("NIM"),peer_row.get("MeanNIM"),peer_row.get("MedianNIM"),all_means.get("NIM")],
            ["NPL",row.get("NPL"),peer_row.get("MeanNPL"),peer_row.get("MedianNPL"),all_means.get("NPL")],
            ["CAR",row.get("CAR"),peer_row.get("MeanCAR"),peer_row.get("MedianCAR"),all_means.get("CAR")],
            ["CASA",row.get("CASA"),peer_row.get("MeanCASA"),peer_row.get("MedianCASA"),all_means.get("CASA")],
            ["CIR",row.get("CIR"),peer_row.get("MeanCIR"),peer_row.get("MedianCIR"),all_means.get("CIR")],
            ["LDR",row.get("LDR"),peer_row.get("MeanLDR"),peer_row.get("MedianLDR"),all_means.get("LDR")],
            ["P/B",row.get("PB_Current"),peer_row.get("MeanPB"),peer_row.get("MedianPB"),all_means.get("PB_Current")],
            ["P/TBV",row.get("PTBV_Current"),peer_row.get("MeanPTBV"),peer_row.get("MedianPTBV"),all_means.get("PTBV_Current")],
        ],columns=["Chỉ tiêu",selected,"Trung bình nhóm so sánh","Trung vị nhóm so sánh","Bình quân 20 NH"])
        pct_metrics={"ROE","ROA","NIM","NPL","CAR","CASA","CIR","LDR"}
        def _fb(r):
            if r["Chỉ tiêu"] in pct_metrics:
                return [r["Chỉ tiêu"],pct(r[selected]),pct(r["Trung bình nhóm so sánh"]),pct(r["Trung vị nhóm so sánh"]),pct(r["Bình quân 20 NH"])]
            return [r["Chỉ tiêu"],mult(r[selected]),mult(r["Trung bình nhóm so sánh"]),mult(r["Trung vị nhóm so sánh"]),mult(r["Bình quân 20 NH"])]
        shown=pd.DataFrame([_fb(r) for _,r in bench.iterrows()],columns=bench.columns)
        st.dataframe(shown,hide_index=True,use_container_width=True)

    score_cols=["ProfitabilityScore","GrowthScore","AssetQualityScore","FundingScore","CapitalScore","ValuationScore"]
    score_names=["Sinh lời","Tăng trưởng","Chất lượng tài sản","Nguồn vốn","An toàn vốn","Định giá"]
    scores=[num(row.get(c)) for c in score_cols]
    fig=go.Figure(go.Bar(x=[x or 0 for x in scores],y=score_names,orientation="h",text=[f"{x:.0f}" if x is not None else "N/A" for x in scores],textposition="outside",name=selected))
    peer_scores=[pd.to_numeric(summary[c],errors="coerce").mean() for c in score_cols]
    fig.add_trace(go.Scatter(x=peer_scores,y=score_names,mode="lines+markers",line=dict(dash="dash"),name="Bình quân 20 NH"))
    fig.update_layout(title="Thẻ điểm 6 trụ cột · so với bình quân 20 ngân hàng niêm yết",xaxis_range=[0,105],height=380,xaxis_title="Điểm / 100")
    st.plotly_chart(fig,use_container_width=True)

    st.markdown("### Xu hướng chỉ tiêu theo thời gian - so với bình quân 20 ngân hàng niêm yết")
    if len(hist):
        st.caption("Mỗi biểu đồ chỉ thể hiện một chỉ tiêu để tránh sai lệch trực quan do khác biệt thang đo.")

        r1c1,r1c2=st.columns(2)
        with r1c1:
            st.plotly_chart(metric_history_figure(selected,["TotalAssets"],"Tổng tài sản",percent=False),use_container_width=True)
        with r1c2:
            st.plotly_chart(metric_history_figure(selected,["GrossLoans"],"Dư nợ khách hàng",percent=False),use_container_width=True)

        r2c1,r2c2=st.columns(2)
        with r2c1:
            st.plotly_chart(metric_history_figure(selected,["CustomerDeposits"],"Tiền gửi khách hàng",percent=False),use_container_width=True)
        with r2c2:
            st.plotly_chart(metric_history_figure(selected,["ROE"],"Tỷ suất sinh lời trên vốn chủ sở hữu (ROE)"),use_container_width=True)

        r3c1,r3c2=st.columns(2)
        with r3c1:
            st.plotly_chart(metric_history_figure(selected,["ROA"],"Tỷ suất sinh lời trên tổng tài sản (ROA)"),use_container_width=True)
        with r3c2:
            st.plotly_chart(metric_history_figure(selected,["NIM"],"Biên lãi ròng (NIM)"),use_container_width=True)

        r4c1,r4c2=st.columns(2)
        with r4c1:
            st.plotly_chart(metric_history_figure(selected,["CIR"],"Tỷ lệ chi phí/thu nhập (CIR)"),use_container_width=True)
        with r4c2:
            st.plotly_chart(metric_history_figure(selected,["NPL"],"Tỷ lệ nợ xấu (NPL)"),use_container_width=True)

        r5c1,r5c2=st.columns(2)
        with r5c1:
            st.plotly_chart(metric_history_figure(selected,["CASA"],"Tỷ lệ tiền gửi không kỳ hạn (CASA)"),use_container_width=True)
        with r5c2:
            st.plotly_chart(metric_history_figure(selected,["LDR"],"Tỷ lệ cho vay trên tiền gửi (LDR)"),use_container_width=True)

        r6c1,r6c2=st.columns(2)
        with r6c1:
            st.plotly_chart(metric_history_figure(selected,["CAR"],"Hệ số an toàn vốn (CAR)"),use_container_width=True)
        with r6c2:
            if len(prices): st.plotly_chart(relative_price_figure(selected),use_container_width=True)

    st.markdown("### Nhận định chuyên môn")
    st.write("**Sinh lời:** "+profitability_text(row.to_dict(),peer_row))
    st.write("**Chất lượng tài sản:** "+asset_quality_text(row.to_dict(),peer_row))
    st.write("**Nguồn vốn:** "+funding_text(row.to_dict(),peer_row))
    st.write("**Vốn:** "+capital_text(row.to_dict(),peer_row))

with tabs[3]:
    st.subheader(f"Định giá cổ phiếu - {selected}")
    a,b,c,d,e=st.columns(5)
    a.metric("Giá thị trường",money(row.Price))
    b.metric("Giá trị hợp lý cơ sở",money(row.FairValue_Base),pct(row.Upside_Base))
    c.metric("Kịch bản thận trọng",money(row.FairValue_Bear))
    d.metric("Kịch bản tích cực",money(row.FairValue_Bull))
    e.metric("P/B hợp lý",mult(row.JustifiedPB))
    st.markdown(f"""<div class="analysis-box"><b>KẾT LUẬN ĐỊNH GIÁ</b><br>{valuation_text(row.to_dict(),peer_row)}</div>""",unsafe_allow_html=True)

    m=methods[methods.Ticker.astype(str).eq(str(selected))].copy()
    if len(m):
        m["FairValuePerShare"]=pd.to_numeric(m.FairValuePerShare,errors="coerce")
        m["Phương pháp"]=m["Method"].map(lambda x: METHOD_VI.get(str(x),str(x)))
        fig=px.bar(m.dropna(subset=["FairValuePerShare"]),x="Phương pháp",y="FairValuePerShare",title="Dải định giá - giá trị cơ bản, nhóm so sánh và chiến lược")
        fig.add_hline(y=row.Price,line_dash="dash",annotation_text="Giá thị trường")
        peer_pb_mean=pd.to_numeric(summary.PB_Current,errors="coerce").mean(); peer_implied=peer_pb_mean*num(row.get("BVPS_Used")) if num(row.get("BVPS_Used")) else None
        if peer_implied is not None: fig.add_hline(y=peer_implied,line_dash="dot",annotation_text=f"P/B bình quân 20 NH {peer_pb_mean:.2f}x")
        if num(row.get("StrategicPriceLow")) is not None: fig.add_hrect(y0=row.StrategicPriceLow,y1=row.StrategicPriceHigh,opacity=.12,line_width=0,annotation_text="Vùng giá chiến lược")
        fig.update_layout(height=430,yaxis_title="Nghìn đồng/cp",xaxis_title="")
        st.plotly_chart(fig,use_container_width=True)
        if not presentation:
            st.dataframe(m[["Method","FairValuePerShare","MarketPrice","Upside","DataType"]].style.format({
                "FairValuePerShare":lambda v: f"{v*1000:,.0f}","MarketPrice":lambda v: f"{v*1000:,.0f}","Upside":"{:.1%}"
            }),hide_index=True,use_container_width=True)

    st.markdown("### Ba lớp giá trị: thị trường - cơ bản - chiến lược")
    bridge=pd.DataFrame([
        {"Lớp giá trị":"Giá thị trường","Giá thấp":row.Price,"Giá cao":row.Price,"Ý nghĩa":"Giá giao dịch trên sàn"},
        {"Lớp giá trị":"Giá trị cơ bản","Giá thấp":row.FairValue_Bear,"Giá cao":row.FairValue_Bull,"Ý nghĩa":"Thu nhập thặng dư + P/B + nhóm so sánh + lịch sử"},
        {"Lớp giá trị":"Giá trị chiến lược/M&A","Giá thấp":row.get("StrategicPriceLow"),"Giá cao":row.get("StrategicPriceHigh"),"Ý nghĩa":"Market intelligence / block premium / quyền kiểm soát"},
    ])
    st.dataframe(bridge.style.format({"Giá thấp":lambda v: f"{v*1000:,.0f}","Giá cao":lambda v: f"{v*1000:,.0f}"},na_rep="N/A"),hide_index=True,use_container_width=True)
    if num(row.get("StrategicPriceLow")) is not None:
        st.warning(f"Khoảng {money(row.StrategicPriceLow)} - {money(row.StrategicPriceHigh)} được gắn nhãn {row.get('StrategicSource','MARKET_INTELLIGENCE')} ({row.get('StrategicConfidence','N/A')}). Không dùng khoảng này để ép ngược mô hình fundamental; chênh lệch được giải thích bằng scarcity/control premium, optionality tái cơ cấu và giá trị chiến lược của lô cổ phần.")

    st.markdown("### Giả định trọng yếu")
    st.write(f"COE **{pct(row.COE)}** · Tăng trưởng dài hạn **{pct(row.LTG)}** · ROE chuẩn hóa **{pct(row.NormalizedROE_Used)}** · P/B hợp lý **{mult(row.JustifiedPB)}**")
    st.caption("Thu nhập thặng dư (Residual Income) là phương pháp nội tại chính. P/B hợp lý, P/B nhóm tương đồng và vùng định giá lịch sử là phương pháp đối chiếu.")
    st.markdown("### Điểm cần lưu ý khi định giá")
    for flag in norm_flags:
        st.warning(flag)

with tabs[4]:
    st.subheader("So sánh tương quan")
    if len(peer):
        st.dataframe(peer.style.format({"MedianPB":"{:.2f}x","MedianPTBV":"{:.2f}x","MedianROE":"{:.1%}","MedianNPL":"{:.1%}","MedianUpside":"{:.1%}"}),hide_index=True,use_container_width=True)
    if peer_row:
        st.markdown(f"### {selected} so với trung vị nhóm {PEER_GROUP_VI.get(str(row.PeerGroup),str(row.PeerGroup))}")
        metrics=[("ROE","ROE_Used","MedianROE",True),("ROA","ROA","MedianROA",True),("NIM","NIM","MedianNIM",True),("NPL","NPL","MedianNPL",False),("CAR","CAR","MedianCAR",True),("CASA","CASA","MedianCASA",True),("CIR","CIR","MedianCIR",False),("P/B","PB_Current","MedianPB",False)]
        rr=[]
        for label,col,pcol,higher in metrics:
            v=num(row.get(col)); pv=num(peer_row.get(pcol)); gap=(v-pv) if v is not None and pv is not None else None
            verdict="N/A" if gap is None else ("Tốt hơn nhóm so sánh" if (gap>0)==higher else "Kém hơn nhóm so sánh" if gap!=0 else "Tương đương nhóm so sánh")
            rr.append({"Chỉ tiêu":label,selected:v,"Trung vị nhóm so sánh":pv,"Chênh lệch":gap,"Đánh giá":verdict})
        peer_cmp=pd.DataFrame(rr)
        st.dataframe(peer_cmp.style.format({selected:"{:.2%}","Trung vị nhóm so sánh":"{:.2%}","Chênh lệch":"{:+.2%}"},na_rep="N/A"),hide_index=True,use_container_width=True)
    q=summary.dropna(subset=["ROE_Used","PB_Current"])
    fig=px.scatter(q,x="ROE_Used",y="PB_Current",color="PeerGroup",text="Ticker",size="TotalAssets",hover_data=["NPL","CAR","Upside_Base","InvestmentScore"],title="ROE - P/B: chất lượng sinh lời và định giá")
    fig.update_traces(textposition="top center"); fig.update_xaxes(tickformat=".0%")
    mean_roe=pd.to_numeric(q.ROE_Used,errors="coerce").mean(); mean_pb=pd.to_numeric(q.PB_Current,errors="coerce").mean()
    fig.add_vline(x=mean_roe,line_dash="dash",annotation_text=f"ROE BQ20 {mean_roe:.1%}"); fig.add_hline(y=mean_pb,line_dash="dash",annotation_text=f"P/B BQ20 {mean_pb:.2f}x")
    fig.update_layout(height=560); st.plotly_chart(fig,use_container_width=True)

with tabs[5]:
    st.subheader(f"Định giá M&A / Quyền kiểm soát - {selected}")
    b=mna_row
    c1,c2,c3,c4=st.columns(4)
    stake=c1.slider("Tỷ lệ mua",.05,1.0,1.0,.05)
    premium=c2.slider("Thặng dư quyền kiểm soát",0.0,.50,float(cfg.get("control_premium",.20)),.01)
    synergy_mult=c3.slider("Hệ số cộng hưởng",0.0,2.0,1.0,.1)
    recap_bn=c4.number_input("Vốn bổ sung cần thiết (tỷ đồng)",min_value=0.0,value=0.0,step=100.0)
    shares=num(row.Shares); standalone=num(row.FairValue_Base)*shares if num(row.FairValue_Base) and shares else None
    synergy=(num(b.get("PV_Synergies")) if b else 0)*synergy_mult
    integration=(num(b.get("IntegrationCost")) if b else 0)
    consideration=(standalone*(1+premium)+synergy-integration-recap_bn*1e9)*stake if standalone else None
    offer_ps=(consideration/(shares*stake)) if consideration and shares and stake else None
    implied_pb=(consideration/(num(row.Equity)*stake)) if consideration and num(row.Equity) else None
    implied_ptbv=(consideration/(num(row.TangibleEquity)*stake)) if consideration and num(row.TangibleEquity) else None
    x1,x2,x3,x4,x5=st.columns(5)
    x1.metric("Giá trị độc lập/cp",money(row.FairValue_Base)); x2.metric("Giá chào mua/cp",money(offer_ps)); x3.metric("P/B giao dịch",mult(implied_pb)); x4.metric("P/TBV giao dịch",mult(implied_ptbv)); x5.metric("Giá trị giao dịch",fmtbn(consideration))
    st.markdown(f"""<div class="analysis-box"><b>HÀM Ý THƯƠNG VỤ</b><br>{mna_text(row.to_dict(),b)}</div>""",unsafe_allow_html=True)
    if strategic_case.get("strategic_low") is not None:
        st.markdown("### Kiểm tra tính hợp lý của vùng giá thâu tóm")
        lo=strategic_case["low"]; hi=strategic_case["high"]
        proof=pd.DataFrame([
            ["Premium so với thị giá",pct(lo.get("premium_to_market")),pct(hi.get("premium_to_market"))],
            ["P/B trên BVPS hiện tại",mult(lo.get("implied_pb_current")),mult(hi.get("implied_pb_current"))],
            ["P/B hậu xử lý (BVPS +10k theo kịch bản nghiên cứu)",mult(lo.get("implied_pb_post_resolution")),mult(hi.get("implied_pb_post_resolution"))],
            ["Giá trị lô 32,5%",fmtbn((lo.get("block_consideration_bn") or 0)*1e9),fmtbn((hi.get("block_consideration_bn") or 0)*1e9)],
            ["Bao phủ 63.250 tỷ gốc+lãi",pct(lo.get("claim_recovery")),pct(hi.get("claim_recovery"))],
            ["Premium so với high-case nghiên cứu công khai",pct(lo.get("premium_to_public_high")),pct(hi.get("premium_to_public_high"))],
        ],columns=["Chỉ tiêu",money(strategic_case.get("strategic_low")),money(strategic_case.get("strategic_high"))])
        st.dataframe(proof,hide_index=True,use_container_width=True)
        st.markdown(f"""<div class="analysis-box"><b>KẾT LUẬN TÍNH HỢP LÝ</b><br>{strategic_case_text}</div>""",unsafe_allow_html=True)
        if len(research):
            st.markdown("### Đối chiếu nghiên cứu công khai")
            rr=research.copy(); rr["BasePrice"]=pd.to_numeric(rr.BasePrice,errors="coerce")*1000; rr["LowPrice"]=pd.to_numeric(rr.LowPrice,errors="coerce")*1000; rr["HighPrice"]=pd.to_numeric(rr.HighPrice,errors="coerce")*1000
            st.dataframe(rr[["Date","Institution","LowPrice","BasePrice","HighPrice","KeyAssumption","SourceURL"]],hide_index=True,use_container_width=True)
    st.warning("Đây là kiểm tra tính hợp lý kinh tế, không phải bằng chứng giao dịch chắc chắn xảy ra. Control premium, synergy, thời gian xử lý và xác suất hoàn tất vẫn là các biến rủi ro.")
    if num(row.get("StrategicPriceLow")) is not None:
        st.markdown("### Đường cong giá lô chiến lược")
        curve=pd.DataFrame({"Quy mô lô":["5%","10%","20%","32,5%","51%"],"Giá tham chiếu/cp":[(num(row.get("StrategicPrice_5pct")) or np.nan)*1000,(num(row.get("StrategicPrice_10pct")) or np.nan)*1000,(num(row.get("StrategicPrice_20pct")) or np.nan)*1000,(num(row.get("StrategicPrice_32_5pct")) or np.nan)*1000,(num(row.get("StrategicPrice_51pct")) or np.nan)*1000]})
        fig_curve=px.line(curve,x="Quy mô lô",y="Giá tham chiếu/cp",markers=True,title="Giá trị chiến lược tăng theo quy mô lô/quyền ảnh hưởng")
        peer_pb_mean=pd.to_numeric(summary.PB_Current,errors="coerce").mean(); peer_implied=peer_pb_mean*num(row.get("BVPS_Used"))*1000 if num(row.get("BVPS_Used")) else None
        if peer_implied is not None: fig_curve.add_hline(y=peer_implied,line_dash="dash",annotation_text="Giá hàm ý P/B bình quân 20 NH")
        st.plotly_chart(fig_curve,use_container_width=True)
        st.caption(f"Nguồn intelligence: {row.get('StrategicSource','N/A')} · ngày {row.get('StrategicAsOfDate','N/A')} · độ tin cậy {row.get('StrategicConfidence','N/A')}. Đây không phải giá giao dịch đã xác nhận.")
    if len(precedents.dropna(how="all")):
        st.markdown("### Giao dịch so sánh")
        st.dataframe(precedents,hide_index=True,use_container_width=True)
    else:
        st.caption("Bảng giao dịch so sánh để trống có chủ ý. Chỉ nhập thương vụ có nguồn xác thực vào Excel Master.")

with tabs[6]:
    st.subheader(f"Định giá tái cơ cấu - {selected}")
    c1,c2,c3=st.columns(3)
    extra=c1.slider("Dự phòng bổ sung / Dư nợ",0.0,.10,float(cfg.get("restructuring_extra_provision_pct_loans",.01)),.005)
    haircut=c2.slider("Haircut trên NPL",0.0,.80,float(cfg.get("restructuring_npl_haircut",.35)),.05)
    recap=c3.number_input("Vốn bổ sung (tỷ đồng)",min_value=0.0,value=0.0,step=100.0,key="restruct")
    equity=num(row.Equity); loans=num(row.GrossLoans) or 0; npl=num(row.NPL) or 0; shares=num(row.Shares)
    adjusted=equity-loans*extra-loans*npl*haircut-recap*1e9 if equity is not None else None
    adj_bvps=adjusted/shares if adjusted is not None and shares else None
    value=adj_bvps*num(row.JustifiedPB) if adj_bvps and num(row.JustifiedPB) else None
    a,b,c,d=st.columns(4); a.metric("Vốn báo cáo",fmtbn(equity)); b.metric("Vốn điều chỉnh",fmtbn(adjusted)); c.metric("BVPS điều chỉnh",money(adj_bvps)); d.metric("Giá trị sau tái cơ cấu",money(value))
    st.warning("P/B thấp không đồng nghĩa cổ phiếu rẻ nếu book value cần clean-up. Mô hình điều chỉnh chất lượng tài sản và nhu cầu tái cấp vốn trước khi định giá.")

with tabs[7]:
    st.subheader(f"Phân bổ giá mua (PPA) & Goodwill - {selected}")
    # Do not reuse the short variable `b` here: it is overwritten by Streamlit column objects in the previous tab.
    default_cons=num(mna_row.get("IllustrativeConsideration")) if isinstance(mna_row, dict) else 0
    consideration_bn=st.number_input("Giá mua (tỷ đồng)",min_value=0.0,value=float(default_cons/1e9 if default_cons else 0),step=500.0)
    c1,c2,c3=st.columns(3)
    loan_mark=c1.slider("Điều chỉnh FV danh mục cho vay / Dư nợ",-0.10,.05,-float(cfg.get("credit_mark_pct_gross_loans",.02)),.005)
    sec_adj=c2.number_input("Điều chỉnh FV chứng khoán/khác (tỷ)",value=0.0,step=100.0)
    intang_pct=c3.slider("Tài sản vô hình nhận diện / Tiền gửi",0.0,.05,float(cfg.get("identifiable_intangible_pct_customer_deposits",.01)),.0025)
    base_net=num(row.TangibleEquity) or num(row.Equity); loans=num(row.GrossLoans) or 0; dep=num(row.CustomerDeposits) or 0
    identifiable=dep*intang_pct; fv_net=base_net+loans*loan_mark+sec_adj*1e9+identifiable if base_net is not None else None
    consideration=consideration_bn*1e9; goodwill=consideration-fv_net if fv_net is not None else None
    a,b,c,d=st.columns(4); a.metric("Tài sản thuần hữu hình",fmtbn(base_net)); b.metric("Tài sản vô hình nhận diện",fmtbn(identifiable)); c.metric("Tài sản thuần FV",fmtbn(fv_net)); d.metric("Goodwill / (Bargain)",fmtbn(goodwill))
    st.info("PPA mô phỏng acquisition method của IFRS 3. Loan-book mark, chứng khoán, nghĩa vụ ngoại bảng và intangible franchise phải được thẩm định riêng trong thương vụ thực tế.")

with tabs[8]:
    st.subheader(f"Xếp hạng tín nhiệm ngân hàng - {selected}")
    st.caption("Khung xếp hạng mô phỏng/nội bộ tham khảo cấu trúc báo cáo xếp hạng ngân hàng: Vị thế kinh doanh; Vốn, đòn bẩy & lợi nhuận; Vị thế rủi ro; Huy động vốn; Thanh khoản; Quản trị; và Hỗ trợ bên ngoài. Kết quả tự động không phải xếp hạng tín nhiệm chính thức.")

    st.info("Phương pháp V7.2: BICRA/Anchor = vnA- → cộng/trừ notch của Hồ sơ kinh doanh, Vốn & lợi nhuận, Vị thế rủi ro và ma trận Huy động vốn × Thanh khoản → SACP → điều chỉnh hỗ trợ bên ngoài → ICR cuối cùng.")
    rc1,rc2,rc3=st.columns(3)
    governance_score=rc1.select_slider("Quản trị, quản lý & chiến lược",options=[1,2,3,4,5,6],value=3,help="Đầu vào định tính của HỒ SƠ KINH DOANH theo methodology: 1 = Rất Mạnh; 6 = Rất Yếu.")
    analyst_notches=rc2.slider("Điều chỉnh khác trước SACP (notch)",-2,2,0,1,help="Các lưu ý khác/Basel/định tính chưa phản ánh đầy đủ trong 4 yếu tố chính. + là nâng bậc.")
    support_notches=rc3.slider("Hỗ trợ bên ngoài sau SACP (notch)",-4,6,0,1,help="Hỗ trợ Chính phủ/NHNN hoặc tập đoàn sở hữu. + là nâng bậc ICR so với SACP.")
    cr0=build_credit_rating(summary,selected,governance_score,support_notches,analyst_notches)
    st.markdown("### Xác nhận notch theo ma trận methodology")
    st.caption("Các mức Rất mạnh/Mạnh/Phù hợp/Trung Bình có notch cố định. Với Yếu/Rất yếu và các ô ‘hoặc hơn’, chuyên viên chọn notch trong đúng khoảng methodology; mức tự động mặc định là mức đầu tiên của ma trận.")
    n1,n2,n3,n4=st.columns(4)
    overrides={}
    for col,key,label in [(n1,"BusinessPosition","Hồ sơ kinh doanh"),(n2,"CapitalEarnings","Vốn & lợi nhuận"),(n3,"RiskPosition","Vị thế rủi ro")]:
        score=cr0["FactorScores"][key]; allowed=cr0["AllowedFactorNotches"][key]
        with col:
            st.caption(f"{label}: {DESCRIPTOR_6[score]} ({score}/6)")
            if len(allowed)>1:
                overrides[key]=st.selectbox(f"Notch {label}",allowed,index=0,key=f"notch_{key}")
            else:
                st.metric("Notch",f"{allowed[0]:+d}"); overrides[key]=allowed[0]
    with n4:
        st.caption(f"Huy động × Thanh khoản: {cr0['FundingDescriptor']} × {cr0['LiquidityDescriptor']}")
        allowed_fl=cr0["AllowedFundingLiquidityNotches"]
        if len(allowed_fl)>1:
            overrides["FundingLiquidity"]=st.selectbox("Notch Huy động × Thanh khoản",allowed_fl,index=0,key="notch_fl")
        else:
            st.metric("Notch",f"{allowed_fl[0]:+d}"); overrides["FundingLiquidity"]=allowed_fl[0]
    cr=build_credit_rating(summary,selected,governance_score,support_notches,analyst_notches,overrides)

    a,b,c,d,e=st.columns(5)
    a.metric("BICRA / Anchor",cr["AnchorRating"])
    b.metric("Tổng notch nội tại",f"{cr['InternalNotches']:+d}")
    c.metric("SACP",cr["SACPRating"])
    d.metric("ICR cuối cùng",cr["FinalRating"])
    e.metric("Triển vọng",cr["Outlook"])
    st.warning("KẾT QUẢ MÔ PHỎNG/NỘI BỘ: không được sử dụng như kết quả xếp hạng tín nhiệm chính thức nếu chưa hoàn tất quy trình phân tích định tính, phỏng vấn, kiểm soát chất lượng và Hội đồng xếp hạng.")

    st.markdown("### Khung phân tích xếp hạng")
    rows=[]
    for k,v in cr["FactorScores"].items():
        maxs=4 if k in {"Funding","Liquidity"} else 6
        notch = cr["FactorNotches"].get(k, "—") if k not in {"Funding","Liquidity"} else "—"
        rows.append([FACTOR_LABELS[k],f"{v}/{maxs}",notch,cr["FactorRationale"][k]])
    rows.append(["Huy động vốn × Thanh khoản","Ma trận Bảng 10",cr["FundingLiquidityNotch"],f"{cr['FundingDescriptor']} × {cr['LiquidityDescriptor']}"])
    rows.append(["Điều chỉnh khác trước SACP","—",cr["OtherInternalNotches"],"Điều chỉnh chuyên viên/Hội đồng cho các yếu tố khác chưa phản ánh đầy đủ."])
    st.dataframe(pd.DataFrame(rows,columns=["Yếu tố","Điểm","Notch tác động SACP","Luận điểm"]),hide_index=True,use_container_width=True)
    st.markdown("### Cầu nối từ BICRA đến kết quả cuối cùng")
    bridge=pd.DataFrame([
        ["BICRA / Anchor",cr["AnchorRating"],"Điểm xuất phát"],
        ["Hồ sơ kinh doanh",f"{cr['BusinessNotch']:+d}","notch"],
        ["Vốn & lợi nhuận",f"{cr['CapitalNotch']:+d}","notch"],
        ["Vị thế rủi ro",f"{cr['RiskNotch']:+d}","notch"],
        ["Huy động vốn × Thanh khoản",f"{cr['FundingLiquidityNotch']:+d}","notch"],
        ["Điều chỉnh khác",f"{cr['OtherInternalNotches']:+d}","notch"],
        ["SACP",cr["SACPRating"],"Sau điều chỉnh nội tại"],
        ["Hỗ trợ bên ngoài",f"{cr['ExternalSupportNotches']:+d}","notch"],
        ["ICR cuối cùng",cr["FinalRating"],"Kết quả"],
    ],columns=["Bước","Kết quả/Điều chỉnh","Ý nghĩa"])
    st.dataframe(bridge,hide_index=True,use_container_width=True)

    labels=[FACTOR_LABELS[k] for k in cr["FactorScores"]]
    vals=[(v if k not in {"Funding","Liquidity"} else 1+(v-1)*5/3) for k,v in cr["FactorScores"].items()]
    fig=go.Figure(go.Bar(x=vals,y=labels,orientation="h",text=[f"{v:.1f}" for v in vals],textposition="outside"))
    fig.update_layout(title="Điểm yếu tố xếp hạng (1 = mạnh nhất; 6 = yếu nhất)",xaxis_range=[0.7,6.3],height=390,xaxis_title="Điểm")
    st.plotly_chart(fig,use_container_width=True)

    c1,c2=st.columns(2)
    with c1:
        st.markdown("### Điểm mạnh")
        for x in cr["Strengths"]: st.write("• "+x)
    with c2:
        st.markdown("### Điểm hạn chế")
        for x in cr["Constraints"]: st.write("• "+x)

    c3,c4=st.columns(2)
    with c3:
        st.markdown("### Yếu tố có thể dẫn đến nâng bậc")
        for x in cr["UpgradeTriggers"]: st.write("• "+x)
    with c4:
        st.markdown("### Yếu tố có thể dẫn đến hạ bậc")
        for x in cr["DowngradeTriggers"]: st.write("• "+x)

    st.markdown("### So sánh xếp hạng mô phỏng 20 ngân hàng niêm yết")
    st.dataframe(rating_table(summary,governance_score),hide_index=True,use_container_width=True,height=400)

    st.markdown("### Xuất báo cáo xếp hạng tín nhiệm")
    try:
        cr_pdf=generate_credit_rating_pdf(ROOT,selected,governance_score,support_notches,analyst_notches,overrides)
        cr_docx=generate_credit_rating_docx(ROOT,selected,governance_score,support_notches,analyst_notches,overrides)
        x1,x2=st.columns(2)
        x1.download_button("📄 Tải Báo cáo XHTN PDF",cr_pdf,file_name=f"{selected}_Bao_cao_Xep_hang_Tin_nhiem.pdf",mime="application/pdf",use_container_width=True)
        x2.download_button("📝 Tải Báo cáo XHTN Word",cr_docx,file_name=f"{selected}_Bao_cao_Xep_hang_Tin_nhiem.docx",mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",use_container_width=True)
    except Exception as exc:
        st.warning(f"Chưa tạo được báo cáo XHTN: {exc}")

with tabs[9]:
    st.subheader("Báo cáo chính thức & Quản trị mô hình")
    st.markdown('<div class="report-box">',unsafe_allow_html=True)
    st.markdown(f"### Xuất báo cáo khoảng 10 trang A4 - {selected}")
    report_mode=st.radio("Nội dung báo cáo",["Định giá cổ phiếu","M&A / Thâu tóm","Xếp hạng tín nhiệm"],horizontal=True)
    rmode="mna" if report_mode.startswith("M&A") else "investment"
    st.caption("Báo cáo và dashboard dùng cùng valuation outputs; không copy số liệu thủ công.")
    if qa["ReportStatus"]=="CHÍNH THỨC":
        st.success(f"ĐỦ ĐIỀU KIỆN PHÁT HÀNH · Độ phủ {qa['ReportCoverage']:.0%} · thiếu {qa['CoreMissingCount']} chỉ tiêu lõi.")
    elif qa["ReportStatus"]=="BẢN NHÁP":
        st.warning(f"BẢN NHÁP – CẦN RÀ SOÁT · Độ phủ {qa['ReportCoverage']:.0%}. Báo cáo xuất ra sẽ được đóng dấu BẢN NHÁP.")
    else:
        st.error(f"KHÔNG PHÁT HÀNH – THIẾU DỮ LIỆU · Độ phủ {qa['ReportCoverage']:.0%}. Thiếu: {qa['CoreMissing'] or 'không xác định'}.")
    if qa["QualityWarnings"]:
        st.caption("Kiểm soát chất lượng: "+qa["QualityWarnings"])
    if qa["CanExportDraft"]:
        try:
            if report_mode=="Xếp hạng tín nhiệm":
                pdf_bytes=generate_credit_rating_pdf(ROOT,selected,3,0,0)
                docx_bytes=generate_credit_rating_docx(ROOT,selected,3,0,0)
                pdf_name=f"{selected}_Bao_cao_Xep_hang_Tin_nhiem.pdf"; docx_name=f"{selected}_Bao_cao_Xep_hang_Tin_nhiem.docx"
            else:
                pdf_bytes=generate_pdf_bytes(ROOT,selected,rmode)
                docx_bytes=generate_docx_bytes(ROOT,selected,rmode)
                pdf_name=f"{selected}_Bao_cao_Phan_tich_Dinh_gia.pdf"; docx_name=f"{selected}_Bao_cao_Phan_tich_Dinh_gia.docx"
            b1,b2=st.columns(2)
            b1.download_button("📄 Tải PDF A4",pdf_bytes,file_name=pdf_name,mime="application/pdf",use_container_width=True)
            b2.download_button("📝 Tải Word",docx_bytes,file_name=docx_name,mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",use_container_width=True)
        except Exception as exc:
            st.warning(f"Chưa tạo được báo cáo: {exc}")
    else:
        st.info("Nút xuất báo cáo được khóa cho đến khi dữ liệu đạt ngưỡng Bản nháp tối thiểu.")
    st.markdown('</div>',unsafe_allow_html=True)

    if not presentation:
        st.markdown("### Quản trị dữ liệu")
        st.write("**ACTUAL**: Vnstock/BCTC/giá thị trường. **CALCULATED**: công thức. **ASSUMPTION**: COE, tăng trưởng, control premium, synergy, credit mark, recapitalization.")
        st.write("**Nguyên tắc:** dữ liệu thiếu giữ N/A; assumption không được hiển thị như số liệu quan sát.")
        st.markdown("### Nhật ký cập nhật")
        if len(log): st.dataframe(log,hide_index=True,use_container_width=True,height=300)
        st.markdown("### Kiểm toán output")
        st.dataframe(summary[["Ticker","DataCoverage","RetrievedAt","DataType","SourceMode"]].style.format({"DataCoverage":"{:.0%}"}),hide_index=True,use_container_width=True)
