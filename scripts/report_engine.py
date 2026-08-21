
from pathlib import Path
from io import BytesIO
import os, math, json, tempfile
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

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

PAGE_W,PAGE_H=A4
MARGIN=16*mm

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
        "cfg":json.loads((root/"config/model_config.json").read_text(encoding="utf-8")) if (root/"config/model_config.json").exists() else {}
    }

def _font_paths():
    candidates=[
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf","/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf","/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    ]
    for a,b in candidates:
        if Path(a).exists() and Path(b).exists():return a,b
    return None,None

def _register_pdf_fonts():
    reg,bold=_font_paths()
    if reg and "VNFont" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("VNFont",reg))
        pdfmetrics.registerFont(TTFont("VNFont-Bold",bold))
    return ("VNFont","VNFont-Bold") if reg else ("Helvetica","Helvetica-Bold")

def _period_sort(s):
    import re
    st=str(s).upper()
    y=re.search(r"(20\d{2})",st); q=re.search(r"Q([1-4])",st)
    return (int(y.group(1)) if y else 0,int(q.group(1)) if q else 0,st)

def _metric_history(hist,ticker,metrics):
    if hist.empty:return pd.DataFrame()
    x=hist[hist["Ticker"].astype(str).eq(str(ticker)) & hist["Metric"].astype(str).isin(metrics)].copy()
    if x.empty:return x
    x["Value"]=pd.to_numeric(x["Value"],errors="coerce")
    x=x.dropna(subset=["Value"])
    if "CAR" in metrics:
        x=x[~((x["Metric"].astype(str)=="CAR") & (x["Value"]<=0))]
    x["_sort"]=x["Period"].astype(str).map(_period_sort)
    return x.sort_values("_sort")

def _fig_to_png(fig):
    bio=BytesIO()
    fig.savefig(bio,format="png",dpi=160,bbox_inches="tight")
    plt.close(fig); bio.seek(0)
    return bio

def _chart_history(hist,ticker,metrics,title,percent=False):
    x=_metric_history(hist,ticker,metrics)
    fig,ax=plt.subplots(figsize=(7.4,3.3))
    if x.empty:
        ax.text(.5,.5,"Chưa có đủ dữ liệu lịch sử",ha="center",va="center")
        ax.set_axis_off()
    else:
        for metric,g in x.groupby("Metric"):
            ax.plot(g["Period"].astype(str),g["Value"],marker="o",label=str(metric))
        ax.set_title(title); ax.grid(alpha=.2); ax.legend(fontsize=8)
        ax.tick_params(axis="x",rotation=45,labelsize=7)
        if percent:
            ax.yaxis.set_major_formatter(lambda v,pos:f"{v:.1%}")
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
        if len(cur):
            ax.scatter(cur["ROE_Used"],cur["PB_Current"],s=120,marker="*")
        ax.set_xlabel("ROE"); ax.set_ylabel("P/B (x)"); ax.set_title("Bản đồ ROE - P/B của nhóm ngân hàng")
        ax.xaxis.set_major_formatter(lambda v,pos:f"{v:.0%}"); ax.grid(alpha=.2)
    return _fig_to_png(fig)

def _chart_valuation(methods,row):
    fig,ax=plt.subplots(figsize=(7.4,3.3))
    m=methods[methods["Ticker"].astype(str).eq(str(row.get("Ticker")))].copy() if len(methods) else pd.DataFrame()
    if m.empty:
        ax.text(.5,.5,"Chưa có kết quả theo phương pháp",ha="center",va="center"); ax.set_axis_off()
    else:
        m["FairValuePerShare"]=pd.to_numeric(m["FairValuePerShare"],errors="coerce")
        m=m.dropna(subset=["FairValuePerShare"])
        m["FairValuePerShare"]=m["FairValuePerShare"]*1000
        ax.bar(m["Method"],m["FairValuePerShare"])
        if n(row.get("Price")) is not None: ax.axhline(n(row.get("Price"))*1000,linestyle="--",label="Giá thị trường")
        ax.set_title("Giá trị hợp lý theo phương pháp"); ax.set_ylabel("VND/cp"); ax.tick_params(axis="x",rotation=20,labelsize=8)
        ax.legend(fontsize=8)
    return _fig_to_png(fig)

def _chart_scores(row):
    names=["Sinh lời","Tăng trưởng","Chất lượng TS","Nguồn vốn","An toàn vốn","Định giá"]
    vals=[row.get("ProfitabilityScore"),row.get("GrowthScore"),row.get("AssetQualityScore"),row.get("FundingScore"),row.get("CapitalScore"),row.get("ValuationScore")]
    fig,ax=plt.subplots(figsize=(7.4,3.1))
    y=np.arange(len(names))
    vv=[n(v) or 0 for v in vals]
    ax.barh(y,vv); ax.set_yticks(y,names); ax.set_xlim(0,100); ax.set_title("Thẻ điểm 6 trụ cột")
    for i,v in enumerate(vv): ax.text(v+1,i,f"{v:.0f}",va="center",fontsize=8)
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
        im=ax.imshow(mat,aspect="auto")
        ax.set_xticks(range(len(coes)),[f"{x:.1%}" for x in coes])
        ax.set_yticks(range(len(roes)),[f"{x:.1%}" for x in roes])
        ax.set_xlabel("Chi phí vốn chủ sở hữu (COE)"); ax.set_ylabel("ROE chuẩn hóa")
        ax.set_title("Sensitivity giá trị hợp lý: ROE x COE")
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]): ax.text(j,i,f"{mat[i,j]/1000:.1f}k",ha="center",va="center",fontsize=7)
        fig.colorbar(im,ax=ax,fraction=.035,pad=.03,label="VND/cp")
    return _fig_to_png(fig)

def _chart_price(prices,ticker):
    fig,ax=plt.subplots(figsize=(7.4,3.0))
    p=prices[prices["Ticker"].astype(str).eq(str(ticker))].copy() if len(prices) else pd.DataFrame()
    if p.empty:
        ax.text(.5,.5,"Chưa có lịch sử giá",ha="center",va="center"); ax.set_axis_off()
    else:
        p["Date"]=pd.to_datetime(p["Date"],errors="coerce"); p["Close"]=pd.to_numeric(p["Close"],errors="coerce")
        p=p.dropna().sort_values("Date")
        ax.plot(p["Date"],p["Close"]); ax.set_title("Diễn biến giá cổ phiếu"); ax.set_ylabel("VND/cp"); ax.grid(alpha=.2)
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
    p=Paragraph(str(text).replace("\n","<br/>"),style)
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
    c.drawString(MARGIN,7*mm,"Nguồn: Vnstock/BCTC + mô hình nội bộ. ACTUAL/CALCULATED/ASSUMPTION tách riêng.")
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
    title="BÁO CÁO PHÂN TÍCH, ĐỊNH GIÁ & M&A NGÂN HÀNG"
    cats,risks=catalysts_risks(row)
    qa=assess_report_quality(row,d["cfg"],d["hist"],d["prices"])
    norm_flags=normalization_flags(row,d["cfg"],d["prices"])
    stamp=qa["ReportStamp"]

    # Page 1
    _draw_header(c,title,ticker,1,font,bold,stamp)
    y=PAGE_H-29*mm; y=_draw_para(c,f"1. TÓM TẮT ĐIỀU HÀNH - {ticker}",st["h1"],MARGIN,y,120*mm,30*mm)
    y=_draw_para(c,executive_summary(row),st["body"],MARGIN,y-2*mm,118*mm,70*mm)
    _kpi_table(c,[("Giá thị trường",money(row.get("Price"))),("Giá trị hợp lý",money(row.get("FairValue_Base"))),("Tiềm năng",pct(row.get("Upside_Base"))),("P/B hiện tại",mult(row.get("PB_Current"))),("ROE",pct(row.get("ROE_Used"))),("Điểm đầu tư",f"{n(row.get('InvestmentScore')):.0f}/100" if n(row.get("InvestmentScore")) is not None else "N/A")],st,PAGE_H-32*mm)
    _draw_image(c,_chart_scores(row),MARGIN,31*mm,175*mm,66*mm)
    _draw_para(c,f"Trạng thái báo cáo: {qa['ReportStatus']} | Độ phủ kiểm soát: {qa['ReportCoverage']:.0%} | Thiếu chỉ tiêu lõi: {qa['CoreMissingCount']}",st["small"],MARGIN,27*mm,175*mm,12*mm)
    if n(row.get("StrategicPriceLow")) is not None:
        _draw_para(c,f"Market Intelligence/M&A: {money(row.get('StrategicPriceLow'))} - {money(row.get('StrategicPriceHigh'))} | Nguồn: {row.get('StrategicSource','N/A')} | Không phải fair value fundamental.",st["small"],MARGIN,20*mm,175*mm,12*mm)
    c.showPage()

    # Page 2
    _draw_header(c,title,ticker,2,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"2. HỒ SƠ NGÂN HÀNG & VỊ THẾ TƯƠNG ĐỐI",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,business_profile(row,peer_row),st["body"],MARGIN,y-2*mm,175*mm,45*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["TotalAssets","GrossLoans","CustomerDeposits"],"Quy mô bảng cân đối và tăng trưởng",False),MARGIN,77*mm,175*mm,90*mm)
    _draw_image(c,_chart_price(d["prices"],ticker),MARGIN,25*mm,175*mm,48*mm)
    c.showPage()

    # Page 3
    _draw_header(c,title,ticker,3,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"3. KHẢ NĂNG SINH LỜI & HIỆU QUẢ HOẠT ĐỘNG",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,profitability_text(row),st["body"],MARGIN,y-2*mm,175*mm,42*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["ROE","ROA","NIM","CIR"],"ROE - ROA - NIM - CIR",True),MARGIN,70*mm,175*mm,105*mm)
    c.showPage()

    # Page 4
    _draw_header(c,title,ticker,4,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"4. CHẤT LƯỢNG TÀI SẢN & CHI PHÍ TÍN DỤNG",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,asset_quality_text(row),st["body"],MARGIN,y-2*mm,175*mm,42*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["NPL"],"Xu hướng tỷ lệ nợ xấu (NPL)",True),MARGIN,69*mm,175*mm,108*mm)
    y=61*mm
    _draw_para(c,"Lưu ý: Provision Expense có thể được Vnstock/BCTC thể hiện theo đơn vị tiền tệ, do đó cần đọc cùng raw source khi so sánh với tỷ lệ NPL.",st["small"],MARGIN,y,175*mm,20*mm)
    c.showPage()

    # Page 5
    _draw_header(c,title,ticker,5,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"5. NGUỒN VỐN, THANH KHOẢN & CHI PHÍ HUY ĐỘNG",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,funding_text(row),st["body"],MARGIN,y-2*mm,175*mm,45*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["CASA","LDR"],"CASA và LDR",True),MARGIN,70*mm,175*mm,108*mm)
    c.showPage()

    # Page 6
    _draw_header(c,title,ticker,6,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"6. VỐN, KHẢ NĂNG CHỐNG CHỊU & NĂNG LỰC TĂNG TRƯỞNG",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,capital_text(row),st["body"],MARGIN,y-2*mm,175*mm,45*mm)
    _draw_image(c,_chart_history(d["hist"],ticker,["CAR"],"Xu hướng hệ số an toàn vốn (CAR)",True),MARGIN,70*mm,175*mm,108*mm)
    c.showPage()

    # Page 7
    _draw_header(c,title,ticker,7,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"7. ĐỊNH GIÁ TƯƠNG ĐỐI & NHÓM SO SÁNH",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,valuation_text(row),st["body"],MARGIN,y-2*mm,175*mm,43*mm)
    _draw_image(c,_chart_peer(d["summary"],ticker),MARGIN,82*mm,175*mm,95*mm)
    if peer_row:
        pdata=[["Chỉ tiêu",ticker,"Peer median"],
               ["ROE",pct(row.get("ROE_Used")),pct(peer_row.get("MedianROE"))],
               ["NIM",pct(row.get("NIM")),pct(peer_row.get("MedianNIM"))],
               ["NPL",pct(row.get("NPL")),pct(peer_row.get("MedianNPL"))],
               ["CAR",pct(row.get("CAR")),pct(peer_row.get("MedianCAR"))],
               ["CASA",pct(row.get("CASA")),pct(peer_row.get("MedianCASA"))],
               ["P/B",mult(row.get("PB_Current")),mult(peer_row.get("MedianPB"))]]
        tt=Table(pdata,colWidths=[45*mm,45*mm,45*mm]); tt.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.35,colors.grey),("FONTNAME",(0,0),(-1,-1),font),("FONTSIZE",(0,0),(-1,-1),7.5),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF0F7"))]))
        tw,th=tt.wrap(140*mm,60*mm); tt.drawOn(c,MARGIN,25*mm)
    c.showPage()

    # Page 8
    _draw_header(c,title,ticker,8,font,bold,stamp); y=PAGE_H-29*mm
    if mode=="mna":
        y=_draw_para(c,"8. GIÁ TRỊ QUYỀN KIỂM SOÁT & MÔ PHỎNG M&A",st["h1"],MARGIN,y,170*mm,20*mm)
        y=_draw_para(c,mna_text(row,mna_row),st["body"],MARGIN,y-2*mm,175*mm,55*mm)
        if mna_row:
            data=[["Standalone",bn(mna_row.get("StandaloneEquityValue"))],["PV cộng hưởng",bn(mna_row.get("PV_Synergies"))],["Chi phí tích hợp",bn(mna_row.get("IntegrationCost"))],["Consideration",bn(mna_row.get("IllustrativeConsideration"))],["P/B giao dịch",mult(mna_row.get("ImpliedPB"))],["P/TBV giao dịch",mult(mna_row.get("ImpliedPTBV"))]]
            t=Table(data,colWidths=[60*mm,65*mm]); t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.4,colors.grey),("FONTNAME",(0,0),(-1,-1),font),("FONTSIZE",(0,0),(-1,-1),8.5),("BACKGROUND",(0,0),(0,-1),colors.HexColor("#F3F6FA"))]))
            tw,th=t.wrap(130*mm,100*mm); t.drawOn(c,MARGIN,y-th-10*mm)
    else:
        y=_draw_para(c,"8. ĐỊNH GIÁ CƠ BẢN & GIÁ TRỊ CHIẾN LƯỢC",st["h1"],MARGIN,y,170*mm,20*mm)
        y=_draw_para(c,valuation_text(row),st["body"],MARGIN,y-2*mm,175*mm,38*mm)
        if n(row.get("StrategicPriceLow")) is not None:
            strategic=(f"Lớp giá trị chiến lược/M&A được ghi nhận riêng ở {money(row.get('StrategicPriceLow'))} - {money(row.get('StrategicPriceHigh'))}. "
                       f"Nguồn: {row.get('StrategicSource','N/A')}; ngày {row.get('StrategicAsOfDate','N/A')}; confidence {row.get('StrategicConfidence','N/A')}. "
                       "Khoảng này không được dùng để ép ngược giá trị cơ bản; chênh lệch cần được giải thích bằng quy mô lô, quyền kiểm soát, scarcity, tái cơ cấu và synergy.")
            y=_draw_para(c,strategic,st["body"],MARGIN,y-2*mm,175*mm,42*mm)
        _draw_image(c,_chart_valuation(d["methods"],row),MARGIN,69*mm,175*mm,95*mm)
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
        y=_draw_para(c,"9. PHÂN TÍCH ĐỘ NHẠY & BIÊN AN TOÀN",st["h1"],MARGIN,y,170*mm,20*mm)
        y=_draw_para(c,"Độ nhạy của giá trị hợp lý được kiểm tra theo hai biến trọng yếu nhất của định giá ngân hàng: ROE chuẩn hóa và chi phí vốn chủ sở hữu. Ma trận bên dưới không phải dự báo xác suất mà là khung kiểm tra biên an toàn.",st["body"],MARGIN,y-2*mm,175*mm,42*mm)
        _draw_image(c,_chart_sensitivity(row),MARGIN,70*mm,175*mm,108*mm)
    c.showPage()

    # Page 10
    _draw_header(c,title,ticker,10,font,bold,stamp); y=PAGE_H-29*mm
    y=_draw_para(c,"10. KẾT LUẬN, ĐỘNG LỰC & RỦI RO",st["h1"],MARGIN,y,170*mm,20*mm)
    y=_draw_para(c,executive_summary(row),st["body"],MARGIN,y-2*mm,175*mm,48*mm)
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
    norm_flags=normalization_flags(row,d["cfg"],d["prices"])
    doc=Document(); sec=doc.sections[0]
    sec.page_width=Mm(210); sec.page_height=Mm(297); sec.top_margin=Mm(18); sec.bottom_margin=Mm(16); sec.left_margin=Mm(16); sec.right_margin=Mm(16)
    _doc_font(doc); cats,risks=catalysts_risks(row)

    pages=[
        ("1. TÓM TẮT ĐIỀU HÀNH",executive_summary(row),_chart_scores(row)),
        ("2. HỒ SƠ NGÂN HÀNG & VỊ THẾ TƯƠNG ĐỐI",business_profile(row,peer_row),_chart_history(d["hist"],ticker,["TotalAssets","GrossLoans","CustomerDeposits"],"Quy mô bảng cân đối",False)),
        ("3. KHẢ NĂNG SINH LỜI & HIỆU QUẢ HOẠT ĐỘNG",profitability_text(row),_chart_history(d["hist"],ticker,["ROE","ROA","NIM","CIR"],"ROE - ROA - NIM - CIR",True)),
        ("4. CHẤT LƯỢNG TÀI SẢN & CHI PHÍ TÍN DỤNG",asset_quality_text(row),_chart_history(d["hist"],ticker,["NPL"],"Xu hướng tỷ lệ nợ xấu (NPL)",True)),
        ("5. NGUỒN VỐN, THANH KHOẢN & CHI PHÍ HUY ĐỘNG",funding_text(row),_chart_history(d["hist"],ticker,["CASA","LDR"],"CASA và LDR",True)),
        ("6. VỐN, KHẢ NĂNG CHỐNG CHỊU & NĂNG LỰC TĂNG TRƯỞNG",capital_text(row),_chart_history(d["hist"],ticker,["CAR"],"Xu hướng hệ số an toàn vốn (CAR)",True)),
        ("7. ĐỊNH GIÁ TƯƠNG ĐỐI & NHÓM SO SÁNH",valuation_text(row),_chart_peer(d["summary"],ticker)),
        ("8. GIÁ TRỊ QUYỀN KIỂM SOÁT & MÔ PHỎNG M&A" if mode=="mna" else "8. ĐỊNH GIÁ NỘI TẠI & FOOTBALL FIELD",mna_text(row,mna_row) if mode=="mna" else valuation_text(row),_chart_valuation(d["methods"],row)),
        ("9. PPA, GOODWILL & TÁC ĐỘNG TÁI CƠ CẤU" if mode=="mna" else "9. PHÂN TÍCH ĐỘ NHẠY & BIÊN AN TOÀN","Phân tích độ nhạy kiểm tra tác động của ROE chuẩn hóa và COE đối với giá trị hợp lý. Trong M&A, cùng khung này được dùng để kiểm tra khả năng chịu đựng của giá mua tối đa.",_chart_sensitivity(row)),
        ("10. KẾT LUẬN, ĐỘNG LỰC & RỦI RO",executive_summary(row),None),
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
            vals=[("Giá thị trường",money(row.get("Price"))),("Giá trị hợp lý",money(row.get("FairValue_Base"))),("Tiềm năng",pct(row.get("Upside_Base"))),("ROE",pct(row.get("ROE_Used"))),("P/B",mult(row.get("PB_Current"))),("NPL",pct(row.get("NPL")))]
            for j,(k,v) in enumerate(vals):
                rr=j//2; cc=(j%2)*2; table.cell(rr,cc).text=k; table.cell(rr,cc+1).text=v
        if chart is not None:_add_picture(doc,chart,176)
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
