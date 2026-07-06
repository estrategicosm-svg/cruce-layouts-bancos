import os
from parsers.pdf_parser import BancoPDFParser
from parsers.banco_parser import BancoParser
import io
import pandas as pd

PDF_DIR = r"C:\Users\USER\OneDrive - Sinergy IE SC\Escritorio\GENERA\ESTADOS_CTA\PRUEBA_INTEGRACION_CONCILIADOR_IVA_20260702"

class DummyUploadedFile:
    def __init__(self, name, content):
        self.name = name
        self.content = content
    def getvalue(self):
        return self.content
    def read(self):
        return self.content

def run_tests():
    print("=== PROBANDO FLUJO EXCEL ===")
    df_test = pd.DataFrame([{"fecha": "01/01/2024", "concepto": "Test", "cargo": 100}])
    buf = io.BytesIO()
    df_test.to_excel(buf, index=False)
    buf.seek(0)
    
    parser_banco = BancoParser()
    try:
        movs = parser_banco.parsear_excel(buf)
        print(f"Flujo Excel OK: {len(movs)} movimientos")
    except Exception as e:
        print(f"Flujo Excel FAILED: {e}")

    print("\n=== PROBANDO FLUJO PDF ===")
    pdf_parser = BancoPDFParser()
    
    for file in os.listdir(PDF_DIR):
        if not file.lower().endswith(".pdf"):
            continue
        print(f"\nProbando: {file}")
        path = os.path.join(PDF_DIR, file)
        with open(path, "rb") as f:
            content = f.read()
            
        df, validacion = pdf_parser.parsear_pdf(content, file)
        print(f"  Válido: {validacion['valido']}")
        if validacion['advertencias']:
            print("  Advertencias:")
            for a in validacion['advertencias']:
                print(f"   - {a}")
        else:
            print("  Sin advertencias")
            
        print(f"  Total Cargos: {validacion.get('total_cargos')}")
        print(f"  Total Abonos: {validacion.get('total_abonos')}")
        print(f"  Movimientos : {validacion.get('total_movimientos')}")

if __name__ == "__main__":
    run_tests()
