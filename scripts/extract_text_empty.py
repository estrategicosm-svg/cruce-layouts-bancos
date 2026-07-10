"""Extract full text from page 2+ of the 6 empty PDFs to understand the format."""
import sys
import zipfile
import tempfile
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

PAQUETE = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")
zip_path = str(PAQUETE / "ESTADOS_DE_CTA_RENOMBRADO.zip")

VACIOS = [
    "CSC/CSC_BANAMEX_CTA7562_MXN_FEB2024.pdf",
    "ICOLD/ICOLD_BANAMEX_CTA3695_MXN_FEB2024.pdf",
    "ICOLD/ICOLD_BAJIO_CTA0201_MXN_FEB2024.pdf",
    "ICOLD/ICOLD_BANAMEX_CTA2995_USD_FEB2024.pdf",
    "INTRA/INTRA_BANAMEX_CTA0859_USD_FEB2024.pdf",
    "INTRA/INTRA_BANAMEX_CTA0688_MXN_FEB2024.pdf",
]

import pdfplumber

with zipfile.ZipFile(zip_path) as zf:
    for pdf_name in VACIOS:
        print(f"\n{'='*80}")
        print(f"ARCHIVO: {pdf_name}")
        pdf_bytes = zf.read(pdf_name)

        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(fd, 'wb') as tmp:
            tmp.write(pdf_bytes)

        try:
            with pdfplumber.open(tmp_path) as pdf:
                print(f"  PAGINAS: {len(pdf.pages)}")
                for pg_idx in range(min(2, len(pdf.pages))):
                    page = pdf.pages[pg_idx]
                    text = page.extract_text() or ""
                    print(f"\n  --- PAGINA {pg_idx+1} TEXTO COMPLETO ---")
                    for i, line in enumerate(text.split('\n')):
                        print(f"    {i:3d}: |{line}|")
                    print(f"  --- FIN PAGINA {pg_idx+1} ---")
        except Exception as e:
            print(f"  ERROR: {e}")
        finally:
            os.unlink(tmp_path)
