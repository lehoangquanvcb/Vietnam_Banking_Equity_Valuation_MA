from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.report_engine import report_font_status
from scripts.credit_rating_report import credit_rating_font_status

def main():
    pkg=ROOT/'packages.txt'
    if not pkg.exists():
        raise SystemExit('FAIL: packages.txt missing')
    text=pkg.read_text(encoding='utf-8').lower()
    if 'fonts-lato' not in text:
        raise SystemExit('FAIL: packages.txt does not request fonts-lato')
    a=report_font_status(); b=credit_rating_font_status()
    if not a.get('ok') or not b.get('ok'):
        raise SystemExit(f'FAIL: no Unicode PDF fallback: valuation={a}, rating={b}')
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    if 'default_rating_export' not in app or 'rating_result=None' not in app:
        raise SystemExit('FAIL: rating state guard missing')
    if 'Không tìm thấy font Lato để xuất PDF' in (ROOT/'scripts/report_engine.py').read_text(encoding='utf-8'):
        raise SystemExit('FAIL: fatal Lato-only PDF guard remains')
    print('OK - Streamlit runtime guards passed.')
    print('Valuation report font runtime:',a)
    print('Credit-rating report font runtime:',b)

if __name__=='__main__': main()
