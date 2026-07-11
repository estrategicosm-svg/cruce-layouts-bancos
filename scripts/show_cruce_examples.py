"""Show real CRUCE_ID examples from the full universe of 1000 movements."""
import sys
import zipfile
import tempfile
import os
from pathlib import Path
from decimal import Decimal
from collections import defaultdict, Counter
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.pdf_parser import BancoPDFParser
from agent3.engine import (
    _construir_universo_movimientos,
    asignar_cruce_ids,
    _extraer_empresa,
    _mapear_banco_code,
    _naturaleza_tipo_cruce,
)

ZIP_PATH = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR\ESTADOS_DE_CTA_RENOMBRADO.zip")

parser = BancoPDFParser()
all_movimientos = []

with zipfile.ZipFile(str(ZIP_PATH)) as zf:
    for name in sorted(zf.namelist()):
        if not name.lower().endswith(".pdf"):
            continue
        df, validation = parser.parsear_pdf(zf.read(name), name)
        if df is not None and not df.empty:
            for idx, row in df.iterrows():
                cargo_val = row.get("Cargo", 0)
                abono_val = row.get("Abono", 0)
                try:
                    c = Decimal(str(cargo_val).replace(",", "")) if cargo_val else Decimal("0")
                except Exception:
                    c = Decimal("0")
                try:
                    a = Decimal(str(abono_val).replace(",", "")) if abono_val else Decimal("0")
                except Exception:
                    a = Decimal("0")

                if c == 0 and a == 0:
                    continue

                fecha_val = row.get("Fecha", None)
                if isinstance(fecha_val, datetime):
                    fecha = fecha_val
                elif hasattr(fecha_val, "to_pydatetime"):
                    fecha = fecha_val.to_pydatetime()
                else:
                    try:
                        fecha = datetime.strptime(str(fecha_val), "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        fecha = datetime(2024, 2, 1)

                from core.models import MovimientoBancario
                m = MovimientoBancario(
                    banco=str(row.get("Banco", "") or ""),
                    cuenta=str(row.get("Cuenta", "") or ""),
                    fecha=fecha,
                    concepto=str(row.get("Concepto", "") or ""),
                    cargo=c,
                    abono=a,
                    moneda=str(row.get("Moneda", "MXN") or "MXN"),
                    referencia=str(row.get("Referencia_Bancaria_Limpia", "") or "").strip(),
                )
                m._fila_origen = idx + 2
                m._archivo_origen = name
                all_movimientos.append(m)

print(f"\nTOTAL MOVIMIENTOS VALIDOS: {len(all_movimientos)}")

universo = _construir_universo_movimientos(all_movimientos, "ESTADOS_DE_CTA_RENOMBRADO.pdf")
cruce_map = asignar_cruce_ids(universo)

# Distribution
dist = Counter()
for r in universo:
    tipo = _naturaleza_tipo_cruce(r.NATURALEZA)
    banco_code = _mapear_banco_code(r.BANCO)
    key = (r.EMPRESA, tipo, banco_code)
    dist[key] += 1

print("\n" + "=" * 60)
print("DISTRIBUCION EMPRESA-TIPO-BANCO (consecutivo final)")
print("=" * 60)
for (emp, tipo, banco), count in sorted(dist.items()):
    print(f"  {emp}-{tipo}-{banco:<6} = {count:>4} movimientos (consecutivos 001-{count:03d})")

print("\n" + "=" * 60)
print("EJEMPLOS REALES POR EMPRESA + TIPO + BANCO")
print("=" * 60)

# Group by (empresa, tipo, banco)
groups = defaultdict(list)
for r in universo:
    tipo = _naturaleza_tipo_cruce(r.NATURALEZA)
    banco_code = _mapear_banco_code(r.BANCO)
    groups[(r.EMPRESA, tipo, banco_code)].append(r)

for (emp, tipo, banco), records in sorted(groups.items()):
    print(f"\n--- {emp}-{tipo}-{banco} ({len(records)} movimientos) ---")
    for r in records[:3]:
        print(f"  {r.CRUCE_ID}  fecha={r.FECHA}  cargo={r.CARGO:>14}  abono={r.ABONO:>14}  archivo={r.ARCHIVO_BANCO}")
    if len(records) > 3:
        last = records[-1]
        print(f"  ... ({len(records) - 3} mas)")
        print(f"  {last.CRUCE_ID}  fecha={last.FECHA}  cargo={last.CARGO:>14}  abono={last.ABONO:>14}")

# Verify determinism
universo2 = _construir_universo_movimientos(all_movimientos, "ESTADOS_DE_CTA_RENOMBRADO.pdf")
cruce_map2 = asignar_cruce_ids(universo2)
match = all(r1.CRUCE_ID == r2.CRUCE_ID for r1, r2 in zip(universo, universo2))
print(f"\n{'=' * 60}")
print(f"DETERMINISMO: {'OK - misma entrada produce mismos CRUCE_ID' if match else 'FALLO'}")
print(f"{'=' * 60}")

# Verify uniqueness
ids = [r.CRUCE_ID for r in universo]
print(f"UNICIDAD: {'OK - todos unicos' if len(ids) == len(set(ids)) else 'FALLO - duplicados'}")
print(f"TOTAL CRUCE_IDs asignados: {len(set(ids))}")
