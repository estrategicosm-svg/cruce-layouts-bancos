"""Analyze BBVA PDF word positions to understand layout."""
import sys
import zipfile
import tempfile
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.legacy_pdf_engine import extract_words_digital

PAQUETE = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")
zip_path = str(PAQUETE / "ESTADOS_DE_CTA_RENOMBRADO.zip")

pdf_name = "ICOLD/ICOLD_BBVA_CTA2519_MXN_FEB2024.pdf"

with zipfile.ZipFile(zip_path) as zf:
    pdf_bytes = zf.read(pdf_name)
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, 'wb') as f:
        f.write(pdf_bytes)

    pages_words = extract_words_digital(tmp_path)
    os.unlink(tmp_path)

    # Page 2 has transactions
    if len(pages_words) > 1:
        print("--- PAGE 2 WORDS (first 40 lines) ---")
        for i, line_words in enumerate(pages_words[1][:40]):
            line_str = " ".join([w['text'] for w in line_words]).strip()
            x0_vals = [f"{w['x0']:.0f}-{w['x1']:.0f}" for w in line_words]
            print(f"  {i:3d}: |{line_str[:120]}|")
            for j, w in enumerate(line_words):
                print(f"       [{j}] x0={w['x0']:.1f} x1={w['x1']:.1f} top={w['top']:.1f} |{w['text']}|")
