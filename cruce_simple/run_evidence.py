"""Genera evidencia final del cruce simple."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cruce_simple.app import ejecutar_cruce


def main() -> None:
    paq = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")
    out = Path(__file__).parent.parent / "outputs" / "CRUCE_LAYOUTS_VS_BANCOS_FEB24.xlsx"

    eg = (paq / "LAYOUT_CARGA_EGRESOS.xlsx").read_bytes()
    ing = (paq / "LAYOUT_CEDULA_INGRESOS.xlsx").read_bytes()
    zip_b = (paq / "ESTADOS_DE_CTA_RENOMBRADO.zip").read_bytes()

    r = ejecutar_cruce(
        egresos_bytes=eg, nombre_egresos="LAYOUT_CARGA_EGRESOS.xlsx",
        ingresos_bytes=ing, nombre_ingresos="LAYOUT_CEDULA_INGRESOS.xlsx",
        zip_bancos_bytes=zip_b, nombre_zip="ESTADOS_DE_CTA_RENOMBRADO.zip",
        archivo_salida=str(out),
    )

    print("=" * 70)
    print("EVIDENCIA FINAL — CRUCE SIMPLE LAYOUTS vs BANCOS")
    print("=" * 70)
    for k in [
        "FILAS_EGRESOS", "FILAS_INGRESOS",
        "GRUPOS_EGRESOS", "GRUPOS_INGRESOS",
        "MOVIMIENTOS_BANCARIOS", "MOVIMIENTOS_CARGOS",
        "MOVIMIENTOS_ABONOS", "MOVIMIENTOS_TDC",
        "CRUCES_ENCONTRADOS_EGRESOS", "CRUCES_ENCONTRADOS_INGRESOS",
        "MULTIPLES_CANDIDATOS", "SIN_CANDIDATO", "MONEDAS_MIXTAS",
        "ARCHIVO", "TAMAÑO", "SHA256", "HOJAS",
    ]:
        print(f"  {k} = {r[k]}")
    print("=" * 70)


if __name__ == "__main__":
    main()
