"""Process all 18 PDFs and report per-file metrics."""
import sys
import os
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.pdf_parser import BancoPDFParser

PAQUETE = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")
zip_path = str(PAQUETE / "ESTADOS_DE_CTA_RENOMBRADO.zip")

parser = BancoPDFParser()

results = []
with zipfile.ZipFile(zip_path) as zf:
    pdf_names = sorted(zf.namelist())
    for pdf_name in pdf_names:
        if not pdf_name.lower().endswith('.pdf'):
            continue
        pdf_bytes = zf.read(pdf_name)
        try:
            df, validation = parser.parsear_pdf(pdf_bytes, pdf_name)
            n = len(df)
            cargos = df['Cargo'].sum() if n > 0 else 0
            abonos = df['Abono'].sum() if n > 0 else 0
            banco = df['Banco'].iloc[0] if n > 0 else 'N/A'
            cuenta = df['Cuenta'].iloc[0] if n > 0 else 'N/A'
            moneda = df['Moneda'].iloc[0] if n > 0 else 'N/A'
            results.append({
                'ARCHIVO': pdf_name,
                'BANCO': banco,
                'CUENTA': cuenta,
                'MONEDA': moneda,
                'MOVIMIENTOS': n,
                'CARGOS': cargos,
                'ABONOS': abonos,
                'VALIDO': validation.get('valido'),
                'ADVERTENCIAS': '; '.join(validation.get('advertencias', []))
            })
        except Exception as e:
            results.append({
                'ARCHIVO': pdf_name,
                'BANCO': 'ERROR', 'CUENTA': 'ERROR', 'MONEDA': 'ERROR',
                'MOVIMIENTOS': 0, 'CARGOS': 0, 'ABONOS': 0,
                'VALIDO': False, 'ADVERTENCIAS': str(e)
            })

total_movs = sum(r['MOVIMIENTOS'] for r in results)
total_cargos = sum(r['CARGOS'] for r in results)
total_abonos = sum(r['ABONOS'] for r in results)
con_movs = sum(1 for r in results if r['MOVIMIENTOS'] > 0)
sin_movs = sum(1 for r in results if r['MOVIMIENTOS'] == 0)

print(f"{'ARCHIVO':<55} {'BANCO':<12} {'CUENTA':<12} {'MONEDA':<7} {'MOV':<6} {'CARGOS':>14} {'ABONOS':>14} {'VALIDO'}")
print("-" * 140)
for r in results:
    print(f"{r['ARCHIVO']:<55} {r['BANCO']:<12} {r['CUENTA']:<12} {r['MONEDA']:<7} {r['MOVIMIENTOS']:<6} {r['CARGOS']:>14,.2f} {r['ABONOS']:>14,.2f} {r['VALIDO']}")

print(f"\n{'='*140}")
print(f"TOTAL_PDFS={len(results)}")
print(f"CON_MOVIMIENTOS={con_movs}")
print(f"SIN_MOVIMIENTOS={sin_movs}")
print(f"MOVIMIENTOS_TOTAL={total_movs}")
print(f"CARGOS_TOTAL={total_cargos:,.2f}")
print(f"ABONOS_TOTAL={total_abonos:,.2f}")

# Detail for zero-movement PDFs
print(f"\n--- PDFs SIN MOVIMIENTOS ---")
for r in results:
    if r['MOVIMIENTOS'] == 0:
        print(f"  {r['ARCHIVO']}: {r['ADVERTENCIAS']}")

# Mixto analysis
print(f"\n--- ANALISIS MIXTO ---")
all_dfs = []
with zipfile.ZipFile(zip_path) as zf:
    for r in results:
        if r['MOVIMIENTOS'] > 0:
            pdf_bytes = zf.read(r['ARCHIVO'])
            df, _ = parser.parsear_pdf(pdf_bytes, r['ARCHIVO'])
            df['_ARCHIVO'] = r['ARCHIVO']
            all_dfs.append(df)

if all_dfs:
    import pandas as pd
    all_df = pd.concat(all_dfs, ignore_index=True)
    cargo_only = ((pd.to_numeric(all_df['Cargo'], errors='coerce').fillna(0) > 0) & 
                  (pd.to_numeric(all_df['Abono'], errors='coerce').fillna(0) == 0)).sum()
    abono_only = ((pd.to_numeric(all_df['Cargo'], errors='coerce').fillna(0) == 0) & 
                  (pd.to_numeric(all_df['Abono'], errors='coerce').fillna(0) > 0)).sum()
    mixto = ((pd.to_numeric(all_df['Cargo'], errors='coerce').fillna(0) > 0) & 
             (pd.to_numeric(all_df['Abono'], errors='coerce').fillna(0) > 0)).sum()
    print(f"CARGO_ONLY={cargo_only}")
    print(f"ABONO_ONLY={abono_only}")
    print(f"MIXTO={mixto}")

    # Show 20 mixto examples
    mask = (pd.to_numeric(all_df['Cargo'], errors='coerce').fillna(0) > 0) & (pd.to_numeric(all_df['Abono'], errors='coerce').fillna(0) > 0)
    mixto_df = all_df[mask].head(20)
    print(f"\n--- 20 EJEMPLOS MIXTOS ---")
    for _, row in mixto_df.iterrows():
        print(f"  {row['_ARCHIVO']:<45} Cargo={row['Cargo']:>12} Abono={row['Abono']:>12} Concepto={str(row['Concepto'])[:60]}")
