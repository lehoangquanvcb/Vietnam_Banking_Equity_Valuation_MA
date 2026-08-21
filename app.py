
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
from scripts.quality_engine import assess_report_quality, normalization_flags

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
def money(x): return "N/A" if num(x) is None else f"{num(x):,.0f}"
def mult(x,d=2): return "N/A" if num(x) is None else f"{num(x):.{d}f}x"
def fmtbn(x): return "N/A" if num(x) is None else f"{num(x)/1e9:,.0f} tỷ"
def safe(df): return df.copy().replace([np.inf,-np.inf],np.nan)

summary=csv(OUT/"valuation_summary.csv")
methods=csv(OUT/"valuation_methods.csv")
peer=csv(OUT/"peer_summary.csv")
mna=csv(OUT/"mna_baseline.csv")
hist=csv(DATA/"bank_history_long.csv")
prices=csv(DATA/"price_history.csv")
log=csv(DATA/"refresh_log.csv")
cfg=js(ROOT/"config/model_config.json")
precedents=csv(ROOT/"config/transaction_precedents.csv")

st.sidebar.markdown("## MỤC ĐÍCH PHÂN TÍCH")
mode_label=st.sidebar.radio(
    "Chọn chế độ",
    ["Đầu tư cổ phiếu","M&A / Thâu tóm","Tái cơ cấu ngân hàng"],
    index=0
)
mode={"Đầu tư cổ phiếu":"investment","M&A / Thâu tóm":"mna","Tái cơ cấu ngân hàng":"restructuring"}[mode_label]
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

st.title("NỀN TẢNG PHÂN TÍCH, ĐỊNH GIÁ & M&A NGÂN HÀNG VIỆT NAM")
st.caption("Vietnam Banking Valuation & M&A Intelligence Platform")
st.markdown(f"**Chế độ hiện tại:** {mode_label}")

if summary.empty:
    st.info("Project đã sẵn sàng nhưng chưa có dữ liệu valuation. Chạy `RUN_UPDATE_AND_PUSH.bat` trên máy local có Vnstock Sponsor Bronze.")
    st.stop()

# Normalize numeric columns.
text_cols={"Ticker","PeerGroup","OwnershipType","ValuationView","QualityView","FundamentalView","InvestmentView","RetrievedAt","DataType","SourceMode"}
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

# Header investment case.
h1,h2,h3,h4,h5,h6=st.columns(6)
h1.metric("Giá thị trường",money(row.Price))
h2.metric("Giá trị hợp lý",money(row.FairValue_Base),pct(row.Upside_Base))
h3.metric("P/B",mult(row.PB_Current))
h4.metric("ROE",pct(row.ROE_Used))
h5.metric("NPL",pct(row.NPL))
h6.metric("Điểm đầu tư",f"{row.InvestmentScore:.0f}/100" if num(row.get("InvestmentScore")) is not None else "N/A")

status_icon={"CHÍNH THỨC":"✅","BẢN NHÁP":"⚠️","CHƯA ĐỦ DỮ LIỆU":"⛔"}.get(qa["ReportStatus"],"ℹ️")
st.markdown(f"""<div class="analysis-box"><b>{status_icon} TRẠNG THÁI BÁO CÁO: {qa["ReportStatus"]}</b> · Độ phủ kiểm soát {qa["ReportCoverage"]:.0%}<br><br><b>NHẬN ĐỊNH CHÍNH</b><br>{executive_summary(row.to_dict())}</div>""",unsafe_allow_html=True)

tabs=st.tabs([
    "Tổng quan thị trường","Sàng lọc cổ phiếu","Hồ sơ ngân hàng","Định giá cổ phiếu",
    "So sánh tương quan","M&A / Quyền kiểm soát","Tái cơ cấu","PPA & Goodwill","Báo cáo & Quản trị"
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
        fig=px.bar(q,x="InvestmentScore",y="Ticker",orientation="h",title="Top 10 điểm đầu tư",hover_data=["Upside_Base","ROE_Used","NPL"])
        fig.update_layout(height=460,xaxis_title="Điểm / 100"); st.plotly_chart(fig,use_container_width=True)

    if not presentation:
        cols=["Ticker","PeerGroup","Price","FairValue_Base","Upside_Base","PB_Current","ROE_Used","NPL","CAR","InvestmentScore","InvestmentView"]
        st.dataframe(safe(summary[cols].sort_values("InvestmentScore",ascending=False)).style.format({
            "Price":"{:,.0f}","FairValue_Base":"{:,.0f}","Upside_Base":"{:.1%}","PB_Current":"{:.2f}x","ROE_Used":"{:.1%}","NPL":"{:.1%}","CAR":"{:.1%}","InvestmentScore":"{:.0f}"
        }),hide_index=True,use_container_width=True,height=400)

with tabs[1]:
    st.subheader("Sàng lọc cổ phiếu ngân hàng")
    c1,c2,c3,c4=st.columns(4)
    groups=["Tất cả"]+sorted(summary.PeerGroup.dropna().astype(str).unique().tolist())
    grp=c1.selectbox("Nhóm ngân hàng",groups)
    minroe=c2.slider("ROE tối thiểu",0.0,.35,.10,.01)
    maxpb=c3.slider("P/B tối đa",.3,4.0,2.0,.1)
    minscore=c4.slider("Điểm đầu tư tối thiểu",0,100,50,5)
    z=summary.copy()
    if grp!="Tất cả":z=z[z.PeerGroup.astype(str).eq(grp)]
    z=z[(z.ROE_Used>=minroe)&(z.PB_Current<=maxpb)&(z.InvestmentScore>=minscore)]
    cols=["Ticker","PeerGroup","Price","FairValue_Base","Upside_Base","PB_Current","PTBV_Current","PE_Current","ROE_Used","NIM","NPL","CAR","CASA","InvestmentScore","InvestmentView"]
    st.dataframe(safe(z[cols].sort_values("InvestmentScore",ascending=False)).style.format({
        "Price":"{:,.0f}","FairValue_Base":"{:,.0f}","Upside_Base":"{:.1%}","PB_Current":"{:.2f}x","PTBV_Current":"{:.2f}x","PE_Current":"{:.1f}x","ROE_Used":"{:.1%}","NIM":"{:.1%}","NPL":"{:.1%}","CAR":"{:.1%}","CASA":"{:.1%}","InvestmentScore":"{:.0f}"
    }),hide_index=True,use_container_width=True)

with tabs[2]:
    st.subheader(f"Hồ sơ ngân hàng - {selected}")
    c1,c2,c3,c4,c5,c6=st.columns(6)
    c1.metric("ROE",pct(row.ROE_Used)); c2.metric("ROA",pct(row.ROA)); c3.metric("NIM",pct(row.NIM))
    c4.metric("NPL",pct(row.NPL)); c5.metric("CAR",pct(row.CAR)); c6.metric("CASA",pct(row.CASA))
    st.markdown(f"""<div class="analysis-box"><b>VỊ THẾ & TĂNG TRƯỞNG</b><br>{business_profile(row.to_dict(),peer_row)}</div>""",unsafe_allow_html=True)

    score_cols=["ProfitabilityScore","GrowthScore","AssetQualityScore","FundingScore","CapitalScore","ValuationScore"]
    score_names=["Sinh lời","Tăng trưởng","Chất lượng tài sản","Nguồn vốn","An toàn vốn","Định giá"]
    scores=[num(row.get(c)) for c in score_cols]
    fig=go.Figure(go.Bar(x=[x or 0 for x in scores],y=score_names,orientation="h",text=[f"{x:.0f}" if x is not None else "N/A" for x in scores],textposition="outside"))
    fig.update_layout(title="Thẻ điểm 6 trụ cột",xaxis_range=[0,105],height=380,xaxis_title="Điểm / 100")
    st.plotly_chart(fig,use_container_width=True)

    left,right=st.columns(2)
    with left:
        h=hist[hist.Ticker.astype(str).eq(str(selected))].copy() if len(hist) else pd.DataFrame()
        if len(h):
            h["Value"]=pd.to_numeric(h.Value,errors="coerce")
            q=h[h.Metric.astype(str).isin(["ROE","ROA","NIM","NPL","CAR","CASA"])].copy()
            if len(q):
                fig=px.line(q,x="Period",y="Value",color="Metric",markers=True,title="Lịch sử chỉ tiêu tài chính")
                fig.update_yaxes(tickformat=".1%"); st.plotly_chart(fig,use_container_width=True)
    with right:
        p=prices[prices.Ticker.astype(str).eq(str(selected))].copy() if len(prices) else pd.DataFrame()
        if len(p):
            p["Date"]=pd.to_datetime(p.Date,errors="coerce"); p["Close"]=pd.to_numeric(p.Close,errors="coerce")
            st.plotly_chart(px.line(p,x="Date",y="Close",title="Diễn biến giá cổ phiếu"),use_container_width=True)

    st.markdown("### Nhận định chuyên môn")
    st.write("**Sinh lời:** "+profitability_text(row.to_dict()))
    st.write("**Chất lượng tài sản:** "+asset_quality_text(row.to_dict()))
    st.write("**Nguồn vốn:** "+funding_text(row.to_dict()))
    st.write("**Vốn:** "+capital_text(row.to_dict()))

with tabs[3]:
    st.subheader(f"Định giá cổ phiếu - {selected}")
    a,b,c,d,e=st.columns(5)
    a.metric("Giá thị trường",money(row.Price))
    b.metric("Giá trị hợp lý cơ sở",money(row.FairValue_Base),pct(row.Upside_Base))
    c.metric("Kịch bản thận trọng",money(row.FairValue_Bear))
    d.metric("Kịch bản tích cực",money(row.FairValue_Bull))
    e.metric("P/B hợp lý",mult(row.JustifiedPB))
    st.markdown(f"""<div class="analysis-box"><b>KẾT LUẬN ĐỊNH GIÁ</b><br>{valuation_text(row.to_dict())}</div>""",unsafe_allow_html=True)

    m=methods[methods.Ticker.astype(str).eq(str(selected))].copy()
    if len(m):
        m["FairValuePerShare"]=pd.to_numeric(m.FairValuePerShare,errors="coerce")
        fig=px.bar(m.dropna(subset=["FairValuePerShare"]),x="Method",y="FairValuePerShare",title="Football Field - giá trị hợp lý theo phương pháp")
        fig.add_hline(y=row.Price,line_dash="dash",annotation_text="Giá thị trường")
        fig.update_layout(height=430,yaxis_title="VND/cp",xaxis_title="")
        st.plotly_chart(fig,use_container_width=True)
        if not presentation:
            st.dataframe(m[["Method","FairValuePerShare","MarketPrice","Upside","DataType"]].style.format({
                "FairValuePerShare":"{:,.0f}","MarketPrice":"{:,.0f}","Upside":"{:.1%}"
            }),hide_index=True,use_container_width=True)

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
    q=summary.dropna(subset=["ROE_Used","PB_Current"])
    fig=px.scatter(q,x="ROE_Used",y="PB_Current",color="PeerGroup",text="Ticker",size="TotalAssets",hover_data=["NPL","CAR","Upside_Base","InvestmentScore"],title="ROE - P/B: chất lượng sinh lời và định giá")
    fig.update_traces(textposition="top center"); fig.update_xaxes(tickformat=".0%"); fig.update_layout(height=560)
    st.plotly_chart(fig,use_container_width=True)

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
    st.warning("Đây là mô phỏng giá trị quyền kiểm soát, không phải giá chào mua quan sát. Control premium, synergy, integration cost và recapitalization là ASSUMPTION.")
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
    st.subheader("Báo cáo chính thức & Quản trị mô hình")
    st.markdown('<div class="report-box">',unsafe_allow_html=True)
    st.markdown(f"### Xuất báo cáo khoảng 10 trang A4 - {selected}")
    report_mode=st.radio("Nội dung báo cáo",["Định giá cổ phiếu","M&A / Thâu tóm"],horizontal=True)
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
            pdf_bytes=generate_pdf_bytes(ROOT,selected,rmode)
            docx_bytes=generate_docx_bytes(ROOT,selected,rmode)
            b1,b2=st.columns(2)
            b1.download_button("📄 Tải PDF A4",pdf_bytes,file_name=f"{selected}_Bao_cao_Phan_tich_Dinh_gia.pdf",mime="application/pdf",use_container_width=True)
            b2.download_button("📝 Tải Word",docx_bytes,file_name=f"{selected}_Bao_cao_Phan_tich_Dinh_gia.docx",mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",use_container_width=True)
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
