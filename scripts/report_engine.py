
from pathlib import Path
from io import BytesIO
import os, math, json, tempfile
from xml.sax.saxutils import escape
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from docx import Document
from docx.shared import Mm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn

try:
    from scripts.narrative_engine import (
        executive_summary,business_profile,profitability_text,asset_quality_text,
        funding_text,capital_text,valuation_text,catalysts_risks,mna_text,pct,mult,money,bn,n
    )
except Exception:
    from narrative_engine import (
        executive_summary,business_profile,profitability_text,asset_quality_text,
        funding_text,capital_text,valuation_text,catalysts_risks,mna_text,pct,mult,money,bn,n
    )
try:
    from scripts.quality_engine import assess_report_quality, normalization_flags
except Exception:
    from quality_engine import assess_report_quality, normalization_flags
try:
    from scripts.strategic_case import load_research, strategic_reasonableness, reasonableness_conclusion, all_bank_means
except Exception:
    from strategic_case import load_research, strategic_reasonableness, reasonableness_conclusion, all_bank_means

PAGE_W,PAGE_H=A4
MARGIN=16*mm

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
    "ROE":"ROE","ROA":"ROA","NIM":"NIM",
    "NPL":"Tỷ lệ nợ xấu (NPL)",
    "CAR":"Hệ số an toàn vốn (CAR)",
    "CIR":"Tỷ lệ chi phí/thu nhập (CIR)",
    "LDR":"Tỷ lệ cho vay/tiền gửi (LDR)",
    "CASA":"Tỷ lệ tiền gửi không kỳ hạn (CASA)",
    "PB":"P/B","PE":"P/E",
}
METHOD_VI={
    "ResidualIncome":"Thu nhập thặng dư",
    "JustifiedPB":"P/B hợp lý",
    "PeerPB":"P/B nhóm so sánh",
    "HistoricalPB":"P/B lịch sử",
}
def _metric_vi(metric):
    return METRIC_VI.get(str(metric),str(metric))

def _set_y_padding(ax, values, percent=False):
    vals=pd.to_numeric(pd.Series(values),errors="coerce").dropna()
    if vals.empty:return
    lo=float(vals.min()); hi=float(vals.max())
    span=hi-lo
    if span<=0:
        span=max(abs(hi)*.20,.01 if percent else 1.0)
    pad=max(span*.15,.003 if percent else abs(hi)*.03 if hi else 1.0)
    lower=lo-pad; upper=hi+pad
    if percent and lo>=0: lower=max(0.0,lower)
    if lower==upper: upper=lower+(0.01 if percent else 1.0)
    ax.set_ylim(lower,upper)


def _load(root):
    root=Path(root); data=root/"data"; out=data/"model_outputs"
    def csv(p):
        try:return pd.read_csv(p)
        except Exception:return pd.DataFrame()
    return {
        "summary":csv(out/"valuation_summary.csv"),
        "methods":csv(out/"valuation_methods.csv"),
        "peer":csv(out/"peer_summary.csv"),
        "mna":csv(out/"mna_baseline.csv"),
        "hist":csv(data/"bank_history_long.csv"),
        "prices":csv(data/"price_history.csv"),
        "precedents":csv(root/"config/transaction_precedents.csv"),
        "research":load_research(root),
        "cfg":json.loads((root/"config/model_config.json").read_text(encoding="utf-8")) if (root/"config/model_config.json").exists() else {}
    }

def _font_paths():
    candidates=[]
    try:
        import matplotlib
        mpl_fonts=Path(matplotlib.get_data_path())/"fonts"/"ttf"
        candidates.append((str(mpl_fonts/"DejaVuSans.ttf"),str(mpl_fonts/"DejaVuSans-Bold.ttf")))
    except Exception:
        pass
    candidates += [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf","/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf","/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    ]
    for a,b in candidates:
        if Path(a).exists() and Path(b).exists(): return a,b
    return None,None

def _register_pdf_fonts():
    reg,bold=_font_paths()
    if not reg or not bold:
        raise RuntimeError("Không tìm thấy font Unicode để xuất PDF tiếng Việt; project cần matplotlib/DejaVu Sans.")
    if "VNFont" not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont("VNFont",reg))
    if "VNFont-Bold" not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont("VNFont-Bold",bold))
    return "VNFont","VNFont-Bold"

def _period_sort(s):
    import re
    st=str(s).upper().strip()
    y=re.search(r"(20\d{2})",st)
    q=re.search(r"Q\s*([1-4])",st)
    return (int(y.group(1)) if y else 0,int(q.group(1)) if q else 0,st)

def _period_to_date(s):
    """Convert quarter labels such as 2025-Q2 / 2025Q2 to a true timestamp.
    Using a real date axis prevents categorical-axis reordering when target and peer
    series have different missing quarters.
    """
    y,q,_=_period_sort(s)
    if y and q:
        return pd.Timestamp(year=y,month=(q-1)*3+1,day=1)
    if y:
        return pd.Timestamp(year=y,month=1,day=1)
    return pd.NaT

def _with_period_date(df):
    if df is None or df.empty:
        return df
    out=df.copy()
    out["_date"]=out["Period"].map(_period_to_date)
    out=out.dropna(subset=["_date"]).sort_values(["_date","Metric"] if "Metric" in out.columns else ["_date"])
    return out

def _set_quarter_ticks(ax, frames, max_ticks=10):
    dates=[]
    for f in frames:
        if f is not None and len(f) and "_date" in f.columns:
            dates.extend(pd.to_datetime(f["_date"],errors="coerce").dropna().tolist())
    if not dates:
        return
    uniq=sorted(pd.unique(pd.Series(dates)))
    step=max(1,int(np.ceil(len(uniq)/max_ticks)))
    ticks=uniq[::step]
    if uniq[-1] not in ticks: ticks.append(uniq[-1])
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{pd.Timestamp(d).year}-Q{((pd.Timestamp(d).month-1)//3)+1}" for d in ticks],rotation=45,ha="right",fontsize=7)

def _metric_history(hist,ticker,metrics):
    if hist.empty:return pd.DataFrame()
    x=hist[hist["Ticker"].astype(str).eq(str(ticker)) & hist["Metric"].astype(str).isin(metrics)].copy()
    if x.empty:return x
    x["Value"]=pd.to_numeric(x["Value"],errors="coerce")
    x=x.dropna(subset=["Value"])
    ratio_metrics={"ROE","ROA","NIM","NPL","CAR","CIR","LDR","CASA","PB","PE"}
    x=x[~(x["Metric"].astype(str).isin(ratio_metrics) & (x["Value"]==0))]
    x=x[~((x["Metric"].astype(str)=="CAR") & (x["Value"]<=0))]
    return _with_period_date(x)

def _peer_metric_history(hist,metrics):
    if hist.empty:return pd.DataFrame()
    x=hist[hist["Metric"].astype(str).isin(metrics)].copy()
    if x.empty:return x
    x["Value"]=pd.to_numeric(x["Value"],errors="coerce")
    x=x.dropna(subset=["Value"])
    ratio_metrics={"ROE","ROA","NIM","NPL","CAR","CIR","LDR","CASA","PB","PE"}
    x=x[~(x["Metric"].astype(str).isin(ratio_metrics) & (x["Value"]==0))]
    x=x[~((x["Metric"].astype(str)=="CAR") & (x["Value"]<=0))]
    x["_date"]=x["Period"].map(_period_to_date)
    x=x.dropna(subset=["_date"])
    out=x.groupby(["_date","Metric"],as_index=False).agg(Value=("Value","mean"),BankCount=("Ticker","nunique"))
    return out.sort_values(["_date","Metric"])

def _fig_to_png(fig):
    bio=BytesIO()
    fig.savefig(bio,format="png",dpi=160,bbox_inches="tight")
    plt.close(fig); bio.seek(0)
    return bio

def _chart_history(hist,ticker,metrics,title,percent=False):
    x=_metric_history(hist,ticker,metrics); pm=_peer_metric_history(hist,metrics)
    fig,ax=plt.subplots(figsize=(7.4,3.0))
    plotted=[]
    if x.empty:
        ax.text(.5,.5,"Chưa có đủ dữ liệu lịch sử",ha="center",va="center"); ax.set_axis_off()
    else:
        for metric in metrics:
            label=_metric_vi(metric)
            g=x[x["Metric"].astype(str).eq(str(metric))].sort_values("_date")
            if g.empty: continue
            plotted.extend(g["Value"].tolist())
            line=ax.plot(g["_date"],g["Value"],marker="o",markersize=3.5,linewidth=1.8,label=f"{ticker} - {label}")[0]
            pg=pm[pm["Metric"].astype(str).eq(str(metric))].sort_values("_date")
            if len(pg):
                plotted.extend(pg["Value"].tolist())
                ax.plot(pg["_date"],pg["Value"],linestyle="--",linewidth=1.7,color=line.get_color(),alpha=.70,label=f"Bình quân 20 NH - {label}")
        ax.set_title(title+" · so với bình quân 20 ngân hàng",fontsize=10.5)
        ax.grid(alpha=.2); ax.legend(fontsize=6.8,ncol=2,loc="best")
        _set_quarter_ticks(ax,[x,pm])
        if percent: ax.yaxis.set_major_formatter(lambda v,pos:f"{v:.1%}")
        _set_y_padding(ax,plotted,percent=percent)
        fig.tight_layout()
    return _fig_to_png(fig)


def _chart_peer(summary,ticker):
    fig,ax=plt.subplots(figsize=(7.4,3.4))
    q=summary.dropna(subset=["ROE_Used","PB_Current"]).copy()
    if q.empty:
        ax.text(.5,.5,"Chưa có đủ dữ liệu peer",ha="center",va="center"); ax.set_axis_off()
    else:
        ax.scatter(q["ROE_Used"],q["PB_Current"],s=45,alpha=.75)
        for _,r in q.iterrows():
            ax.annotate(str(r["Ticker"]),(r["ROE_Used"],r["PB_Current"]),fontsize=7,xytext=(3,3),textcoords="offset points")
        cur=q[q["Ticker"].astype(str).eq(str(ticker))]
        if len(cur): ax.scatter(cur["ROE_Used"],cur["PB_Current"],s=120,marker="*")
        mean_roe=pd.to_numeric(q["ROE_Used"],errors="coerce").mean(); mean_pb=pd.to_numeric(q["PB_Current"],errors="coerce").mean()
        ax.axvline(mean_roe,linestyle="--",alpha=.65,label=f"ROE bình quân 20 NH {mean_roe:.1%}"); ax.axhline(mean_pb,linestyle="--",alpha=.65,label=f"P/B bình quân 20 NH {mean_pb:.2f}x")
        ax.set_xlabel("ROE"); ax.set_ylabel("P/B (x)"); ax.set_title("Bản đồ ROE - P/B · benchmark bình quân 20 ngân hàng"); ax.legend(fontsize=7)
        ax.xaxis.set_major_formatter(lambda v,pos:f"{v:.0%}"); ax.grid(alpha=.2)
    return _fig_to_png(fig)

def _chart_valuation(methods,row,summary=None):
    fig,ax=plt.subplots(figsize=(7.4,3.3))
    m=methods[methods["Ticker"].astype(str).eq(str(row.get("Ticker")))].copy() if len(methods) else pd.DataFrame()
    if m.empty:
        ax.text(.5,.5,"Chưa có kết quả theo phương pháp",ha="center",va="center"); ax.set_axis_off()
    else:
        m["FairValuePerShare"]=pd.to_numeric(m["FairValuePerShare"],errors="coerce"); m=m.dropna(subset=["FairValuePerShare"]); m["FairValuePerShare"]=m["FairValuePerShare"]*1000
        m["Phương pháp"]=m["Method"].map(lambda x: METHOD_VI.get(str(x),str(x)))
        ax.bar(m["Phương pháp"],m["FairValuePerShare"])
        if n(row.get("Price")) is not None: ax.axhline(n(row.get("Price"))*1000,linestyle="--",label="Giá thị trường")
        if summary is not None and len(summary) and n(row.get("BVPS_Used")) is not None:
            mpb=pd.to_numeric(summary["PB_Current"],errors="coerce").mean()
            if pd.notna(mpb): ax.axhline(mpb*n(row.get("BVPS_Used"))*1000,linestyle=":",linewidth=2,label=f"Giá hàm ý P/B bình quân 20 NH ({mpb:.2f}x)")
        slo=n(row.get("StrategicPriceLow")); shi=n(row.get("StrategicPriceHigh"))
        if slo is not None and shi is not None: ax.axhspan(slo*1000,shi*1000,alpha=.10,label="Vùng giá chiến lược/M&A")
        ax.set_title("Giá trị theo phương pháp · so sánh bình quân 20 ngân hàng"); ax.set_ylabel("VND/cp"); ax.tick_params(axis="x",rotation=20,labelsize=8); ax.legend(fontsize=7)
    return _fig_to_png(fig)


def _chart_scores(row,summary=None):
    names=["Sinh lời","Tăng trưởng","Chất lượng TS","Nguồn vốn","An toàn vốn","Định giá"]
    score_cols=["ProfitabilityScore","GrowthScore","AssetQualityScore","FundingScore","CapitalScore","ValuationScore"]
    vals=[row.get(c) for c in score_cols]; fig,ax=plt.subplots(figsize=(7.4,3.1)); y=np.arange(len(names)); vv=[n(v) or 0 for v in vals]
    ax.barh(y,vv); ax.set_yticks(y,names); ax.set_xlim(0,100); ax.set_title("Thẻ điểm 6 trụ cột · so với bình quân 20 ngân hàng")
    for i,v in enumerate(vv): ax.text(v+1,i,f"{v:.0f}",va="center",fontsize=8)
    if summary is not None and len(summary):
        means=[pd.to_numeric(summary[c],errors="coerce").mean() for c in score_cols]
        ax.plot(means,y,linestyle="--",marker="o",label="Bình quân 20 NH"); ax.legend(fontsize=7)
    return _fig_to_png(fig)


def _chart_sensitivity(row):
    bv=n(row.get("BVPS_Used")); price=n(row.get("Price"))
    coe=n(row.get("COE")) or .13; g=n(row.get("LTG")) or .05; roe=n(row.get("NormalizedROE_Used")) or .15
    fig,ax=plt.subplots(figsize=(7.4,3.4))
    if bv is None:
        ax.text(.5,.5,"Chưa có BVPS để lập sensitivity",ha="center",va="center"); ax.set_axis_off()
    else:
        coes=np.array([coe-.02,coe-.01,coe,coe+.01,coe+.02])
        roes=np.array([roe-.04,roe-.02,roe,roe+.02,roe+.04])
        mat=np.zeros((len(roes),len(coes)))
        for i,r in enumerate(roes):
            for j,c in enumerate(coes):
                den=max(c-g,.01)
                pb=max(.3,min(4.0,(r-g)/den))
                mat[i,j]=pb*bv
        display_mat=mat*1000.0
        im=ax.imshow(display_mat,aspect="auto")
        ax.set_xticks(range(len(coes)),[f"{x:.1%}" for x in coes])
        ax.set_yticks(range(len(roes)),[f"{x:.1%}" for x in roes])
        ax.set_xlabel("Chi phí vốn chủ sở hữu (COE)"); ax.set_ylabel("ROE chuẩn hóa")
        ax.set_title("Sensitivity giá trị cơ bản: ROE x COE")
        for i in range(display_mat.shape[0]):
            for j in range(display_mat.shape[1]): ax.text(j,i,f"{display_mat[i,j]/1000:.1f}k",ha="center",va="center",fontsize=7)
        fig.colorbar(im,ax=ax,fraction=.035,pad=.03,label="VND/cp")
    return _fig_to_png(fig)

def _chart_price(prices,ticker):
    fig,ax=plt.subplots(figsize=(7.4,3.0)); p=prices[prices["Ticker"].astype(str).eq(str(ticker))].copy() if len(prices) else pd.DataFrame()
    if p.empty:
        ax.text(.5,.5,"Chưa có lịch sử giá",ha="center",va="center"); ax.set_axis_off()
    else:
        allp=prices.copy(); allp["Date"]=pd.to_datetime(allp["Date"],errors="coerce"); allp["Close"]=pd.to_numeric(allp["Close"],errors="coerce"); allp=allp.dropna(subset=["Date","Close"]).sort_values(["Ticker","Date"])
        allp["Norm"]=allp.groupby("Ticker")["Close"].transform(lambda s: s/s.iloc[0]*100 if len(s) and s.iloc[0] else np.nan)
        bench=allp.groupby("Date",as_index=False)["Norm"].mean(); p=allp[allp["Ticker"].astype(str).eq(str(ticker))].copy()
        ax.plot(p["Date"],p["Norm"],label=f"{ticker} (chỉ số=100)"); ax.plot(bench["Date"],bench["Norm"],linestyle="--",label="Bình quân 20 NH (chỉ số=100)")
        ax.set_title("Diễn biến giá tương đối · so với bình quân 20 ngân hàng"); ax.set_ylabel("Chỉ số giá (đầu kỳ=100)"); ax.grid(alpha=.2); ax.legend(fontsize=7)
    return _fig_to_png(fig)


def _pdf_styles(font,bold):
    styles=getSampleStyleSheet()
    return {
        "h1":ParagraphStyle("h1",fontName=bold,fontSize=15,leading=19,textColor=colors.HexColor("#0F2747"),spaceAfter=5),
        "h2":ParagraphStyle("h2",fontName=bold,fontSize=11.5,leading=15,textColor=colors.HexColor("#0F2747"),spaceAfter=4),
        "body":ParagraphStyle("body",fontName=font,fontSize=8.8,leading=12.2,textColor=colors.HexColor("#222222")),
        "small":ParagraphStyle("small",fontName=font,fontSize=7.3,leading=9.5,textColor=colors.HexColor("#555555")),
        "kpi":ParagraphStyle("kpi",fontName=bold,fontSize=9.5,leading=12,textColor=colors.HexColor("#0F2747"),alignment=TA_CENTER),
    }

def _draw_para(c,text,style,x,y,w,h):
    safe_text=escape(str(text)).replace("\n","<br/>")
    p=Paragraph(safe_text,style)
    _,ph=p.wrap(w,h); p.drawOn(c,x,y-ph); return y-ph

def _draw_header(c,title,ticker,page,font,bold,stamp=None):
    c.setFillColor(colors.HexColor("#0F2747")); c.rect(0,PAGE_H-20*mm,PAGE_W,20*mm,fill=1,stroke=0)
    c.setFillColor(colors.white); c.setFont(bold,11); c.drawString(MARGIN,PAGE_H-12.5*mm,title)
    c.setFont(font,7.5); c.drawRightString(PAGE_W-MARGIN,PAGE_H-12.5*mm,f"{ticker} | Trang {page}/10")
    if stamp and stamp!="ĐỦ ĐIỀU KIỆN PHÁT HÀNH":
        c.saveState()
        c.setFillColor(colors.HexColor("#B42318")); c.setFont(bold,18)
        c.translate(PAGE_W/2,PAGE_H/2); c.rotate(32)
        c.drawCentredString(0,0,stamp)
        c.restoreState()
    c.setFillColor(colors.HexColor("#555555")); c.setFont(font,6.8)
    c.setFont(font,6.2)
    c.drawString(MARGIN,7*mm,"Nguồn: Vnstock/BCTC + mô hình nội bộ. Dữ liệu thực / số liệu tính toán / giả định được tách riêng.")
    c.drawRightString(PAGE_W-MARGIN,7*mm,"Tham khảo - không phải khuyến nghị đầu tư/chào mua.")

def _draw_image(c,bio,x,y,w,h):
    from reportlab.lib.utils import ImageReader
    bio.seek(0); c.drawImage(ImageReader(bio),x,y,width=w,height=h,preserveAspectRatio=True,anchor="c")

def _kpi_table(c,items,styles,y):
    data=[[Paragraph(k,styles["small"]),Paragraph(v,styles["kpi"])] for k,v in items]
    t=Table(data,colWidths=[31*mm,31*mm],rowHeights=12*mm)
    t.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),.35,colors.HexColor("#D9E2F3")),
        ("BACKGROUND",(0,0),(0,-1),colors.HexColor("#F3F6FA")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("ALIGN",(1,0),(1,-1),"CENTER"),
    ]))
    tw,th=t.wrap(62*mm,80*mm); t.drawOn(c,PAGE_W-MARGIN-tw,y-th); return y-th

def _report_context(root,ticker):
    d=_load(root); summary=d["summary"]
    row=summary[summary["Ticker"].astype(str).eq(str(ticker))]
    if row.empty: raise ValueError(f"Không có valuation_summary cho {ticker}")
    row=row.iloc[0].to_dict()
    peer_row=None
    if len(d["peer"]):
        q=d["peer"][d["peer"]["PeerGroup"].astype(str).eq(str(row.get("PeerGroup")))]
        if len(q): peer_row=q.iloc[0].to_dict()
    mna_row=None
    if len(d["mna"]):
        q=d["mna"][d["mna"]["Ticker"].astype(str).eq(str(ticker))]
        if len(q): mna_row=q.iloc[0].to_dict()
    return d,row,peer_row,mna_row

def generate_pdf_bytes(root,ticker,mode="investment"):
    d,row,peer_row,mna_row=_report_context(root,ticker)
    font,bold=_register_pdf_fonts(); st=_pdf_styles(font,bold)
    bio=BytesIO(); c=canvas.Canvas(bio,pagesize=A4)
    title="BÁO CÁO PHÂN TÍCH, ĐỊNH GIÁ & M&A NGÂN HÀNG · ENGINE V6.2"
    cats,risks=catalysts_risks(row)
    qa=assess_report_quality(row,d["cfg"],d["hist"],d["prices"])
    norm_flags=normalization_flags(row,d["cfg"],d["prices"])
    strategic_case=strategic_reasonableness(row,d["cfg"],d.get("research"))
    strategic_case_text=reasonableness_conclusion(strategic_case)
    allmean=all_bank_means(d["summary"])
    stamp=qa["ReportStamp"]

    # Page 1
    _draw_header(c,title,ticker,1,font,bold,stamp)
    y=PAGE_H-29*mm; y=_draw_para(c,f"1. TÓM TẮT ĐIỀU HÀNH - {ticker}",st["h1"],MARGIN,y,120*mm,30*mm)
    y=_draw_para(c,executive_summary(row,peer_row),st["body"],MARGIN,y-2*mm,118*mm,70*mm)
    kpis=[("Giá thị trường",money(row.get("Price"))),("Giá trị cơ bản",money(row.get("FairValue_Base")))]
    if n(row.get("StrategicPriceLow")) is not None:
        kpis += [("Giá chiến lược thấp",money(row.get("StrategicPriceLow"))),("Giá chiến lược cao",money(row.get("StrategicPriceHigh")))]
    else:
        kpis += [("P/B hiện tại",mult(row.get("PB_Current"))),("ROE",pct(row.get("ROE_Used")))]
    kpis += [("NPL",pct(row.get("NPL"))),("Điểm cơ bản",f"{n(row.get('FundamentalScore')):.0f}/100" if n(row.get("FundamentalScore")) is not None else "N/A")]
    _kpi_table(c,kpis,st,PAGE_H-32*mm)
    _draw_image(c,_chart_scores(row,d["summary"]),MARGIN,31*mm,175*mm,66*mm)
    _draw_para(c,f"Trạng thái báo cáo: {qa['ReportStatus']} | Độ phủ kiểm soát: {qa['ReportCoverage']:.0%} | Thiếu chỉ tiêu lõi: {qa['CoreMissingCount']}",st["small"],MARGIN,27*mm,175*mm,12*mm)
    if n(row.get("StrategicPriceLow")) is not None:
        _draw_para(c,f"Thông tin thị trường/M&A: {money(row.get('StrategicPriceLow'))} - {money(row.get('StrategicPriceHigh'))} | Nguồn: {row.get('StrategicSource','N/A')} | Không phải giá trị cơ bản.",st["small"],MARGIN,20*mm,175*mm,12*mm)
    c.showPage()

    # Page 2
    _draw_header(c,title,ticker,2,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"2. HỒ SƠ NGÂN HÀNG & VỊ THẾ TƯƠNG ĐỐI",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,business_profile(row,peer_row),st["body"],MARGIN,y-2*mm,175*mm,45*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["TotalAssets"],"Tổng tài sản",False),MARGIN,151*mm,175*mm,43*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["GrossLoans"],"Dư nợ khách hàng",False),MARGIN,99*mm,175*mm,43*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["CustomerDeposits"],"Tiền gửi khách hàng",False),MARGIN,47*mm,175*mm,43*mm)
    c.showPage()

    # Page 3
    _draw_header(c,title,ticker,3,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"3. KHẢ NĂNG SINH LỜI & HIỆU QUẢ HOẠT ĐỘNG",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,profitability_text(row,peer_row),st["body"],MARGIN,y-2*mm,175*mm,42*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["ROE"],"Tỷ suất sinh lời trên vốn chủ sở hữu (ROE)",True),MARGIN,126*mm,84*mm,50*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["ROA"],"Tỷ suất sinh lời trên tổng tài sản (ROA)",True),MARGIN+91*mm,126*mm,84*mm,50*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["NIM"],"Biên lãi ròng (NIM)",True),MARGIN,67*mm,84*mm,50*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["CIR"],"Tỷ lệ chi phí/thu nhập (CIR)",True),MARGIN+91*mm,67*mm,84*mm,50*mm)
    c.showPage()

    # Page 4
    _draw_header(c,title,ticker,4,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"4. CHẤT LƯỢNG TÀI SẢN & CHI PHÍ TÍN DỤNG",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,asset_quality_text(row,peer_row),st["body"],MARGIN,y-2*mm,175*mm,42*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["NPL"],"Xu hướng tỷ lệ nợ xấu (NPL)",True),MARGIN,69*mm,175*mm,108*mm)
    y=61*mm
    _draw_para(c,"Lưu ý: Provision Expense có thể được Vnstock/BCTC thể hiện theo đơn vị tiền tệ, do đó cần đọc cùng nguồn dữ liệu gốc khi so sánh với tỷ lệ NPL.",st["small"],MARGIN,y,175*mm,20*mm)
    c.showPage()

    # Page 5
    _draw_header(c,title,ticker,5,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"5. NGUỒN VỐN, THANH KHOẢN & CHI PHÍ HUY ĐỘNG",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,funding_text(row,peer_row),st["body"],MARGIN,y-2*mm,175*mm,45*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["CASA"],"Tỷ lệ tiền gửi không kỳ hạn (CASA)",True),MARGIN,124*mm,175*mm,58*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["LDR"],"Tỷ lệ cho vay trên tiền gửi (LDR)",True),MARGIN,59*mm,175*mm,58*mm)
    c.showPage()

    # Page 6
    _draw_header(c,title,ticker,6,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"6. VỐN, KHẢ NĂNG CHỐNG CHỊU & NĂNG LỰC TĂNG TRƯỞNG",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,capital_text(row,peer_row),st["body"],MARGIN,y-2*mm,175*mm,45*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["CAR"],"Xu hướng hệ số an toàn vốn (CAR)",True),MARGIN,70*mm,175*mm,108*mm)
    c.showPage()

    # Page 7
    _draw_header(c,title,ticker,7,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"7. ĐỊNH GIÁ TƯƠNG ĐỐI & NHÓM SO SÁNH",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,valuation_text(row,peer_row),st["body"],MARGIN,y-2*mm,175*mm,43*mm)
    _draw_image(c,_chart_peer(d["summary"],ticker),MARGIN,82*mm,175*mm,95*mm)
    if peer_row:
        pdata=[["Chỉ tiêu",ticker,"Trung bình nhóm so sánh","Bình quân 20 NH"],
               ["ROE",pct(row.get("ROE_Used")),pct(peer_row.get("MeanROE")),pct(allmean.get("ROE_Used"))],
               ["NIM",pct(row.get("NIM")),pct(peer_row.get("MeanNIM")),pct(allmean.get("NIM"))],
               ["NPL",pct(row.get("NPL")),pct(peer_row.get("MeanNPL")),pct(allmean.get("NPL"))],
               ["CAR",pct(row.get("CAR")),pct(peer_row.get("MeanCAR")),pct(allmean.get("CAR"))],
               ["CASA",pct(row.get("CASA")),pct(peer_row.get("MeanCASA")),pct(allmean.get("CASA"))],
               ["P/B",mult(row.get("PB_Current")),mult(peer_row.get("MeanPB")),mult(allmean.get("PB_Current"))]]
        tt=Table(pdata,colWidths=[34*mm,34*mm,34*mm,40*mm]); tt.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.35,colors.grey),("FONTNAME",(0,0),(-1,-1),font),("FONTSIZE",(0,0),(-1,-1),7.5),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF0F7"))]))
        tw,th=tt.wrap(145*mm,60*mm); tt.drawOn(c,MARGIN,25*mm)
    c.showPage()

    # Page 8
    _draw_header(c,title,ticker,8,font,bold,stamp); y=PAGE_H-29*mm
    if mode=="mna":
        y=_draw_para(c,"8. GIÁ TRỊ QUYỀN KIỂM SOÁT & MÔ PHỎNG M&A",st["h1"],MARGIN,y,170*mm,20*mm)
        y=_draw_para(c,mna_text(row,mna_row),st["body"],MARGIN,y-2*mm,175*mm,55*mm)
        if mna_row:
            data=[["Giá trị độc lập",bn(mna_row.get("Giá trị độc lậpEquityValue"))],["Giá trị hiện tại của cộng hưởng",bn(mna_row.get("PV_Synergies"))],["Chi phí tích hợp",bn(mna_row.get("IntegrationCost"))],["Giá trị thanh toán",bn(mna_row.get("IllustrativeGiá trị thanh toán"))],["P/B giao dịch",mult(mna_row.get("ImpliedPB"))],["P/TBV giao dịch",mult(mna_row.get("ImpliedPTBV"))]]
            t=Table(data,colWidths=[60*mm,65*mm]); t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.4,colors.grey),("FONTNAME",(0,0),(-1,-1),font),("FONTSIZE",(0,0),(-1,-1),8.5),("BACKGROUND",(0,0),(0,-1),colors.HexColor("#F3F6FA"))]))
            tw,th=t.wrap(130*mm,100*mm); t.drawOn(c,MARGIN,y-th-10*mm)
    else:
        y=_draw_para(c,"8. ĐỊNH GIÁ CƠ BẢN & GIÁ TRỊ CHIẾN LƯỢC",st["h1"],MARGIN,y,170*mm,20*mm)
        y=_draw_para(c,valuation_text(row,peer_row),st["body"],MARGIN,y-2*mm,175*mm,38*mm)
        if n(row.get("StrategicPriceLow")) is not None:
            strategic=(f"Lớp giá trị chiến lược/M&A được ghi nhận riêng ở {money(row.get('StrategicPriceLow'))} - {money(row.get('StrategicPriceHigh'))}. "
                       f"Nguồn: {row.get('StrategicSource','N/A')}; ngày {row.get('StrategicAsOfDate','N/A')}; mức độ tin cậy {row.get('StrategicConfidence','N/A')}. "
                       "Khoảng này không được dùng để ép ngược giá trị cơ bản; chênh lệch cần được giải thích bằng quy mô lô, quyền kiểm soát, scarcity, tái cơ cấu và synergy.")
            y=_draw_para(c,strategic,st["body"],MARGIN,y-2*mm,175*mm,42*mm)
        _draw_image(c,_chart_valuation(d["methods"],row,d["summary"]),MARGIN,69*mm,175*mm,95*mm)
    c.showPage()

    # Page 9
    _draw_header(c,title,ticker,9,font,bold,stamp); y=PAGE_H-29*mm
    if mode=="mna":
        y=_draw_para(c,"9. PPA, GOODWILL & TÁC ĐỘNG TÁI CƠ CẤU",st["h1"],MARGIN,y,170*mm,20*mm)
        ppa=(
            "Trong acquisition method, giá mua được phân bổ vào tài sản và nợ phải trả có thể xác định theo giá trị hợp lý. "
            "Đối với ngân hàng, loan-book credit mark, chứng khoán, các nghĩa vụ ngoại bảng và tài sản vô hình liên quan đến "
            "franchise khách hàng/tiền gửi cần được thẩm định riêng. Goodwill chỉ là phần chênh lệch sau các điều chỉnh này. "
            "Trong trường hợp ngân hàng mục tiêu cần bổ sung vốn, recapitalization phải được trừ khỏi giá mua tối đa."
        )
        y=_draw_para(c,ppa,st["body"],MARGIN,y-2*mm,175*mm,55*mm)
        _draw_image(c,_chart_sensitivity(row),MARGIN,70*mm,175*mm,105*mm)
    else:
        y=_draw_para(c,"9. KIỂM TRA TÍNH HỢP LÝ 80.000–100.000 ĐỒNG/CP",st["h1"],MARGIN,y,170*mm,20*mm)
        if strategic_case.get("strategic_low") is not None:
            lo=strategic_case["low"]; hi=strategic_case["high"]
            data=[["Chỉ tiêu","80.000 đồng/cp","100.000 đồng/cp"],["Premium so với thị giá",pct(lo.get("premium_to_market")),pct(hi.get("premium_to_market"))],["P/B trên BVPS hiện tại",mult(lo.get("implied_pb_current")),mult(hi.get("implied_pb_current"))],["P/B hậu xử lý (BVPS +10k)",mult(lo.get("implied_pb_post_resolution")),mult(hi.get("implied_pb_post_resolution"))],["Giá trị lô 32,5%",bn((lo.get("block_consideration_bn") or 0)*1e9),bn((hi.get("block_consideration_bn") or 0)*1e9)],["Bao phủ 63.250 tỷ gốc+lãi",pct(lo.get("claim_recovery")),pct(hi.get("claim_recovery"))],["So với high-case công khai",pct(lo.get("premium_to_public_high")),pct(hi.get("premium_to_public_high"))]]
            tb=Table(data,colWidths=[72*mm,50*mm,50*mm]); tb.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.35,colors.HexColor("#CBD5E1")),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0F2747")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),bold),("FONTNAME",(0,1),(-1,-1),font),("FONTSIZE",(0,0),(-1,-1),7.4),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
            tw,th=tb.wrap(175*mm,100*mm); tb.drawOn(c,MARGIN,y-th-4*mm); y=y-th-8*mm
            y=_draw_para(c,"80.000 đồng/cp có thể xem là mức chiến lược tương đối dễ biện minh vì chỉ premium nhẹ so với thị giá và nằm sát high-case fundamental công khai. 100.000 đồng/cp là hợp lý có điều kiện: giá trị lô 32,5% tiến gần mức thu hồi đầy đủ 63.250 tỷ đồng, vì vậy cần xác suất xử lý cao cùng scarcity/quyền ảnh hưởng và giá trị hậu tái cơ cấu.",st["small"],MARGIN,y,175*mm,45*mm)
            _draw_para(c,"Đối chiếu nghiên cứu công khai 2026: HSC 57.600; MBS 58.800; VNDIRECT 73.000 (sensitivity 66.000–81.000); Vietcap 73.500; SBBS 66.200 đồng/cp. Vì vậy 80.000 nằm ở vùng high-case standalone, còn 100.000 cần strategic premium chứ không thể được gọi là standalone fair value.",st["small"],MARGIN,y-2*mm,175*mm,32*mm)
        else: _draw_para(c,"Không có dữ liệu market intelligence để kiểm tra giá chiến lược.",st["body"],MARGIN,y-2*mm,175*mm,42*mm)
    c.showPage()

    # Page 10
    _draw_header(c,title,ticker,10,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"10. KẾT LUẬN, ĐỘNG LỰC & RỦI RO",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,executive_summary(row,peer_row),st["body"],MARGIN,y-2*mm,175*mm,48*mm)
    y=_draw_para(c,"ĐỘNG LỰC TIỀM NĂNG",st["h2"],MARGIN,y-4*mm,175*mm,15*mm)
    for x in cats[:5]: y=_draw_para(c,"• "+x,st["body"],MARGIN+3*mm,y,170*mm,18*mm)-1*mm
    y=_draw_para(c,"RỦI RO CHÍNH",st["h2"],MARGIN,y-2*mm,175*mm,15*mm)
    for x in risks[:5]: y=_draw_para(c,"• "+x,st["body"],MARGIN+3*mm,y,170*mm,18*mm)-1*mm
    y=_draw_para(c,"ĐIỂM CẦN LƯU Ý KHI ĐỊNH GIÁ",st["h2"],MARGIN,y-2*mm,175*mm,15*mm)
    for x in norm_flags[:4]: y=_draw_para(c,"• "+x,st["small"],MARGIN+3*mm,y,170*mm,14*mm)-1*mm
    y=_draw_para(c,"GHI CHÚ PHƯƠNG PHÁP",st["h2"],MARGIN,y-1*mm,175*mm,15*mm)
    _draw_para(c,"Residual Income là phương pháp nội tại chính; P/B hợp lý, peer P/B và historical P/B là cross-check. Trong M&A, giá trị quyền kiểm soát, cộng hưởng, PPA và recapitalization được tách khỏi standalone fair value. Mọi assumption phải được gắn nhãn và không được trình bày như dữ liệu quan sát thực tế.",st["small"],MARGIN,y,175*mm,42*mm)
    c.save(); bio.seek(0); return bio.getvalue()

def _doc_font(doc):
    styles=doc.styles
    for style_name in ["Normal","Title","Heading 1","Heading 2"]:
        style=styles[style_name]
        style.font.name="Arial"
        style._element.rPr.rFonts.set(qn("w:eastAsia"),"Arial")
    styles["Normal"].font.size=Pt(9)

def _add_doc_header(section,ticker,page):
    header=section.header.paragraphs[0]
    header.text=f"BÁO CÁO PHÂN TÍCH, ĐỊNH GIÁ & M&A NGÂN HÀNG | {ticker}"
    for run in header.runs:
        run.font.name="Arial"
        run.font.size=Pt(8)
    footer=section.footer.paragraphs[0]
    footer.text="Tài liệu phân tích - không phải khuyến nghị đầu tư/chào mua."
    for run in footer.runs:
        run.font.name="Arial"
        run.font.size=Pt(7)

def _add_picture(doc,bio,width=178):
    bio.seek(0); doc.add_picture(bio,width=Mm(width))

def generate_docx_bytes(root,ticker,mode="investment"):
    d,row,peer_row,mna_row=_report_context(root,ticker)
    qa=assess_report_quality(row,d["cfg"],d["hist"],d["prices"])
    norm_flags=normalization_flags(row,d["cfg"],d["hist"] if False else d["prices"])
    strategic_case=strategic_reasonableness(row,d["cfg"],d.get("research"))
    strategic_case_text=reasonableness_conclusion(strategic_case)
    doc=Document(); sec=doc.sections[0]
    sec.page_width=Mm(210); sec.page_height=Mm(297); sec.top_margin=Mm(18); sec.bottom_margin=Mm(16); sec.left_margin=Mm(16); sec.right_margin=Mm(16)
    _doc_font(doc); cats,risks=catalysts_risks(row)

    pages=[
        ("1. TÓM TẮT ĐIỀU HÀNH",executive_summary(row,peer_row),_chart_scores(row,d["summary"])),
        ("2. HỒ SƠ NGÂN HÀNG & VỊ THẾ TƯƠNG ĐỐI",business_profile(row,peer_row),[
            _chart_history(d["hist"],ticker,["TotalAssets"],"Tổng tài sản",False),
            _chart_history(d["hist"],ticker,["GrossLoans"],"Dư nợ khách hàng",False),
            _chart_history(d["hist"],ticker,["CustomerDeposits"],"Tiền gửi khách hàng",False)]),
        ("3. KHẢ NĂNG SINH LỜI & HIỆU QUẢ HOẠT ĐỘNG",profitability_text(row,peer_row),[
            _chart_history(d["hist"],ticker,["ROE"],"Tỷ suất sinh lời trên vốn chủ sở hữu (ROE)",True),
            _chart_history(d["hist"],ticker,["ROA"],"Tỷ suất sinh lời trên tổng tài sản (ROA)",True),
            _chart_history(d["hist"],ticker,["NIM"],"Biên lãi ròng (NIM)",True),
            _chart_history(d["hist"],ticker,["CIR"],"Tỷ lệ chi phí/thu nhập (CIR)",True)]),
        ("4. CHẤT LƯỢNG TÀI SẢN & CHI PHÍ TÍN DỤNG",asset_quality_text(row,peer_row),_chart_history(d["hist"],ticker,["NPL"],"Xu hướng tỷ lệ nợ xấu (NPL)",True)),
        ("5. NGUỒN VỐN, THANH KHOẢN & CHI PHÍ HUY ĐỘNG",funding_text(row,peer_row),[
            _chart_history(d["hist"],ticker,["CASA"],"Tỷ lệ tiền gửi không kỳ hạn (CASA)",True),
            _chart_history(d["hist"],ticker,["LDR"],"Tỷ lệ cho vay trên tiền gửi (LDR)",True)]),
        ("6. VỐN, KHẢ NĂNG CHỐNG CHỊU & NĂNG LỰC TĂNG TRƯỞNG",capital_text(row,peer_row),_chart_history(d["hist"],ticker,["CAR"],"Xu hướng hệ số an toàn vốn (CAR)",True)),
        ("7. ĐỊNH GIÁ TƯƠNG ĐỐI & NHÓM SO SÁNH",valuation_text(row,peer_row),_chart_peer(d["summary"],ticker)),
        ("8. GIÁ TRỊ QUYỀN KIỂM SOÁT & MÔ PHỎNG M&A" if mode=="mna" else "8. ĐỊNH GIÁ CƠ BẢN & KIỂM TRA GIÁ THÂU TÓM",mna_text(row,mna_row) if mode=="mna" else valuation_text(row,peer_row)+" "+strategic_case_text,_chart_valuation(d["methods"],row,d["summary"])),
        ("9. PPA, GOODWILL & TÁC ĐỘNG TÁI CƠ CẤU" if mode=="mna" else "9. KIỂM TRA TÍNH HỢP LÝ 80.000–100.000 ĐỒNG/CP","Đối chiếu định lượng vùng giá chiến lược với thị giá, BVPS hiện tại/hậu xử lý, giá trị lô 32,5%, ước tính 63.250 tỷ đồng gốc+lãi liên quan và các benchmark nghiên cứu công khai. Đây là kiểm tra tính hợp lý kinh tế, không phải khẳng định giá giao dịch tương lai.",_chart_sensitivity(row)),
        ("10. KẾT LUẬN, ĐỘNG LỰC & RỦI RO",executive_summary(row,peer_row),None),
    ]
    for i,(head,body,chart) in enumerate(pages,1):
        _add_doc_header(doc.sections[-1],ticker,i)
        p=doc.add_paragraph(); p.style="Heading 1"; p.add_run(head)
        doc.add_paragraph(body)
        if i==1:
            p=doc.add_paragraph()
            r=p.add_run(f"TRẠNG THÁI: {qa['ReportStamp']} | Độ phủ: {qa['ReportCoverage']:.0%}")
            r.bold=True
            table=doc.add_table(rows=3,cols=4); table.style="Table Grid"
            vals=[("Giá thị trường",money(row.get("Price"))),("Giá trị cơ bản",money(row.get("FairValue_Base"))),("Chênh lệch cơ bản",pct(row.get("Upside_Base"))),("ROE",pct(row.get("ROE_Used"))),("P/B",mult(row.get("PB_Current"))),("NPL",pct(row.get("NPL")))]
            for j,(k,v) in enumerate(vals):
                rr=j//2; cc=(j%2)*2; table.cell(rr,cc).text=k; table.cell(rr,cc+1).text=v
        if chart is not None:
            if isinstance(chart,(list,tuple)):
                # Nhiều biểu đồ trên cùng một trang: thu nhỏ có kiểm soát để không tràn sang trang sau.
                chart_width = 86 if len(chart)>=3 else 138
                for ch in chart:
                    _add_picture(doc,ch,chart_width)
            else:
                _add_picture(doc,chart,176)
        if i==10:
            doc.add_paragraph("ĐỘNG LỰC TIỀM NĂNG",style="Heading 2")
            for x in cats[:5]: doc.add_paragraph(x,style="List Bullet")
            doc.add_paragraph("RỦI RO CHÍNH",style="Heading 2")
            for x in risks[:5]: doc.add_paragraph(x,style="List Bullet")
            doc.add_paragraph("ĐIỂM CẦN LƯU Ý KHI ĐỊNH GIÁ",style="Heading 2")
            for x in norm_flags[:5]: doc.add_paragraph(x,style="List Bullet")
            doc.add_paragraph("Tài liệu phân tích phục vụ mục đích tham khảo; không phải khuyến nghị mua/bán chứng khoán hoặc chào mua trong một thương vụ cụ thể.")
        if i<10: doc.add_page_break()
    bio=BytesIO(); doc.save(bio); return bio.getvalue()
