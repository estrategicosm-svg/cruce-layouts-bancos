"""Trace exact code path: BancoPDFParser.parsear_pdf -> process_single_pdf"""
import sys
import os
import zipfile
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.pdf_parser import BancoPDFParser

PAQUETE = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")
zip_path = str(PAQUETE / "ESTADOS_DE_CTA_RENOMBRADO.zip")

pdf_name = "CSC/CSC_BANAMEX_CTA7562_MXN_FEB2024.pdf"

with zipfile.ZipFile(zip_path) as zf:
    pdf_bytes = zf.read(pdf_name)

parser = BancoPDFParser()
try:
    df, validation = parser.parsear_pdf(pdf_bytes, pdf_name)
    print(f"DF_LEN: {len(df)}")
    print(f"VALIDATION: {validation}")
except Exception as e:
    import traceback
    traceback.print_exc()

# Now try process_single_pdf directly
from parsers.legacy_pdf_engine import process_single_pdf
fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
with os.fdopen(fd, 'wb') as f:
    f.write(pdf_bytes)

try:
    resultado = process_single_pdf(tmp_path)
    txs = resultado.get("transacciones", [])
    real_movs = [m for m in txs if m.get("es_movimiento_real", True)]
    print(f"\nDIRECT: txs={len(txs)}, real_movs={len(real_movs)}")
    print(f"BANK: {resultado.get('banco')}")
    print(f"RECAP: {resultado.get('recap')}")
    for i, t in enumerate(txs[:3]):
        print(f"  TX {i}: cargo={t.get('cargo')}, abono={t.get('abono')}, real={t.get('es_movimiento_real')}, evidencia={t.get('es_evidencia')}")
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    os.unlink(tmp_path)
