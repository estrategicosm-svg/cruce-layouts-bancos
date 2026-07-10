"""Check CSC_BAJIO word positions to understand amount extraction failure."""
import sys
import zipfile
import tempfile
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.legacy_pdf_engine import extract_words_digital, group_words_into_lines, partition_line, get_default_columns

PAQUETE = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")
zip_path = str(PAQUETE / "ESTADOS_DE_CTA_RENOMBRADO.zip")

pdf_name = "CSC/CSC_BAJIO_CTA0201_MXN_FEB2024.pdf"

with zipfile.ZipFile(zip_path) as zf:
    pdf_bytes = zf.read(pdf_name)
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, 'wb') as f:
        f.write(pdf_bytes)

    pages_words = extract_words_digital(tmp_path)
    os.unlink(tmp_path)

    # Page 1 = transactions start
    for pg_idx in range(min(2, len(pages_words))):
        print(f"\n=== PAGE {pg_idx+1} ===")
        for i, line_words in enumerate(pages_words[pg_idx][:15]):
            line_str = " ".join([w['text'] for w in line_words]).strip()
            # Check what columns these words fall into
            columns = [
                ("Fecha", 0, 70),
                ("Concepto", 70, 250),
                ("Cargo", 250, 320),
                ("Abono", 320, 400),
                ("Saldo", 400, 650)
            ]
            row_text, row_words = partition_line(line_words, columns)
            
            has_amount = any("$" in w['text'] or "," in w['text'] for w in line_words)
            monto_words = [w for w in line_words if any(c.isdigit() for c in w['text']) and len(w['text']) > 1]
            
            print(f"  {i:3d}: |{line_str[:100]}|")
            if monto_words:
                for w in monto_words:
                    cx = (w['x0'] + w['x1']) / 2.0
                    print(f"       [{w['text']}] x0={w['x0']:.1f} cx={cx:.1f}")
            print(f"       FECHA=|{row_text['Fecha']}| CONCEPTO=|{row_text['Concepto'][:50]}| CARGO=|{row_text['Cargo']}| ABONO=|{row_text['Abono']}| SALDO=|{row_text['Saldo']}|")
