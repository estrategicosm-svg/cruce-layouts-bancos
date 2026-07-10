"""Investigate CSC_BAJIO 60 movements with 0 cargo/abono, and the 2 MIXTO."""
import sys
import zipfile
import tempfile
import os
import pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.pdf_parser import BancoPDFParser

PAQUETE = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")
zip_path = str(PAQUETE / "ESTADOS_DE_CTA_RENOMBRADO.zip")

parser = BancoPDFParser()

# 1. CSC_BAJIO
with zipfile.ZipFile(zip_path) as zf:
    pdf_bytes = zf.read("CSC/CSC_BAJIO_CTA0201_MXN_FEB2024.pdf")
    df, val = parser.parsear_pdf(pdf_bytes, "CSC/CSC_BAJIO_CTA0201_MXN_FEB2024.pdf")
    print("=== CSC_BAJIO ===")
    print(f"len={len(df)}, val={val}")
    if len(df) > 0:
        print(df[['Fecha','Concepto','Cargo','Abono','Saldo']].head(10).to_string())
        # Check if these are legitimately 0-movement rows (like comision summary)
        cargo_sum = pd.to_numeric(df['Cargo'], errors='coerce').fillna(0).sum()
        abono_sum = pd.to_numeric(df['Abono'], errors='coerce').fillna(0).sum()
        print(f"Cargo sum={cargo_sum}, Abono sum={abono_sum}")
        # Show unique concepts
        print("UNIQUE CONCEPTS:")
        for c in df['Concepto'].unique()[:20]:
            print(f"  {c[:100]}")

# 2. MIXTO investigation - Banregio files
print("\n=== MIXTO INVESTIGATION ===")
for pdf_name in ["INTRA/INTRA_BANREGIO_CTA0026_MXN_FEB2024.pdf", "TRANSCRUCES/TRANSCRUCES_BANREGIO-TDC_CTA8222_MXN_FEB2024.pdf"]:
    with zipfile.ZipFile(zip_path) as zf:
        pdf_bytes = zf.read(pdf_name)
        df, val = parser.parsear_pdf(pdf_bytes, pdf_name)
        cargo_num = pd.to_numeric(df['Cargo'], errors='coerce').fillna(0)
        abono_num = pd.to_numeric(df['Abono'], errors='coerce').fillna(0)
        mask = (cargo_num > 0) & (abono_num > 0)
        mixto = df[mask]
        print(f"\n{pdf_name}: mixto_count={len(mixto)}")
        for _, row in mixto.iterrows():
            print(f"  Cargo={row['Cargo']:>14} Abono={row['Abono']:>14} Concepto={str(row['Concepto'])[:80]}")
            print(f"  Fecha={row['Fecha']} Saldo={row['Saldo']}")
