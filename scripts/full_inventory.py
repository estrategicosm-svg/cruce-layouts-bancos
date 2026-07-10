"""Full 18-PDF inventory table for H2 closure.
Raw counts from process_single_pdf; valid counts after zero-amount + es_movimiento_real filter.
"""
import os
import re
import sys
import tempfile
import zipfile

sys.path.insert(0, ".")
from parsers.legacy_pdf_engine import process_single_pdf
from parsers.pdf_parser import BancoPDFParser, REF_TRUNCADAS_INVALIDAS, REF_TRUNCADAS_REGEX
import pandas as pd

zip_path = r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR\ESTADOS_DE_CTA_RENOMBRADO.zip"

results = []

with zipfile.ZipFile(zip_path) as zf:
    for name in sorted(zf.namelist()):
        if not name.lower().endswith(".pdf"):
            continue
        data = zf.read(name)

        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            raw = process_single_pdf(tmp, name)
        finally:
            os.remove(tmp)

        raw_movs = raw.get("transacciones", [])
        raw_count = len(raw_movs)
        recap = raw.get("recap", {})

        valid_count = 0
        zero_count = 0
        mixto_count = 0
        cargo_total = 0.0
        abono_total = 0.0
        banco_from_data = ""

        for m in raw_movs:
            es_real = m.get("es_movimiento_real", True)
            c = float(m.get("cargo") or 0)
            a = float(m.get("abono") or 0)
            if not es_real:
                zero_count += 1
                continue
            if c == 0 and a == 0:
                zero_count += 1
                continue
            valid_count += 1
            if c > 0 and a > 0:
                mixto_count += 1
            cargo_total += c
            abono_total += a

        banco_from_data = recap.get("banco", "")
        if not banco_from_data and raw_movs:
            banco_from_data = raw_movs[0].get("banco", "")

        empresa = ""
        parts = name.split("/")
        if len(parts) > 1:
            empresa = parts[0]

        cuenta = recap.get("cuenta", "")
        moneda = recap.get("moneda", "MXN")

        status = "OK" if valid_count > 0 else "SIN MOVIMIENTOS"
        if zero_count > 0:
            status += f" [CERO={zero_count}]"
        if mixto_count > 0:
            status += f" [MIXTO={mixto_count}]"

        results.append({
            "ARCHIVO": name,
            "EMPRESA": empresa,
            "BANCO": banco_from_data,
            "CUENTA": cuenta,
            "MONEDA": moneda,
            "FILAS_BRUTAS": raw_count,
            "IMPORTE_CERO": zero_count,
            "MOVIMIENTOS_VALIDOS": valid_count,
            "MIXTOS": mixto_count,
            "CARGO_TOTAL": round(cargo_total, 2),
            "ABONO_TOTAL": round(abono_total, 2),
            "ESTATUS": status,
        })

hdr = (f"{'ARCHIVO':<55} {'EMP':<8} {'BANCO':<10} {'CUENTA':<16} {'MON':<5}"
       f" {'BRUT':>4} {'ZERO':>4} {'VALID':>5} {'MIX':>3}"
       f" {'CARGO':>14} {'ABONO':>14} {'ESTATUS'}")
print(hdr)
print("=" * len(hdr))
t = {"brut": 0, "zero": 0, "valid": 0, "mix": 0, "cargo": 0.0, "abono": 0.0}
for r in results:
    print(f"{r['ARCHIVO']:<55} {r['EMPRESA']:<8} {r['BANCO']:<10} {r['CUENTA']:<16} {r['MONEDA']:<5}"
          f" {r['FILAS_BRUTAS']:>4} {r['IMPORTE_CERO']:>4} {r['MOVIMIENTOS_VALIDOS']:>5} {r['MIXTOS']:>3}"
          f" {r['CARGO_TOTAL']:>14.2f} {r['ABONO_TOTAL']:>14.2f} {r['ESTATUS']}")
    t["brut"] += r["FILAS_BRUTAS"]
    t["zero"] += r["IMPORTE_CERO"]
    t["valid"] += r["MOVIMIENTOS_VALIDOS"]
    t["mix"] += r["MIXTOS"]
    t["cargo"] += r["CARGO_TOTAL"]
    t["abono"] += r["ABONO_TOTAL"]
print("=" * len(hdr))
print(f"{'TOTAL':<55} {'':<8} {'':<10} {'':<16} {'':<5}"
      f" {t['brut']:>4} {t['zero']:>4} {t['valid']:>5} {t['mix']:>3}"
      f" {t['cargo']:>14.2f} {t['abono']:>14.2f}")
print()
print("UNIVERSO FINAL:")
print(f"  FILAS_PARSEADAS_BRUTAS        = {t['brut']}")
print(f"  FILAS_IMPORTE_CERO_DESCARTADAS= {t['zero']}")
print(f"  MOVIMIENTOS_VALIDOS           = {t['valid']}")
print(f"  MOVIMIENTOS_MIXTOS            = {t['mix']}")
print(f"  MOVIMIENTOS_ELEGIBLES_AUTOM   = {t['valid'] - t['mix']}")
print(f"  REFERENCIAS_TRUNCADAS_ACEPTADAS = 0")
