"""Diagnostico de los 6 PDFs vacios."""
import sys
import zipfile
import tempfile
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

PAQUETE = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")

VACIOS = [
    "CSC/CSC_BANAMEX_CTA7562_MXN_FEB2024.pdf",
    "ICOLD/ICOLD_BANAMEX_CTA3695_MXN_FEB2024.pdf",
    "ICOLD/ICOLD_BAJIO_CTA0201_MXN_FEB2024.pdf",
    "ICOLD/ICOLD_BANAMEX_CTA2995_USD_FEB2024.pdf",
    "INTRA/INTRA_BANAMEX_CTA0859_USD_FEB2024.pdf",
    "INTRA/INTRA_BANAMEX_CTA0688_MXN_FEB2024.pdf",
]

zip_path = str(PAQUETE / "ESTADOS_DE_CTA_RENOMBRADO.zip")

with zipfile.ZipFile(zip_path) as zf:
    for pdf_name in VACIOS:
        print(f"\n{'='*70}")
        print(f"ARCHIVO: {pdf_name}")
        pdf_bytes = zf.read(pdf_name)

        # 1. Tamano
        print(f"  TAMANO_BYTES: {len(pdf_bytes)}")

        # 2. Intentar con pdfplumber directo
        import pdfplumber
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            with pdfplumber.open(tmp_path) as pdf:
                print(f"  PAGINAS: {len(pdf.pages)}")
                for i, page in enumerate(pdf.pages[:2]):
                    text = page.extract_text() or ""
                    tables = page.extract_tables() or []
                    print(f"  PAGINA_{i+1}_TEXTO_PRIMERAS_5_LINEAS:")
                    for line in text.split('\n')[:5]:
                        print(f"    |{line}|")
                    print(f"  PAGINA_{i+1}_TABLAS: {len(tables)}")
                    for ti, t in enumerate(tables[:2]):
                        print(f"    TABLA_{ti+1}_ROWS: {len(t)}")
                        for row in t[:3]:
                            print(f"      {row}")

            os.unlink(tmp_path)
        except Exception as e:
            print(f"  ERROR_PDFPLUMBER: {e}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        # 3. Intentar con el parser del proyecto
        from parsers.pdf_parser import BancoPDFParser
        parser = BancoPDFParser()
        try:
            df, validation = parser.parsear_pdf(pdf_bytes, pdf_name)
            print(f"  PARSER_RESULT: cols={list(df.columns) if hasattr(df, 'columns') else 'N/A'}, len={len(df)}")
            print(f"  PARSER_VALIDATION: {validation}")
        except Exception as e:
            print(f"  PARSER_ERROR: {e}")

        # 4. Buscar texto plano en el PDF
        text_bytes = pdf_bytes
        text_fragments = []
        i = 0
        while i < len(text_bytes):
            idx = text_bytes.find(b'Text', i)
            if idx == -1:
                break
            chunk = text_bytes[max(0,idx-20):idx+100]
            # Check if this is near readable text
            printable = sum(1 for b in chunk if 32 <= b < 127)
            if printable > 20:
                try:
                    text_fragments.append(chunk.decode('latin-1', errors='replace'))
                except:
                    pass
            i = idx + 1
            if len(text_fragments) >= 3:
                break

        if text_fragments:
            print(f"  TEXT_FRAGMENTS_FOUND: {len(text_fragments)}")
            for tf in text_fragments[:3]:
                print(f"    {tf[:120]}")
