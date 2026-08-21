
from pathlib import Path
import argparse
try:
    from scripts.report_engine import generate_pdf_bytes, generate_docx_bytes
except Exception:
    from report_engine import generate_pdf_bytes, generate_docx_bytes

ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser()
ap.add_argument("--ticker",required=True)
ap.add_argument("--mode",choices=["investment","mna","restructuring"],default="investment")
ap.add_argument("--out_dir",default=str(ROOT/"reports"))
args=ap.parse_args()
out=Path(args.out_dir); out.mkdir(parents=True,exist_ok=True)
pdf=generate_pdf_bytes(ROOT,args.ticker,args.mode)
docx=generate_docx_bytes(ROOT,args.ticker,args.mode)
(out/f"{args.ticker}_Bao_cao_Phan_tich_Dinh_gia.pdf").write_bytes(pdf)
(out/f"{args.ticker}_Bao_cao_Phan_tich_Dinh_gia.docx").write_bytes(docx)
print("Created:",out)
