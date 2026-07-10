"""Debug why Banamex parse_banamex_statement extracts 0 txs from text that clearly has transactions."""
import sys
import os
import zipfile
import tempfile
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.legacy_pdf_engine import (
    detect_pdf_type, detect_bank, extract_words_digital,
    parse_transactions, parse_banamex_statement
)

PAQUETE = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")
zip_path = str(PAQUETE / "ESTADOS_DE_CTA_RENOMBRADO.zip")

# Use smallest Banamex file for debug
pdf_name = "CSC/CSC_BANAMEX_CTA7562_MXN_FEB2024.pdf"

with zipfile.ZipFile(zip_path) as zf:
    pdf_bytes = zf.read(pdf_name)

    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, 'wb') as f:
        f.write(pdf_bytes)

    pdf_type = detect_pdf_type(tmp_path)
    bank_name = detect_bank("", pdf_name)
    pages_words = extract_words_digital(tmp_path)
    os.unlink(tmp_path)

    print(f"PDF_TYPE: {pdf_type}")
    print(f"BANK_NAME: {bank_name}")
    print(f"TOTAL_PAGES: {len(pages_words)}")

    # Call parse_banamex_statement directly to debug
    txs, raw_text, warnings, recap = parse_banamex_statement(pages_words, pdf_name, pdf_type)

    print(f"TRANSACTIONS_EXTRACTED: {len(txs)}")
    print(f"RECAP: {recap}")

    # Now manually trace page 2 (where transactions start)
    # Page 2 = index 1
    if len(pages_words) > 1:
        page2_lines = pages_words[1]
        print(f"\n--- PAGE 2 LINES (count={len(page2_lines)}) ---")
        for i, line_words in enumerate(page2_lines[:30]):
            line_str = " ".join([w['text'] for w in line_words]).strip()
            line_upper = line_str.upper()
            # Check what the parser would do with this line
            has_fecha = bool(re.match(r"\d{1,2}\s+(?:ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)", line_upper))
            has_hora = "HORA " in line_upper and "SUC " in line_upper
            has_caja = "CAJA " in line_upper and "AUT " in line_upper
            has_detalle = "DETALLE DE OPERACIONES" in line_upper
            has_monto = bool(re.search(r"\d+[\.,]\d{2}", line_str))

            flags = []
            if has_fecha: flags.append("FECHA")
            if has_hora: flags.append("HORA_SUC")
            if has_caja: flags.append("CAJA_AUT")
            if has_detalle: flags.append("DETALLE")
            if has_monto: flags.append("MONTO")

            print(f"  {i:3d}: [{','.join(flags)}] |{line_str[:120]}|")
