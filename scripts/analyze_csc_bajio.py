"""Analyze CSC_BAJIO raw text to understand format and amount extraction issue."""
import sys
import zipfile
import tempfile
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pdfplumber

PAQUETE = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")
zip_path = str(PAQUETE / "ESTADOS_DE_CTA_RENOMBRADO.zip")

pdf_name = "CSC/CSC_BAJIO_CTA0201_MXN_FEB2024.pdf"

with zipfile.ZipFile(zip_path) as zf:
    pdf_bytes = zf.read(pdf_name)
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, 'wb') as f:
        f.write(pdf_bytes)

    with pdfplumber.open(tmp_path) as pdf:
        print(f"PAGINAS: {len(pdf.pages)}")
        for pg_idx in range(min(3, len(pdf.pages))):
            page = pdf.pages[pg_idx]
            text = page.extract_text() or ""
            print(f"\n--- PAGINA {pg_idx+1} ---")
            for i, line in enumerate(text.split('\n')[:30]):
                print(f"  {i:3d}: |{line}|")

    os.unlink(tmp_path)
