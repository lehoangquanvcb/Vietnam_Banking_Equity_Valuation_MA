from pathlib import Path
import argparse
try:
    from scripts.credit_rating_report import generate_credit_rating_pdf,generate_credit_rating_docx
except Exception:
    from credit_rating_report import generate_credit_rating_pdf,generate_credit_rating_docx
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--ticker',required=True);ap.add_argument('--out_dir',default=str(ROOT/'reports'));ap.add_argument('--governance',type=int,default=3);ap.add_argument('--support',type=int,default=0);ap.add_argument('--analyst',type=int,default=0);a=ap.parse_args();out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
(out/f'{a.ticker}_Bao_cao_Xep_hang_Tin_nhiem.pdf').write_bytes(generate_credit_rating_pdf(ROOT,a.ticker,a.governance,a.support,a.analyst))
(out/f'{a.ticker}_Bao_cao_Xep_hang_Tin_nhiem.docx').write_bytes(generate_credit_rating_docx(ROOT,a.ticker,a.governance,a.support,a.analyst))
print('Created:',out)
