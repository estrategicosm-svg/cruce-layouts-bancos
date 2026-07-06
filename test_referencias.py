import os
import re
import pandas as pd
from parsers.pdf_parser import BancoPDFParser

PDF_DIR = r"C:\Users\USER\OneDrive - Sinergy IE SC\Escritorio\GENERA\ESTADOS_CTA\PRUEBA_INTEGRACION_CONCILIADOR_IVA_20260702"

def evaluar_referencia(ref, row):
    ref = str(ref).strip()
    if not ref or ref == 'nan':
        return "VACÍA"
        
    # SOSPECHOSA: si es igual al cargo o abono
    cargo = str(row.get('Cargo', '')).replace('.0', '')
    abono = str(row.get('Abono', '')).replace('.0', '')
    
    # O si tiene formato de fecha YYYYMMDD
    if len(ref) == 8 and (ref.startswith('2023') or ref.startswith('2024')):
        return "SOSPECHOSA (Parece fecha YYYYMMDD)"
        
    if ref == cargo or ref == abono:
        return "SOSPECHOSA (Es el mismo importe)"
        
    if len(ref) < 6:
        return "SOSPECHOSA (Muy corta, <6 caracteres)"
        
    return "OK"

def run_tests():
    pdf_parser = BancoPDFParser()
    
    for file in os.listdir(PDF_DIR):
        if not file.lower().endswith(".pdf"):
            continue
            
        print(f"\n======================================")
        print(f"BANCO / ARCHIVO: {file}")
        print(f"======================================")
        
        path = os.path.join(PDF_DIR, file)
        with open(path, "rb") as f:
            content = f.read()
            
        df, validacion = pdf_parser.parsear_pdf(content, file)
        
        # Calculate stats
        total = len(df)
        if total == 0:
            print("No se extrajeron movimientos.")
            continue
            
        con_ref = df['Referencia_Bancaria_Limpia'].apply(lambda x: str(x).strip() != '' and str(x).strip() != 'nan').sum()
        pct = (con_ref / total) * 100 if total > 0 else 0
        
        sospechosas = 0
        
        muestras = df.head(10).copy()
        
        print(f"Total movimientos: {total}")
        print(f"Con Referencia rescatada: {con_ref} ({pct:.1f}%)")
        print(f"Mejoró extracción: {'SÍ' if pct > 0 else 'NO'}")
        print(f"Errores de montos: Cargos={validacion.get('total_cargos')}, Abonos={validacion.get('total_abonos')}\n")
        
        print(f"{'FECHA':<12} | {'CONCEPTO':<40} | {'REF_LIMPIA':<15} | {'CARGO':<10} | {'ABONO':<10} | {'VALIDACION'}")
        print("-" * 120)
        
        for idx, row in df.iterrows():
            ref = row.get('Referencia_Bancaria_Limpia', '')
            val = evaluar_referencia(ref, row)
            if "SOSPECHOSA" in val:
                sospechosas += 1
                
            if idx < 10:
                fecha = str(row.get('Fecha', ''))[:10]
                concepto = str(row.get('Concepto', ''))[:38].replace('\n', ' ')
                ref_limpia = str(ref)[:13]
                cargo = str(row.get('Cargo', 0))
                abono = str(row.get('Abono', 0))
                print(f"{fecha:<12} | {concepto:<40} | {ref_limpia:<15} | {cargo:<10} | {abono:<10} | {val}")
                
        print(f"\nTotal Sospechosas en todo el archivo: {sospechosas}")

if __name__ == "__main__":
    run_tests()
